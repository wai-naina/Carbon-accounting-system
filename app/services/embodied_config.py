"""
Hard-coded embodied emissions configuration.

Embodied emissions are calculated using a fixed formula:
  total_embodied = emission_factor × plant_lifetime_years × annual_capture_tonnes
  weekly_embodied = total_embodied / weeks_in_plant_lifetime

Values (as specified):
  - Emission factor: 365.11 kg CO2eq
  - Plant lifetime: 10 years
  - Annual capture: 30 tonnes
  - Weeks in plant lifetime: 520
"""

EMBODIED_EMISSION_FACTOR_KG = 365.11
PLANT_LIFETIME_YEARS = 10
ANNUAL_CAPTURE_TONNES = 30
WEEKS_IN_PLANT_LIFETIME = 520


def get_weekly_embodied_kg() -> float:
    """Return amortized weekly embodied emissions (kg CO2)."""
    total = EMBODIED_EMISSION_FACTOR_KG * PLANT_LIFETIME_YEARS * ANNUAL_CAPTURE_TONNES
    return total / WEEKS_IN_PLANT_LIFETIME if WEEKS_IN_PLANT_LIFETIME > 0 else 0.0
