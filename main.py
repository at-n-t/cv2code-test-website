"""
CV2CC — Code Compliance Verification Form Generator
====================================================
Generates a filled CV2 PDF form from either:
  • a JSON input file  (--input  path/to/project.json)
  • interactive prompts (--interactive)
  • a built-in demo project (no flags)

Usage:
    python main.py                        # run demo
    python main.py --interactive          # guided prompts
    python main.py --input my_project.json
    python main.py --input my_project.json --output reports/my_form.pdf
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from models.building import (
    BuildingData, Jurisdiction, Room,
    RiskCategory, ConstructionType, OccupancyGroup, ZoningDistrict,
)
from generators.pdf_generator import generate_pdf


# ---------------------------------------------------------------------------
# Demo project
# ---------------------------------------------------------------------------

def _demo_project() -> BuildingData:
    """Sample mixed-use office/retail building for demonstration."""
    b = BuildingData(
        project_name     = "Riverside Commerce Center",
        project_number   = "2025-0312",
        permit_number    = "BP-2025-00441",
        date_prepared    = date.today().isoformat(),
        prepared_by      = "Jane Architect, AIA",
        architect_license= "CA-C-12345",
        engineer_license = "SE-67890",

        site_address     = "1200 River Road, Suite 100",
        parcel_number    = "123-456-789-00",
        jurisdiction     = Jurisdiction(
            country          = "USA",
            state            = "CA",
            county           = "Sacramento",
            city             = "Sacramento",
            ibc_edition      = "2022",
            irc_edition      = "2022",
            nfpa_edition     = "2021",
            local_amendments = "Sacramento City Amendments to 2022 CBC",
        ),
        zoning_district  = ZoningDistrict.C2,

        risk_category      = RiskCategory.II,
        construction_type  = ConstructionType.VA,
        occupancy_groups   = [OccupancyGroup.B, OccupancyGroup.M],
        mixed_occupancy    = True,
        mixed_occupancy_method = "Non-Separated",

        stories_above_grade  = 3,
        stories_below_grade  = 0,
        building_height_ft   = 42.0,
        total_floor_area_sqft= 24000.0,
        footprint_sqft       = 8000.0,

        rooms = [
            Room("Ground Floor Retail",   OccupancyGroup.M,  8000, 30),
            Room("2nd Floor Office",       OccupancyGroup.B,  8000, 100),
            Room("3rd Floor Office",       OccupancyGroup.B,  6500, 100),
            Room("Lobby / Common",         OccupancyGroup.B,  1500, 100),
        ],

        sprinkler_system     = True,
        sprinkler_standard   = "NFPA 13",
        fire_alarm_system    = True,
        fire_alarm_standard  = "NFPA 72",

        ada_compliant          = True,
        accessible_route       = True,
        accessible_parking_spaces = 4,
        total_parking_spaces   = 60,

        energy_code  = "ASHRAE 90.1-2019 / Title 24-2022",
        climate_zone = "3B",

        osha_applicable    = False,
        ifc_edition        = "2021",
        additional_codes   = ["ASCE 7-22", "ACI 318-19"],

        special_conditions  = "Site within 500-year flood zone. Finished floor elevation per FEMA requirements.",
        variances_requested = "None",
    )
    return b


# ---------------------------------------------------------------------------
# JSON loader
# ---------------------------------------------------------------------------

def _from_json(path: str) -> BuildingData:
    """Load BuildingData from a JSON file produced by --dump-schema."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    j_data = data.pop("jurisdiction", {})
    rooms_data = data.pop("rooms", [])

    j = Jurisdiction(**{k: v for k, v in j_data.items() if k in Jurisdiction.__dataclass_fields__})

    rooms = []
    for rd in rooms_data:
        og = OccupancyGroup(rd.get("occupancy_group", "B"))
        rooms.append(Room(
            name=rd.get("name", ""),
            occupancy_group=og,
            floor_area_sqft=rd.get("floor_area_sqft", 0),
            occupant_load_factor=rd.get("occupant_load_factor", 0),
        ))

    # Convert enum fields
    def _get(key, enum_cls, default):
        raw = data.pop(key, None)
        if raw is None:
            return default
        try:
            return enum_cls(raw)
        except ValueError:
            print(f"[warn] Unknown value '{raw}' for {key}; using default.")
            return default

    risk       = _get("risk_category",    RiskCategory,    RiskCategory.II)
    const_type = _get("construction_type",ConstructionType,ConstructionType.VB)
    zoning     = _get("zoning_district",  ZoningDistrict,  ZoningDistrict.R1)

    raw_occ = data.pop("occupancy_groups", [])
    occ_groups = []
    for r in raw_occ:
        try:
            occ_groups.append(OccupancyGroup(r))
        except ValueError:
            print(f"[warn] Unknown occupancy group '{r}'; skipping.")

    # Remove computed/non-init fields
    for f in ("total_occupant_load",):
        data.pop(f, None)

    return BuildingData(
        **{k: v for k, v in data.items() if k in BuildingData.__dataclass_fields__},
        jurisdiction     = j,
        rooms            = rooms,
        risk_category    = risk,
        construction_type= const_type,
        zoning_district  = zoning,
        occupancy_groups = occ_groups,
    )


# ---------------------------------------------------------------------------
# Interactive wizard
# ---------------------------------------------------------------------------

def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt}{suffix}: ").strip()
    return val if val else default


def _choose(prompt: str, options: list, default_idx: int = 0) -> str:
    print(f"\n{prompt}")
    for i, opt in enumerate(options):
        marker = " *" if i == default_idx else "  "
        print(f"{marker} {i+1}. {opt}")
    raw = input(f"  Choice [1-{len(options)}] (default {default_idx+1}): ").strip()
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    return options[default_idx]


def _interactive_wizard() -> BuildingData:
    print("\n" + "="*60)
    print("  CV2CC — Interactive Form Wizard")
    print("="*60)

    b = BuildingData()
    b.date_prepared = date.today().isoformat()

    print("\n--- PROJECT IDENTIFICATION ---")
    b.project_name      = _ask("Project name")
    b.project_number    = _ask("Project number")
    b.permit_number     = _ask("Permit number")
    b.prepared_by       = _ask("Prepared by")
    b.architect_license = _ask("Architect license #")

    print("\n--- JURISDICTION ---")
    b.site_address          = _ask("Site address")
    b.parcel_number         = _ask("Parcel number")
    b.jurisdiction.country  = _ask("Country", "USA")
    b.jurisdiction.state    = _ask("State (2-letter)", "CA")
    b.jurisdiction.county   = _ask("County")
    b.jurisdiction.city     = _ask("City")
    b.jurisdiction.ibc_edition = _ask("IBC edition", "2021")
    b.jurisdiction.local_amendments = _ask("Local amendments (if any)")

    zoning_opts = [z.value for z in ZoningDistrict]
    b.zoning_district = ZoningDistrict(_choose("Zoning district:", zoning_opts, 0))

    print("\n--- BUILDING CLASSIFICATION ---")
    rc_opts = [r.value for r in RiskCategory]
    b.risk_category = RiskCategory(_choose("Risk Category (IBC Table 1604.5):", rc_opts, 1))

    ct_opts = [c.value for c in ConstructionType]
    b.construction_type = ConstructionType(_choose("Construction Type (IBC Ch. 6):", ct_opts, 8))

    print("\nOccupancy groups (enter codes separated by commas, e.g. B,M or R-2):")
    print("  Options:", ", ".join(og.value for og in OccupancyGroup))
    raw_occ = input("  Occupancy group(s): ").strip().upper()
    for token in raw_occ.split(","):
        token = token.strip()
        try:
            b.occupancy_groups.append(OccupancyGroup(token))
        except ValueError:
            print(f"  [skip] Unknown occupancy group: {token}")

    print("\n--- DIMENSIONS ---")
    b.stories_above_grade   = int(_ask("Stories above grade", "1"))
    b.stories_below_grade   = int(_ask("Stories below grade",  "0"))
    b.building_height_ft    = float(_ask("Building height (ft)", "20"))
    b.total_floor_area_sqft = float(_ask("Total floor area (sq ft)", "2000"))
    b.footprint_sqft        = float(_ask("Footprint area (sq ft)",   "2000"))

    add_rooms = _ask("Add rooms to schedule? (y/n)", "n").lower()
    while add_rooms == "y":
        rname = _ask("  Room name")
        rog   = _ask("  Occupancy group (e.g. B, M, R-2)", "B")
        rarea = float(_ask("  Floor area (sq ft)", "500"))
        rlf   = float(_ask("  Occupant load factor (sf/person; 0 = skip)", "100"))
        try:
            og = OccupancyGroup(rog.upper())
            b.rooms.append(Room(rname, og, rarea, rlf))
        except ValueError:
            print(f"  [skip] Unknown occupancy: {rog}")
        add_rooms = _ask("  Add another room? (y/n)", "n").lower()

    print("\n--- FIRE PROTECTION ---")
    b.sprinkler_system   = _ask("Sprinkler system? (y/n)", "n").lower() == "y"
    if b.sprinkler_system:
        b.sprinkler_standard = _ask("  Sprinkler standard", "NFPA 13")
    b.fire_alarm_system  = _ask("Fire alarm system? (y/n)", "n").lower() == "y"
    if b.fire_alarm_system:
        b.fire_alarm_standard = _ask("  Fire alarm standard", "NFPA 72")

    print("\n--- ACCESSIBILITY ---")
    b.ada_compliant              = _ask("ADA compliant? (y/n)", "y").lower() == "y"
    b.accessible_route           = _ask("Accessible route provided? (y/n)", "y").lower() == "y"
    b.total_parking_spaces       = int(_ask("Total parking spaces", "0"))
    b.accessible_parking_spaces  = int(_ask("Accessible parking spaces", "0"))

    print("\n--- ENERGY ---")
    b.energy_code  = _ask("Energy code (e.g. ASHRAE 90.1-2019)", "IECC 2021")
    b.climate_zone = _ask("Climate zone (e.g. 3B)", "")

    print("\n--- NOTES ---")
    b.special_conditions  = _ask("Special conditions (or leave blank)")
    b.variances_requested = _ask("Variances requested (or leave blank)", "None")

    return b


# ---------------------------------------------------------------------------
# Schema dump helper
# ---------------------------------------------------------------------------

def _dump_schema(output_path: str):
    """Write a blank JSON template the user can fill in and pass to --input."""
    template = {
        "project_name": "",
        "project_number": "",
        "permit_number": "",
        "date_prepared": date.today().isoformat(),
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
        "zoning_district": "R-1",
        "risk_category": "II",
        "construction_type": "V-B",
        "occupancy_groups": ["B"],
        "mixed_occupancy": False,
        "mixed_occupancy_method": "",
        "stories_above_grade": 1,
        "stories_below_grade": 0,
        "building_height_ft": 0,
        "total_floor_area_sqft": 0,
        "footprint_sqft": 0,
        "rooms": [
            {
                "name": "Example Room",
                "occupancy_group": "B",
                "floor_area_sqft": 500,
                "occupant_load_factor": 100
            }
        ],
        "sprinkler_system": False,
        "sprinkler_standard": "",
        "fire_alarm_system": False,
        "fire_alarm_standard": "",
        "ada_compliant": True,
        "accessible_route": True,
        "accessible_parking_spaces": 0,
        "total_parking_spaces": 0,
        "energy_code": "",
        "climate_zone": "",
        "osha_applicable": False,
        "ifc_edition": "2021",
        "additional_codes": [],
        "special_conditions": "",
        "variances_requested": ""
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2)
    print(f"[cv2cc] Blank project template written to: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CV2CC — Code Compliance Verification Form Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--input",       "-i", metavar="FILE",
                        help="JSON project file to load")
    parser.add_argument("--output",      "-o", metavar="FILE",
                        default="output/cv2_form.pdf",
                        help="Output PDF path (default: output/cv2_form.pdf)")
    parser.add_argument("--interactive", "-I", action="store_true",
                        help="Run interactive wizard to enter project data")
    parser.add_argument("--dump-schema", "-s", metavar="FILE",
                        help="Write a blank JSON template to FILE and exit")
    parser.add_argument("--demo",        "-d", action="store_true",
                        help="Generate the built-in demo project (default when no flags given)")
    args = parser.parse_args()

    # Dump blank template
    if args.dump_schema:
        _dump_schema(args.dump_schema)
        sys.exit(0)

    # Load building data
    if args.input:
        print(f"[cv2cc] Loading project from: {args.input}")
        building = _from_json(args.input)
    elif args.interactive:
        building = _interactive_wizard()
    else:
        print("[cv2cc] No input specified -- generating demo project.")
        building = _demo_project()

    # Generate PDF
    print(f"[cv2cc] Generating PDF -> {args.output}")
    out = generate_pdf(building, args.output)
    print(f"[cv2cc] Done!  Form saved to: {out}")


if __name__ == "__main__":
    main()
