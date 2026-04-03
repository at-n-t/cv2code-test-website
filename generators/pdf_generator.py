"""
PDF form generator for CV2 Code Compliance form.
Uses ReportLab to produce a multi-page, fully filled PDF.
"""

from pathlib import Path
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from models.building import BuildingData
from generators.compliance_checker import check_compliance, Finding


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
DARK_BLUE   = colors.HexColor("#1A3557")
MID_BLUE    = colors.HexColor("#2563A8")
LIGHT_BLUE  = colors.HexColor("#D6E4F0")
ACCENT      = colors.HexColor("#F4A020")
PASS_GREEN  = colors.HexColor("#1E7A3A")
WARN_ORANGE = colors.HexColor("#C45E00")
FAIL_RED    = colors.HexColor("#C0202A")
LIGHT_GRAY  = colors.HexColor("#F2F2F2")
MID_GRAY    = colors.HexColor("#AAAAAA")


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------

def _styles():
    ss = getSampleStyleSheet()

    def _add(name, **kw):
        if name not in ss:
            ss.add(ParagraphStyle(name=name, **kw))
        return ss[name]

    _add("FormTitle",
         fontName="Helvetica-Bold", fontSize=18,
         textColor=DARK_BLUE, alignment=TA_CENTER, spaceAfter=4)
    _add("FormSubtitle",
         fontName="Helvetica", fontSize=10,
         textColor=MID_BLUE, alignment=TA_CENTER, spaceAfter=10)
    _add("SectionHeader",
         fontName="Helvetica-Bold", fontSize=11,
         textColor=colors.white, spaceBefore=12, spaceAfter=4)
    _add("FieldLabel",
         fontName="Helvetica-Bold", fontSize=8,
         textColor=colors.HexColor("#555555"), spaceBefore=2)
    _add("FieldValue",
         fontName="Helvetica", fontSize=9,
         textColor=colors.black, spaceAfter=2)
    _add("FindingPass",
         fontName="Helvetica", fontSize=8,
         textColor=PASS_GREEN, spaceAfter=2, leftIndent=6)
    _add("FindingWarn",
         fontName="Helvetica", fontSize=8,
         textColor=WARN_ORANGE, spaceAfter=2, leftIndent=6)
    _add("FindingFail",
         fontName="Helvetica-Bold", fontSize=8,
         textColor=FAIL_RED, spaceAfter=2, leftIndent=6)
    _add("FooterStyle",
         fontName="Helvetica", fontSize=7,
         textColor=MID_GRAY, alignment=TA_CENTER)
    _add("SmallNote",
         fontName="Helvetica-Oblique", fontSize=7,
         textColor=MID_GRAY, spaceAfter=4)
    return ss


# ---------------------------------------------------------------------------
# Layout utilities
# ---------------------------------------------------------------------------

def _section_header(title: str, ss) -> list:
    """Returns a shaded header row."""
    tbl = Table([[Paragraph(f"  {title}", ss["SectionHeader"])]],
                colWidths=["100%"])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    return [tbl, Spacer(1, 4)]


def _field_row(label: str, value: str, ss,
               col_widths=(2.0*inch, 4.5*inch)) -> Table:
    """Single label-value row."""
    val = value if value else "—"
    tbl = Table(
        [[Paragraph(label, ss["FieldLabel"]),
          Paragraph(val,   ss["FieldValue"])]],
        colWidths=col_widths,
    )
    tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, MID_GRAY),
    ]))
    return tbl


def _two_col(pairs: list[tuple[str, str]], ss,
             col_widths=(1.5*inch, 1.8*inch, 1.5*inch, 1.7*inch)) -> Table:
    """Two side-by-side label+value pairs."""
    row = [
        Paragraph(pairs[0][0], ss["FieldLabel"]),
        Paragraph(pairs[0][1] or "—", ss["FieldValue"]),
        Paragraph(pairs[1][0], ss["FieldLabel"]),
        Paragraph(pairs[1][1] or "—", ss["FieldValue"]),
    ]
    tbl = Table([row], colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, MID_GRAY),
    ]))
    return tbl


def _finding_paragraph(f: Finding, ss) -> Paragraph:
    icons = {"PASS": "✔", "WARNING": "⚠", "VIOLATION": "✘"}
    style_map = {"PASS": "FindingPass", "WARNING": "FindingWarn", "VIOLATION": "FindingFail"}
    icon = icons.get(f.level, "•")
    text = f"<b>{icon} [{f.code_ref}]</b>  {f.description}"
    return Paragraph(text, ss[style_map[f.level]])


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_pdf(building: BuildingData, output_path: str) -> str:
    """
    Generate a CV2 Code Compliance form PDF.

    Args:
        building:    Populated BuildingData instance.
        output_path: Destination file path (will be created/overwritten).

    Returns:
        Absolute path to the generated PDF.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.75*inch,
        rightMargin=0.75*inch,
        topMargin=0.85*inch,
        bottomMargin=0.75*inch,
        title=f"CV2 Form — {building.project_name}",
        author=building.prepared_by,
        subject="Code Compliance Verification Form (CV2)",
    )

    ss = _styles()
    story = []

    # -----------------------------------------------------------------------
    # Header / title block
    # -----------------------------------------------------------------------
    story.append(Paragraph("CODE COMPLIANCE VERIFICATION — CV2 FORM", ss["FormTitle"]))
    story.append(Paragraph(
        "International Building Code (IBC) · ADA · NFPA · Universal Safety Codes",
        ss["FormSubtitle"],
    ))
    story.append(HRFlowable(width="100%", thickness=2, color=ACCENT))
    story.append(Spacer(1, 8))

    # -----------------------------------------------------------------------
    # Section 1 — Project Identification
    # -----------------------------------------------------------------------
    story += _section_header("1 · PROJECT IDENTIFICATION", ss)
    story.append(_field_row("Project Name:",   building.project_name,   ss))
    story.append(_field_row("Project Number:", building.project_number, ss))
    story.append(_field_row("Permit Number:",  building.permit_number,  ss))
    story.append(_two_col(
        [("Date Prepared:", building.date_prepared),
         ("Prepared By:",   building.prepared_by)], ss))
    story.append(_two_col(
        [("Architect License:", building.architect_license),
         ("Engineer License:",  building.engineer_license)], ss))
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 2 — Site / Jurisdiction
    # -----------------------------------------------------------------------
    story += _section_header("2 · SITE & JURISDICTION", ss)
    j = building.jurisdiction
    story.append(_field_row("Site Address:", building.site_address, ss))
    story.append(_field_row("Parcel Number:", building.parcel_number, ss))
    story.append(_two_col(
        [("City:", j.city), ("County:", j.county)], ss))
    story.append(_two_col(
        [("State:", j.state), ("Country:", j.country)], ss))
    story.append(_two_col(
        [("IBC Edition:", j.ibc_edition), ("IRC Edition:", j.irc_edition)], ss))
    story.append(_two_col(
        [("IFC Edition:", building.ifc_edition),
         ("NFPA Edition:", j.nfpa_edition)], ss))
    story.append(_field_row("Local Amendments:", j.local_amendments, ss))
    story.append(_field_row("Zoning District:",  building.zoning_district.value, ss))
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 3 — Building Classification
    # -----------------------------------------------------------------------
    story += _section_header("3 · BUILDING CLASSIFICATION", ss)

    # Risk category summary table
    rc_descriptions = {
        "I":   "Low hazard — minor storage, agriculture, temporary facilities",
        "II":  "Normal hazard — most buildings not in other categories",
        "III": "Substantial hazard — schools, assembly >300 occ., healthcare",
        "IV":  "Essential facilities — hospitals, fire stations, emergency ops",
    }
    rc = building.risk_category
    story.append(_field_row("Risk Category:",
        f"{rc.value}  —  {rc_descriptions.get(rc.value, '')}", ss))

    story.append(_field_row("Construction Type:",
        building.construction_type.value
        + "  (" + _construction_type_desc(building.construction_type.value) + ")", ss))

    occ_str = ",  ".join(og.value for og in building.occupancy_groups) or "—"
    story.append(_field_row("Occupancy Group(s):", occ_str, ss))

    if building.mixed_occupancy:
        story.append(_field_row("Mixed Occupancy Method:",
            building.mixed_occupancy_method, ss))

    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 4 — Building Dimensions
    # -----------------------------------------------------------------------
    story += _section_header("4 · BUILDING DIMENSIONS & ROOM SIZING", ss)
    story.append(_two_col(
        [("Stories Above Grade:", str(building.stories_above_grade)),
         ("Stories Below Grade:", str(building.stories_below_grade))], ss))
    story.append(_two_col(
        [("Building Height:", f"{building.building_height_ft} ft"),
         ("Footprint Area:", f"{building.footprint_sqft:,.0f} sq ft")], ss))
    story.append(_field_row("Total Floor Area:",
        f"{building.total_floor_area_sqft:,.0f} sq ft", ss))

    if building.rooms:
        story.append(Spacer(1, 6))
        story.append(Paragraph("  Room Schedule  (IBC Table 1004.5 Occupant Loads)", ss["FieldLabel"]))
        story.append(Spacer(1, 3))

        room_header = ["Room / Space", "Occupancy", "Area (sq ft)", "Load Factor", "Occ. Load"]
        room_rows = [room_header]
        for rm in building.rooms:
            lf = f"{rm.occupant_load_factor:.0f} sf/person" if rm.occupant_load_factor else "N/A"
            room_rows.append([
                rm.name,
                rm.occupancy_group.value,
                f"{rm.floor_area_sqft:,.0f}",
                lf,
                str(rm.occupant_load),
            ])
        room_rows.append(["TOTAL", "", f"{building.total_floor_area_sqft:,.0f}",
                           "", str(building.total_occupant_load)])

        room_tbl = Table(room_rows, colWidths=[2.3*inch, 0.8*inch, 1.1*inch, 1.1*inch, 0.9*inch])
        room_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  DARK_BLUE),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("BACKGROUND",    (0, -1), (-1, -1), LIGHT_BLUE),
            ("FONTNAME",      (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, LIGHT_GRAY]),
            ("ALIGN",         (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",          (0, 0), (-1, -1), 0.3, MID_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ]))
        story.append(room_tbl)

    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 5 — Fire Protection
    # -----------------------------------------------------------------------
    story += _section_header("5 · FIRE PROTECTION SYSTEMS", ss)
    story.append(_two_col(
        [("Sprinkler System:", "Yes" if building.sprinkler_system else "No"),
         ("Standard:", building.sprinkler_standard or "N/A")], ss))
    story.append(_two_col(
        [("Fire Alarm System:", "Yes" if building.fire_alarm_system else "No"),
         ("Standard:", building.fire_alarm_standard or "N/A")], ss))
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 6 — Accessibility
    # -----------------------------------------------------------------------
    story += _section_header("6 · ACCESSIBILITY (ADA / IBC Ch. 11 / ICC A117.1)", ss)
    story.append(_two_col(
        [("ADA Compliant:", "Yes" if building.ada_compliant else "NO"),
         ("Accessible Route:", "Yes" if building.accessible_route else "NO")], ss))
    story.append(_two_col(
        [("Total Parking Spaces:", str(building.total_parking_spaces)),
         ("Accessible Spaces:", str(building.accessible_parking_spaces))], ss))
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 7 — Energy / Environmental
    # -----------------------------------------------------------------------
    story += _section_header("7 · ENERGY & ENVIRONMENTAL CODES", ss)
    story.append(_two_col(
        [("Energy Code:", building.energy_code or "Not specified"),
         ("Climate Zone:", building.climate_zone or "Not specified")], ss))
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 8 — Universal / Safety Codes Referenced
    # -----------------------------------------------------------------------
    story += _section_header("8 · UNIVERSAL & SAFETY CODES REFERENCED", ss)
    codes = [
        f"IBC {j.ibc_edition}", f"IFC {building.ifc_edition}",
        f"NFPA 72 ({j.nfpa_edition})", "ADA 2010 Standards",
        "ICC A117.1-2017", "ASCE 7", "IECC / ASHRAE 90.1",
    ]
    if building.osha_applicable:
        codes.append("OSHA 29 CFR 1926 (Construction)")
    if building.sprinkler_system and building.sprinkler_standard:
        codes.append(building.sprinkler_standard)
    codes.extend(building.additional_codes)

    code_rows = [[Paragraph(f"• {c}", ss["FieldValue"]) for c in codes[i:i+3]]
                 for i in range(0, len(codes), 3)]
    if code_rows:
        code_tbl = Table(code_rows, colWidths=[2.1*inch, 2.1*inch, 2.1*inch])
        code_tbl.setStyle(TableStyle([
            ("VALIGN",     (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(code_tbl)
    story.append(Spacer(1, 6))

    # -----------------------------------------------------------------------
    # Section 9 — Compliance Findings
    # -----------------------------------------------------------------------
    story += _section_header("9 · AUTOMATED COMPLIANCE FINDINGS", ss)
    story.append(Paragraph(
        "The following findings are generated automatically from the data above. "
        "All items must be verified by the licensed design professional of record.",
        ss["SmallNote"],
    ))

    findings = check_compliance(building)

    passes    = [f for f in findings if f.level == "PASS"]
    warnings  = [f for f in findings if f.level == "WARNING"]
    violations = [f for f in findings if f.level == "VIOLATION"]

    # Summary bar
    summary_data = [[
        Paragraph(f"<b>✔ {len(passes)} PASS</b>",      ParagraphStyle("sp", fontName="Helvetica-Bold", fontSize=9, textColor=PASS_GREEN)),
        Paragraph(f"<b>⚠ {len(warnings)} WARNING</b>",  ParagraphStyle("sw", fontName="Helvetica-Bold", fontSize=9, textColor=WARN_ORANGE)),
        Paragraph(f"<b>✘ {len(violations)} VIOLATION</b>", ParagraphStyle("sv", fontName="Helvetica-Bold", fontSize=9, textColor=FAIL_RED)),
    ]]
    summary_tbl = Table(summary_data, colWidths=[2.0*inch, 2.0*inch, 2.5*inch])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX",        (0, 0), (-1, -1), 0.5, MID_GRAY),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 6))

    if violations:
        story.append(Paragraph("<b>VIOLATIONS — Must be resolved before permit issuance:</b>",
                                ss["FindingFail"]))
        for f in violations:
            story.append(_finding_paragraph(f, ss))
        story.append(Spacer(1, 4))

    if warnings:
        story.append(Paragraph("<b>WARNINGS — Review and document resolution:</b>",
                                ss["FindingWarn"]))
        for f in warnings:
            story.append(_finding_paragraph(f, ss))
        story.append(Spacer(1, 4))

    story.append(Paragraph("<b>PASSING ITEMS:</b>", ss["FindingPass"]))
    for f in passes:
        story.append(_finding_paragraph(f, ss))

    story.append(Spacer(1, 8))

    # -----------------------------------------------------------------------
    # Section 10 — Special Conditions & Variances
    # -----------------------------------------------------------------------
    story += _section_header("10 · SPECIAL CONDITIONS & VARIANCES", ss)
    story.append(_field_row("Special Conditions:", building.special_conditions, ss))
    story.append(_field_row("Variances Requested:", building.variances_requested, ss))
    story.append(Spacer(1, 8))

    # -----------------------------------------------------------------------
    # Section 11 — Signature Block
    # -----------------------------------------------------------------------
    story += _section_header("11 · CERTIFICATION", ss)
    story.append(Paragraph(
        "I hereby certify that the information contained in this form is accurate and "
        "complete to the best of my knowledge, and that this project has been designed "
        "in conformance with the codes and standards listed above.",
        ss["FieldValue"],
    ))
    story.append(Spacer(1, 20))

    sig_data = [
        ["Design Professional of Record", "", "Date"],
        ["", "", ""],
        ["Print Name / License No.", "", "AHJ Reviewer"],
    ]
    sig_tbl = Table(sig_data, colWidths=[3.0*inch, 0.5*inch, 3.0*inch])
    sig_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("TEXTCOLOR",     (0, 0), (-1, -1), colors.HexColor("#555555")),
        ("LINEABOVE",     (0, 1), (0, 1), 0.5, colors.black),
        ("LINEABOVE",     (2, 1), (2, 1), 0.5, colors.black),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
    ]))
    story.append(sig_tbl)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GRAY))
    story.append(Paragraph(
        f"Generated by CV2CC — Code Compliance Form Generator  ·  {date.today().isoformat()}  ·  "
        "For official use this form must be reviewed and sealed by the design professional of record.",
        ss["FooterStyle"],
    ))

    doc.build(story)
    return str(output.resolve())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _construction_type_desc(ct: str) -> str:
    desc = {
        "I-A":   "Non-combustible, fully fire-resistive — highest protection",
        "I-B":   "Non-combustible, fire-resistive",
        "II-A":  "Non-combustible, protected",
        "II-B":  "Non-combustible, unprotected",
        "III-A": "Exterior non-combustible, interior combustible, protected",
        "III-B": "Exterior non-combustible, interior combustible, unprotected",
        "IV":    "Heavy timber",
        "V-A":   "Combustible, protected",
        "V-B":   "Combustible, unprotected — least protection",
    }
    return desc.get(ct, "")
