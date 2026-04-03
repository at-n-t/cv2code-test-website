"""
Compliance checker — validates BuildingData against IBC / ADA / safety codes
and returns a list of findings (passes, warnings, violations).
"""

import json
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Literal

from models.building import BuildingData, OccupancyGroup, ConstructionType

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class Finding:
    level: Literal["PASS", "WARNING", "VIOLATION"]
    code_ref: str
    description: str


def _load(filename: str) -> dict:
    with open(DATA_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def check_compliance(b: BuildingData) -> list[Finding]:
    findings: list[Finding] = []

    _check_risk_category(b, findings)
    _check_height_area(b, findings)
    _check_sprinklers(b, findings)
    _check_occupant_load(b, findings)
    _check_accessibility(b, findings)
    _check_parking(b, findings)
    _check_egress(b, findings)
    _check_codes_adopted(b, findings)

    return findings


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_risk_category(b: BuildingData, findings: list[Finding]):
    """Cross-check occupancy group vs risk category."""
    high_risk_occupancies = {
        OccupancyGroup.H1, OccupancyGroup.H2, OccupancyGroup.H3,
        OccupancyGroup.H4, OccupancyGroup.H5,
    }
    essential_occupancies = {OccupancyGroup.I2, OccupancyGroup.I3}

    for og in b.occupancy_groups:
        if og in high_risk_occupancies and b.risk_category.value not in ("III", "IV"):
            findings.append(Finding(
                "WARNING",
                "IBC Table 1604.5",
                f"Occupancy {og.value} typically requires Risk Category III or IV."
            ))
        if og in essential_occupancies and b.risk_category.value not in ("III", "IV"):
            findings.append(Finding(
                "WARNING",
                "IBC Table 1604.5",
                f"Occupancy {og.value} (institutional/essential) typically requires Risk Category III or IV."
            ))

    findings.append(Finding(
        "PASS",
        "IBC Table 1604.5",
        f"Risk Category {b.risk_category.value} recorded."
    ))


def _check_height_area(b: BuildingData, findings: list[Finding]):
    """Check building height and area against IBC table limits."""
    limits = _load("height_area_limits.json")
    ct_key = b.construction_type.value

    if ct_key not in limits:
        findings.append(Finding(
            "WARNING",
            "IBC Tables 504.3/506.2",
            f"No tabulated height/area data for construction type {ct_key} in reference data."
        ))
        return

    ct_data = limits[ct_key]

    for og in b.occupancy_groups:
        og_key = og.value
        if og_key not in ct_data:
            continue  # not in our sample table; skip rather than false-flag

        entry = ct_data[og_key]

        # Height check
        max_ht = entry.get("height_ft")
        if max_ht != "UL" and isinstance(max_ht, (int, float)):
            if b.building_height_ft > max_ht:
                findings.append(Finding(
                    "VIOLATION",
                    "IBC Table 504.3",
                    f"{og.value} / {ct_key}: building height {b.building_height_ft} ft exceeds "
                    f"maximum {max_ht} ft. Consider upgrading construction type or adding sprinklers."
                ))
            else:
                findings.append(Finding(
                    "PASS",
                    "IBC Table 504.3",
                    f"{og.value} / {ct_key}: height {b.building_height_ft} ft ≤ {max_ht} ft."
                ))

        # Area check
        max_area = entry.get("area_sqft")
        if max_area != "UL" and isinstance(max_area, (int, float)):
            if b.total_floor_area_sqft > max_area:
                findings.append(Finding(
                    "VIOLATION",
                    "IBC Table 506.2",
                    f"{og.value} / {ct_key}: floor area {b.total_floor_area_sqft:,.0f} sq ft exceeds "
                    f"allowable {max_area:,} sq ft per floor. Fire walls, sprinklers, or type upgrade required."
                ))
            else:
                findings.append(Finding(
                    "PASS",
                    "IBC Table 506.2",
                    f"{og.value} / {ct_key}: floor area {b.total_floor_area_sqft:,.0f} sq ft ≤ {max_area:,} sq ft."
                ))

        # Stories check
        max_stories = entry.get("stories")
        if max_stories != "UL" and isinstance(max_stories, int):
            total_stories = b.stories_above_grade + b.stories_below_grade
            if total_stories > max_stories:
                findings.append(Finding(
                    "VIOLATION",
                    "IBC Table 504.4",
                    f"{og.value} / {ct_key}: {total_stories} stories exceeds maximum {max_stories}."
                ))
            else:
                findings.append(Finding(
                    "PASS",
                    "IBC Table 504.4",
                    f"{og.value} / {ct_key}: {total_stories} stories ≤ {max_stories}."
                ))


def _check_sprinklers(b: BuildingData, findings: list[Finding]):
    """Flag missing sprinklers where IBC mandates them."""
    thresholds = _load("safety_codes.json").get("sprinkler_thresholds", {})

    needs_sprinkler = False
    reason = ""

    for og in b.occupancy_groups:
        group_letter = og.value.split("-")[0]  # "A", "R", "H", etc.

        if group_letter == "H":
            needs_sprinkler = True
            reason = f"All H occupancies require NFPA 13 sprinklers (IBC 903.2.5)"
        elif group_letter == "I":
            needs_sprinkler = True
            reason = f"All I occupancies require sprinklers (IBC 903.2.6)"
        elif group_letter == "R":
            needs_sprinkler = True
            reason = f"All R occupancies require sprinklers (IBC 903.2.8)"
        elif group_letter == "A" and b.total_floor_area_sqft > 12000:
            needs_sprinkler = True
            reason = f"A occupancy > 12,000 sq ft requires sprinklers (IBC 903.2.1)"
        elif group_letter == "E" and b.total_floor_area_sqft > 12000:
            needs_sprinkler = True
            reason = f"E occupancy > 12,000 sq ft requires sprinklers (IBC 903.2.3)"

    if b.building_height_ft > 55:
        needs_sprinkler = True
        reason = "High-rise (>55 ft above lowest discharge level) requires sprinklers (IBC 403.3)"

    if needs_sprinkler and not b.sprinkler_system:
        findings.append(Finding("VIOLATION", "IBC 903", reason))
    elif needs_sprinkler and b.sprinkler_system:
        findings.append(Finding("PASS", "IBC 903",
            f"Sprinkler system provided ({b.sprinkler_standard}). Required: {reason}"))
    else:
        findings.append(Finding("PASS", "IBC 903",
            "Sprinkler not mandated by IBC for this occupancy/area combination."))


def _check_occupant_load(b: BuildingData, findings: list[Finding]):
    """Verify occupant load calculations exist for all rooms."""
    factors = _load("occupant_load_factors.json")

    for room in b.rooms:
        og_key = room.occupancy_group.value
        if og_key in factors and factors[og_key]["factor"] > 0:
            expected = math.ceil(room.floor_area_sqft / factors[og_key]["factor"])
            if room.occupant_load != expected:
                findings.append(Finding(
                    "WARNING",
                    "IBC Table 1004.5",
                    f"Room '{room.name}': occupant load {room.occupant_load} may differ from "
                    f"calculated {expected} (area {room.floor_area_sqft} sf ÷ {factors[og_key]['factor']} sf/person)."
                ))
            else:
                findings.append(Finding(
                    "PASS",
                    "IBC Table 1004.5",
                    f"Room '{room.name}': occupant load {room.occupant_load} verified."
                ))

    if b.rooms:
        findings.append(Finding(
            "PASS",
            "IBC 1004",
            f"Total building occupant load: {b.total_occupant_load} persons."
        ))


def _check_accessibility(b: BuildingData, findings: list[Finding]):
    """Basic ADA / IBC Chapter 11 accessibility checks."""
    reqs = _load("accessibility_requirements.json")

    if b.stories_above_grade > 1 and not any(
        og in [OccupancyGroup.R3] for og in b.occupancy_groups
    ):
        # Elevator typically required for multi-story non-R3 buildings
        findings.append(Finding(
            "WARNING",
            "IBC 1104.4",
            f"Building has {b.stories_above_grade} stories above grade. "
            "An accessible route (elevator) is required to all accessible floors (IBC 1104.4)."
        ))
    else:
        findings.append(Finding(
            "PASS",
            "IBC 1104.4",
            "Accessible route requirement reviewed."
        ))

    if b.ada_compliant:
        findings.append(Finding(
            "PASS",
            "ADA 2010 / IBC Ch. 11",
            "Project marked ADA compliant. Verify ICC A117.1 scoping and technical provisions."
        ))
    else:
        findings.append(Finding(
            "VIOLATION",
            "ADA 2010 / IBC Ch. 11",
            "Project not marked ADA compliant. ADA compliance is mandatory for public-use buildings."
        ))


def _check_parking(b: BuildingData, findings: list[Finding]):
    """Verify accessible parking count meets ADA / IBC Table 1106.1."""
    if b.total_parking_spaces == 0:
        return  # No parking provided / not applicable

    reqs = _load("accessibility_requirements.json")
    tiers = reqs["parking"]["tiers"]
    required = 1
    total = b.total_parking_spaces

    for tier in tiers:
        max_t = tier["total_max"]
        req = tier["required_accessible"]
        if isinstance(req, int) and total <= max_t:
            required = req
            break
        elif isinstance(req, str) and "%" in req:
            required = math.ceil(total * 0.02)
            break
        elif isinstance(req, str) and "20 +" in req:
            required = 20 + math.ceil((total - 1000) / 100)
            break

    if b.accessible_parking_spaces < required:
        findings.append(Finding(
            "VIOLATION",
            "IBC Table 1106.1 / ADA 208",
            f"Parking: {b.accessible_parking_spaces} accessible spaces provided; "
            f"{required} required for {total} total spaces."
        ))
    else:
        findings.append(Finding(
            "PASS",
            "IBC Table 1106.1 / ADA 208",
            f"Parking: {b.accessible_parking_spaces} accessible spaces provided "
            f"(minimum {required} required)."
        ))

    # Van-accessible check: 1 per 6 accessible spaces
    van_required = max(1, math.ceil(b.accessible_parking_spaces / 6))
    findings.append(Finding(
        "WARNING",
        "ADA 208.2",
        f"At least {van_required} of the {b.accessible_parking_spaces} accessible space(s) "
        "must be van-accessible (96-inch access aisle)."
    ))


def _check_egress(b: BuildingData, findings: list[Finding]):
    """Basic egress checks — minimum exits, occupant load thresholds."""
    total_load = b.total_occupant_load

    # IBC 1006.3.3: ≥2 exits when occupant load > 49
    if total_load > 49:
        findings.append(Finding(
            "WARNING",
            "IBC 1006.3.3",
            f"Total occupant load {total_load} > 49: minimum 2 exits required from each space/floor."
        ))
    if total_load > 499:
        findings.append(Finding(
            "WARNING",
            "IBC 1006.3.3",
            f"Total occupant load {total_load} > 499: minimum 3 exits required."
        ))
    if total_load > 999:
        findings.append(Finding(
            "WARNING",
            "IBC 1006.3.3",
            f"Total occupant load {total_load} > 999: minimum 4 exits required."
        ))

    if total_load > 0:
        findings.append(Finding(
            "PASS",
            "IBC 1004 / 1006",
            "Egress occupant load reviewed. Verify exit widths per IBC 1005.1."
        ))


def _check_codes_adopted(b: BuildingData, findings: list[Finding]):
    """Cross-check project code editions against state adoption table."""
    if not b.jurisdiction.state:
        findings.append(Finding(
            "WARNING",
            "Jurisdiction",
            "No state specified; cannot verify adopted code edition."
        ))
        return

    adoptions = _load("state_code_adoptions.json")
    state = b.jurisdiction.state.upper()

    if state not in adoptions:
        findings.append(Finding(
            "WARNING",
            "Jurisdiction",
            f"State '{state}' not found in adoption table. Verify local codes manually."
        ))
        return

    entry = adoptions[state]
    adopted_ibc = entry["ibc"]
    adopted_irc = entry["irc"]
    notes = entry.get("notes", "")

    if b.jurisdiction.ibc_edition != adopted_ibc:
        findings.append(Finding(
            "WARNING",
            "State Code Adoption",
            f"{entry['name']}: project uses IBC {b.jurisdiction.ibc_edition}; "
            f"state adopts IBC {adopted_ibc}. Confirm with AHJ."
        ))
    else:
        findings.append(Finding(
            "PASS",
            "State Code Adoption",
            f"{entry['name']}: IBC {b.jurisdiction.ibc_edition} matches state adoption."
        ))

    if notes:
        findings.append(Finding(
            "WARNING",
            "State Code Notes",
            f"{entry['name']} code note: {notes}"
        ))
