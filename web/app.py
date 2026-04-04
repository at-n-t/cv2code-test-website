"""
CV2CC Web Application — Flask backend
"""

import json
import sys
import os
import uuid
import tempfile
from pathlib import Path
from datetime import date, datetime

# Load .env for local development (no-op on Vercel where env vars are set in dashboard)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on environment variables already being set

# Allow imports from parent directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import (
    Flask, render_template, request, jsonify,
    send_file, url_for, session,
)

from models.building import (
    BuildingData, Jurisdiction, Room,
    RiskCategory, ConstructionType, OccupancyGroup, ZoningDistrict,
)
from generators.pdf_generator import generate_pdf
from generators.compliance_checker import check_compliance

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
_secret = os.environ.get("CV2CC_SECRET")
if _secret:
    app.secret_key = _secret
else:
    import secrets as _secrets
    app.secret_key = _secrets.token_hex(32)  # ephemeral — set CV2CC_SECRET in env for persistent sessions

# Vercel's filesystem is read-only; use /tmp there, web/generated locally
OUTPUT_DIR = Path("/tmp/cv2cc") if os.environ.get("VERCEL") else Path(__file__).parent / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Reference data endpoints (populate dropdowns)
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    data_dir = Path(__file__).parent.parent / "data"
    with open(data_dir / "state_code_adoptions.json", encoding="utf-8") as f:
        states = json.load(f)
    # Remove _note key
    states = {k: v for k, v in states.items() if not k.startswith("_")}
    return render_template("index.html",
        states=states,
        risk_categories=[r.value for r in RiskCategory],
        construction_types=[c.value for c in ConstructionType],
        occupancy_groups=[o.value for o in OccupancyGroup],
        zoning_districts=[z.value for z in ZoningDistrict],
        today=date.today().isoformat(),
        statsig_client_key=os.environ.get("STATSIG_CLIENT_KEY", ""),
    )


# ---------------------------------------------------------------------------
# Chat interface (Version B — A/B test)
# ---------------------------------------------------------------------------

_CHAT_SYSTEM_PROMPT = """You are CV2CC, an expert AI assistant that helps licensed architects \
fill out CV2 building permit application forms in the United States. Your job is to guide them \
through a friendly, conversational interview — one topic at a time — to collect all the \
information needed to generate a complete CV2 code-compliance form.

TONE: Professional, warm, efficient. No fluff. Architects are busy — be direct.

INTERVIEW ORDER (cover every topic before declaring ready):
1. Project basics — name, project number (optional), permit number (optional), date prepared
2. Professional credentials — architect name & license #, structural engineer license (optional)
3. Site location — street address, city, county, STATE (critical — drives code editions)
4. Code jurisdiction — IBC/IRC edition (auto-suggest from state below), local amendments
5. Building classification — occupancy group(s) (A/B/E/F/H/I/M/R/S/U), construction type \
(I-A, I-B, II-A, II-B, III-A, III-B, IV, V-A, V-B), risk category (I–IV), zoning district
6. Dimensions — stories above grade, below grade, height (ft), total floor area (sq ft), \
footprint (sq ft)
7. Room/space breakdown — for each major space: room name, occupancy group, floor area
8. Fire & life safety — sprinkler system (NFPA 13 / 13R / 13D), fire alarm system
9. ADA / accessibility — ADA compliant, accessible route, total parking, accessible parking
10. Energy & special — energy code, climate zone, special conditions, variances

STATE → DEFAULT IBC EDITION quick reference:
CA→2022, NY→2020, FL→2020, TX→2021, WA→2021, CO→2021, IL→2021, GA→2021, AZ→2018, all others→2021

RULES:
- Ask only ONE topic at a time. Wait for the user's reply before moving on.
- When the user provides information, confirm it briefly ("Got it — 3 stories, 42 ft tall.") \
then ask the next question.
- If the user is unsure about a value, give a sensible default and tell them they can update it later.
- When you have collected AT MINIMUM (project name, state, occupancy, construction type, \
stories, building height, floor area), ask: "I have enough to generate your CV2 form — shall I \
go ahead?"
- If they confirm, include your normal conversational sign-off AND append the JSON block below.
- Only include the <cv2_data> block ONCE, after confirmation.

OUTPUT FORMAT (append after your conversational message, ONLY upon user confirmation):
<cv2_data>
{
  "project_name": "",
  "project_number": "",
  "permit_number": "",
  "date_prepared": "",
  "prepared_by": "",
  "architect_license": "",
  "engineer_license": "",
  "site_address": "",
  "parcel_number": "",
  "jurisdiction": {
    "country": "USA",
    "state": "",
    "county": "",
    "city": "",
    "ibc_edition": "2021",
    "irc_edition": "2021",
    "nfpa_edition": "2021",
    "local_amendments": ""
  },
  "zoning_district": "C-2",
  "risk_category": "II",
  "construction_type": "V-B",
  "occupancy_groups": [],
  "mixed_occupancy": false,
  "mixed_occupancy_method": "",
  "stories_above_grade": 1,
  "stories_below_grade": 0,
  "building_height_ft": 0,
  "total_floor_area_sqft": 0,
  "footprint_sqft": 0,
  "rooms": [],
  "sprinkler_system": false,
  "sprinkler_standard": "",
  "fire_alarm_system": false,
  "fire_alarm_standard": "",
  "ada_compliant": true,
  "accessible_route": true,
  "total_parking_spaces": 0,
  "accessible_parking_spaces": 0,
  "energy_code": "",
  "climate_zone": "",
  "osha_applicable": false,
  "ifc_edition": "2021",
  "additional_codes": [],
  "special_conditions": "",
  "variances_requested": ""
}
</cv2_data>

Fill every field you have collected. Use sensible defaults for anything not provided."""


@app.route("/chat")
def chat():
    return render_template("chat.html",
        statsig_client_key=os.environ.get("STATSIG_CLIENT_KEY", ""),
        today=date.today().isoformat(),
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    try:
        import anthropic
        import re

        data = request.get_json(force=True)
        messages = data.get("messages", [])

        if not messages:
            return jsonify({"ok": False, "error": "No messages provided"}), 400

        # Anthropic requires messages to start with "user" and alternate roles.
        # Strip any leading assistant messages as a safety guard.
        while messages and messages[0].get("role") != "user":
            messages = messages[1:]

        if not messages:
            return jsonify({"ok": False, "error": "Message history must contain at least one user message"}), 400

        # Deduplicate consecutive same-role messages (merge into one)
        merged = [messages[0]]
        for msg in messages[1:]:
            if msg["role"] == merged[-1]["role"]:
                merged[-1] = {"role": msg["role"], "content": merged[-1]["content"] + "\n" + msg["content"]}
            else:
                merged.append(msg)
        messages = merged

        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=_CHAT_SYSTEM_PROMPT,
            messages=messages,
        )

        full_reply = response.content[0].text

        # Extract structured cv2_data if present
        match = re.search(r"<cv2_data>(.*?)</cv2_data>", full_reply, re.DOTALL)
        cv2_data = None
        if match:
            try:
                cv2_data = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                cv2_data = None

        # Strip the JSON block from what the user sees
        visible = re.sub(r"\s*<cv2_data>.*?</cv2_data>", "", full_reply, flags=re.DOTALL).strip()

        return jsonify({
            "ok": True,
            "message": visible,
            "cv2_data": cv2_data,
            "ready": cv2_data is not None,
        })

    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/state-codes/<state>")
def state_codes(state):
    data_dir = Path(__file__).parent.parent / "data"
    with open(data_dir / "state_code_adoptions.json", encoding="utf-8") as f:
        adoptions = json.load(f)
    entry = adoptions.get(state.upper(), {})
    return jsonify(entry)


@app.route("/api/occupant-load-factor/<occupancy>")
def occupant_load_factor(occupancy):
    data_dir = Path(__file__).parent.parent / "data"
    with open(data_dir / "occupant_load_factors.json", encoding="utf-8") as f:
        factors = json.load(f)
    entry = factors.get(occupancy, {"factor": 0, "note": "Refer to IBC Table 1004.5"})
    return jsonify(entry)


# ---------------------------------------------------------------------------
# Live compliance check (AJAX)
# ---------------------------------------------------------------------------

@app.route("/api/check", methods=["POST"])
def api_check():
    try:
        building = _build_from_form(request.get_json(force=True))
        findings = check_compliance(building)
        return jsonify({
            "ok": True,
            "findings": [
                {"level": f.level, "code_ref": f.code_ref, "description": f.description}
                for f in findings
            ],
            "total_occupant_load": building.total_occupant_load,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


# ---------------------------------------------------------------------------
# Generate PDF
# ---------------------------------------------------------------------------

@app.route("/api/generate", methods=["POST"])
def api_generate():
    try:
        building = _build_from_form(request.get_json(force=True))
        filename  = f"cv2_{uuid.uuid4().hex[:8]}.pdf"
        out_path  = OUTPUT_DIR / filename
        generate_pdf(building, str(out_path))
        # Return the download token
        return jsonify({"ok": True, "token": filename})
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/ai-guidance", methods=["POST"])
def api_ai_guidance():
    try:
        import anthropic

        data = request.get_json(force=True)
        question = data.get("question", "").strip()
        building_context = data.get("building_context", {})

        if not question:
            return jsonify({"ok": False, "error": "No question provided"}), 400

        # Build a concise project summary for context
        ctx_lines = []
        if building_context.get("project_name"):
            ctx_lines.append(f"Project: {building_context['project_name']}")
        j = building_context.get("jurisdiction", {})
        if j.get("state"):
            ctx_lines.append(f"State: {j['state']}")
        if j.get("county"):
            ctx_lines.append(f"County: {j['county']}")
        if j.get("ibc_edition"):
            ctx_lines.append(f"IBC Edition: {j['ibc_edition']}")
        if j.get("local_amendments"):
            ctx_lines.append(f"Local Amendments: {j['local_amendments']}")
        if building_context.get("risk_category"):
            ctx_lines.append(f"Risk Category: {building_context['risk_category']}")
        if building_context.get("construction_type"):
            ctx_lines.append(f"Construction Type: {building_context['construction_type']}")
        if building_context.get("occupancy_groups"):
            ctx_lines.append(f"Occupancy: {', '.join(building_context['occupancy_groups'])}")
        if building_context.get("total_floor_area_sqft"):
            ctx_lines.append(f"Floor Area: {building_context['total_floor_area_sqft']:,} sq ft")
        if building_context.get("building_height_ft"):
            ctx_lines.append(f"Height: {building_context['building_height_ft']} ft")
        if building_context.get("stories_above_grade"):
            ctx_lines.append(f"Stories above grade: {building_context['stories_above_grade']}")
        if building_context.get("sprinkler_system"):
            ctx_lines.append(f"Sprinkler: {building_context.get('sprinkler_standard', 'Yes')}")
        if building_context.get("ada_compliant"):
            ctx_lines.append("ADA Compliant: Yes")

        building_summary = "\n".join(ctx_lines) if ctx_lines else "No project data entered yet."

        client = anthropic.Anthropic()
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            system=(
                "You are an expert building code consultant specializing in IBC (International Building Code), "
                "ADA Standards for Accessible Design (2010), NFPA codes, and US state/local building regulations. "
                "You assist licensed architects with code compliance questions for their projects.\n\n"
                "Guidelines:\n"
                "- Always cite specific code sections (e.g., IBC §903.2.1, ADA §208.2, NFPA 13).\n"
                "- Be concise but thorough. Architects are professionals — skip obvious caveats.\n"
                "- Flag when state or local amendments commonly affect the answer.\n"
                "- When values are tabular (e.g., occupant load factors, parking ratios), provide the specific numbers.\n"
                "- End with one short note if AHJ (Authority Having Jurisdiction) review is advisable."
            ),
            messages=[
                {
                    "role": "user",
                    "content": f"Project context:\n{building_summary}\n\nQuestion: {question}",
                }
            ],
        )

        return jsonify({"ok": True, "answer": message.content[0].text})

    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/download/<token>")
def download(token):
    # Basic validation — token must be a safe filename ending in .pdf
    if not token.endswith(".pdf") or "/" in token or "\\" in token:
        return "Invalid token", 400
    path = OUTPUT_DIR / token
    if not path.exists():
        return "File not found", 404
    project_name = request.args.get("name", "cv2_form")
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project_name)
    return send_file(
        str(path),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{safe_name}_CV2.pdf",
    )


# ---------------------------------------------------------------------------
# Form -> BuildingData parser
# ---------------------------------------------------------------------------

def _build_from_form(data: dict) -> BuildingData:
    j_data = data.get("jurisdiction", {})
    jurisdiction = Jurisdiction(
        country          = j_data.get("country", "USA"),
        state            = j_data.get("state", ""),
        county           = j_data.get("county", ""),
        city             = j_data.get("city", ""),
        ibc_edition      = j_data.get("ibc_edition", "2021"),
        irc_edition      = j_data.get("irc_edition", "2021"),
        nfpa_edition     = j_data.get("nfpa_edition", "2021"),
        local_amendments = j_data.get("local_amendments", ""),
    )

    rooms = []
    for rd in data.get("rooms", []):
        try:
            og = OccupancyGroup(rd.get("occupancy_group", "B"))
        except ValueError:
            og = OccupancyGroup.B
        rooms.append(Room(
            name                 = rd.get("name", ""),
            occupancy_group      = og,
            floor_area_sqft      = float(rd.get("floor_area_sqft", 0) or 0),
            occupant_load_factor = float(rd.get("occupant_load_factor", 0) or 0),
        ))

    occ_groups = []
    for r in data.get("occupancy_groups", []):
        try:
            occ_groups.append(OccupancyGroup(r))
        except ValueError:
            pass

    try:
        risk = RiskCategory(data.get("risk_category", "II"))
    except ValueError:
        risk = RiskCategory.II

    try:
        const_type = ConstructionType(data.get("construction_type", "V-B"))
    except ValueError:
        const_type = ConstructionType.VB

    try:
        zoning = ZoningDistrict(data.get("zoning_district", "R-1"))
    except ValueError:
        zoning = ZoningDistrict.R1

    return BuildingData(
        project_name          = data.get("project_name", ""),
        project_number        = data.get("project_number", ""),
        permit_number         = data.get("permit_number", ""),
        date_prepared         = data.get("date_prepared", date.today().isoformat()),
        prepared_by           = data.get("prepared_by", ""),
        architect_license     = data.get("architect_license", ""),
        engineer_license      = data.get("engineer_license", ""),
        site_address          = data.get("site_address", ""),
        parcel_number         = data.get("parcel_number", ""),
        jurisdiction          = jurisdiction,
        zoning_district       = zoning,
        risk_category         = risk,
        construction_type     = const_type,
        occupancy_groups      = occ_groups,
        mixed_occupancy       = bool(data.get("mixed_occupancy", False)),
        mixed_occupancy_method= data.get("mixed_occupancy_method", ""),
        stories_above_grade   = int(data.get("stories_above_grade", 1) or 1),
        stories_below_grade   = int(data.get("stories_below_grade", 0) or 0),
        building_height_ft    = float(data.get("building_height_ft", 0) or 0),
        total_floor_area_sqft = float(data.get("total_floor_area_sqft", 0) or 0),
        footprint_sqft        = float(data.get("footprint_sqft", 0) or 0),
        rooms                 = rooms,
        sprinkler_system      = bool(data.get("sprinkler_system", False)),
        sprinkler_standard    = data.get("sprinkler_standard", ""),
        fire_alarm_system     = bool(data.get("fire_alarm_system", False)),
        fire_alarm_standard   = data.get("fire_alarm_standard", ""),
        ada_compliant         = bool(data.get("ada_compliant", True)),
        accessible_route      = bool(data.get("accessible_route", True)),
        accessible_parking_spaces = int(data.get("accessible_parking_spaces", 0) or 0),
        total_parking_spaces  = int(data.get("total_parking_spaces", 0) or 0),
        energy_code           = data.get("energy_code", ""),
        climate_zone          = data.get("climate_zone", ""),
        osha_applicable       = bool(data.get("osha_applicable", False)),
        ifc_edition           = data.get("ifc_edition", "2021"),
        additional_codes      = data.get("additional_codes", []),
        special_conditions    = data.get("special_conditions", ""),
        variances_requested   = data.get("variances_requested", ""),
    )


if __name__ == "__main__":
    print("CV2CC -- starting on http://localhost:5000")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port, use_reloader=False)
