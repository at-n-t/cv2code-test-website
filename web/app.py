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

app = Flask(__name__)
app.secret_key = os.environ.get("CV2CC_SECRET", "cv2cc-dev-secret-change-in-prod")

# Temp output directory inside web/
OUTPUT_DIR = Path(__file__).parent / "generated"
OUTPUT_DIR.mkdir(exist_ok=True)


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
    )


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
