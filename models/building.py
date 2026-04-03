"""
Building data models for CV2 form generation.
Follows IBC (International Building Code) classifications.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class RiskCategory(str, Enum):
    """IBC Table 1604.5 Risk Categories."""
    I   = "I"    # Low hazard: agricultural, minor storage
    II  = "II"   # Normal: most buildings
    III = "III"  # Substantial hazard: schools, assembly >300, healthcare
    IV  = "IV"   # Essential facilities: hospitals, fire stations, emergency ops


class ConstructionType(str, Enum):
    """IBC Chapter 6 Construction Types."""
    IA  = "I-A"   # Non-combustible, fire-resistive (highest)
    IB  = "I-B"   # Non-combustible, fire-resistive
    IIA = "II-A"  # Non-combustible, protected
    IIB = "II-B"  # Non-combustible, unprotected
    IIIA = "III-A" # Exterior non-combustible, interior combustible, protected
    IIIB = "III-B" # Exterior non-combustible, interior combustible, unprotected
    IV  = "IV"    # Heavy timber
    VA  = "V-A"   # Combustible, protected
    VB  = "V-B"   # Combustible, unprotected (lowest)


class OccupancyGroup(str, Enum):
    """IBC Chapter 3 Occupancy Classifications."""
    A1  = "A-1"   # Assembly: theaters, concert halls
    A2  = "A-2"   # Assembly: restaurants, nightclubs
    A3  = "A-3"   # Assembly: churches, gyms, libraries
    A4  = "A-4"   # Assembly: arenas, bleachers
    A5  = "A-5"   # Assembly: outdoor stadiums
    B   = "B"     # Business: offices, banks
    E   = "E"     # Educational: schools K-12
    F1  = "F-1"   # Factory: moderate hazard
    F2  = "F-2"   # Factory: low hazard
    H1  = "H-1"   # High hazard: detonable
    H2  = "H-2"   # High hazard: deflagration
    H3  = "H-3"   # High hazard: physical hazard
    H4  = "H-4"   # High hazard: health hazard
    H5  = "H-5"   # High hazard: HPM
    I1  = "I-1"   # Institutional: assisted living
    I2  = "I-2"   # Institutional: hospitals, nursing homes
    I3  = "I-3"   # Institutional: detention/correctional
    I4  = "I-4"   # Institutional: day care
    M   = "M"     # Mercantile: retail stores
    R1  = "R-1"   # Residential: hotels, motels
    R2  = "R-2"   # Residential: apartments
    R3  = "R-3"   # Residential: one/two family dwellings
    R4  = "R-4"   # Residential: care facilities ≤16 occupants
    S1  = "S-1"   # Storage: moderate hazard
    S2  = "S-2"   # Storage: low hazard (parking garages)
    U   = "U"     # Utility: barns, carports


class ZoningDistrict(str, Enum):
    """Common municipal zoning districts."""
    R1  = "R-1"   # Single-family residential
    R2  = "R-2"   # Two-family residential
    R3  = "R-3"   # Multi-family residential
    C1  = "C-1"   # Neighborhood commercial
    C2  = "C-2"   # General commercial
    C3  = "C-3"   # Highway commercial
    I1  = "I-1"   # Light industrial
    I2  = "I-2"   # Heavy industrial
    A   = "A"     # Agricultural
    MX  = "MX"    # Mixed use
    PD  = "PD"    # Planned development
    OS  = "OS"    # Open space / parks


@dataclass
class Jurisdiction:
    """Identifies the governing jurisdiction for code compliance."""
    country: str = "USA"
    state: str = ""
    county: str = ""
    city: str = ""
    # Adopted code editions (leave blank to use defaults)
    ibc_edition: str = "2021"
    irc_edition: str = "2021"
    nfpa_edition: str = "2021"
    local_amendments: str = ""


@dataclass
class Room:
    """Individual room definition with sizing and occupancy load."""
    name: str = ""
    occupancy_group: OccupancyGroup = OccupancyGroup.B
    floor_area_sqft: float = 0.0
    occupant_load_factor: float = 0.0   # sqft per person (IBC Table 1004.5)
    # Computed field
    occupant_load: int = field(default=0, init=False)

    def __post_init__(self):
        if self.occupant_load_factor > 0 and self.floor_area_sqft > 0:
            self.occupant_load = int(self.floor_area_sqft / self.occupant_load_factor)


@dataclass
class BuildingData:
    """Complete building data for CV2 form generation."""

    # --- Project identification ---
    project_name: str = ""
    project_number: str = ""
    permit_number: str = ""
    date_prepared: str = ""
    prepared_by: str = ""
    architect_license: str = ""
    engineer_license: str = ""

    # --- Location ---
    site_address: str = ""
    parcel_number: str = ""
    jurisdiction: Jurisdiction = field(default_factory=Jurisdiction)
    zoning_district: ZoningDistrict = ZoningDistrict.R1

    # --- Building classification ---
    risk_category: RiskCategory = RiskCategory.II
    construction_type: ConstructionType = ConstructionType.VB
    occupancy_groups: list[OccupancyGroup] = field(default_factory=list)
    mixed_occupancy: bool = False
    mixed_occupancy_method: str = ""  # "Separated" or "Non-Separated"

    # --- Building dimensions ---
    stories_above_grade: int = 1
    stories_below_grade: int = 0
    building_height_ft: float = 0.0
    total_floor_area_sqft: float = 0.0
    footprint_sqft: float = 0.0
    rooms: list[Room] = field(default_factory=list)

    # --- Fire protection ---
    sprinkler_system: bool = False
    sprinkler_standard: str = ""   # e.g. "NFPA 13", "NFPA 13R", "NFPA 13D"
    fire_alarm_system: bool = False
    fire_alarm_standard: str = ""  # e.g. "NFPA 72"

    # --- Accessibility ---
    ada_compliant: bool = True
    accessible_route: bool = True
    accessible_parking_spaces: int = 0
    total_parking_spaces: int = 0

    # --- Energy / environmental ---
    energy_code: str = ""   # e.g. "ASHRAE 90.1-2019", "IECC 2021"
    climate_zone: str = ""  # e.g. "3B", "5A"

    # --- Universal / safety codes ---
    osha_applicable: bool = False
    ifc_edition: str = "2021"   # International Fire Code
    additional_codes: list[str] = field(default_factory=list)

    # --- Notes ---
    special_conditions: str = ""
    variances_requested: str = ""

    @property
    def total_occupant_load(self) -> int:
        return sum(r.occupant_load for r in self.rooms)
