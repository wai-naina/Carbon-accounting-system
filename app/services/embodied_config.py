"""
Hard-coded embodied emissions configuration.

Embodied emissions are amortized over the plant lifetime using a fixed
weekly value, independent of actual output or captured CO2.

Source: Carbon Nest LCA Workbook (IPCC 2021 GWP100)
  - Total lifetime embodied:        67,267.5 kgCO₂eq (facility construction:
                                    steel, shipping containers, aluminium,
                                    mild steel, equipment, land use)
  - Lifetime capture (design):      250,000 kg CO₂ (25 t/yr × 10 yr)
  - Plant lifetime:                 10 years
  - Weeks in plant lifetime:        520

  Weekly fixed value: 67,267.5 / 520 = 129.36 kg CO₂eq/week
"""

TOTAL_LIFETIME_EMBODIED_KG = 67_267.5  # kgCO₂eq — from LCA (67.2675 tonnes, facility construction only)
PLANT_LIFETIME_YEARS = 10
WEEKS_IN_PLANT_LIFETIME = 520  # 10 years × 52 weeks


def get_weekly_embodied_kg() -> float:
    """Return the fixed amortized weekly embodied emissions (kg CO2eq).

    This value is constant — it does not vary with actual output,
    captured CO2, or number of cycles in a given week.
    """
    return TOTAL_LIFETIME_EMBODIED_KG / WEEKS_IN_PLANT_LIFETIME if WEEKS_IN_PLANT_LIFETIME > 0 else 0.0


# ── Sorbent degradation emission rates (operational, not embodied) ────────────
# Source: Carbon Nest LCA Workbook (IPCC 2021 GWP100, Contribution Breakdown)
# These are per-unit-of-capture rates applied to actual weekly collected CO2.
# They cover the full upstream lifecycle of PEI and methanol (manufacture,
# preparation, and end-of-life) — not just the physical mass of sorbent lost.
#
#   PEI sorbent:  0.0688 kgCO₂eq / kgCO₂ captured
#   Methanol:     0.0834 kgCO₂eq / kgCO₂ captured
#   Combined:     0.1522 kgCO₂eq / kgCO₂ captured
SORBENT_PEI_RATE: float = 0.0688      # kgCO₂eq per kgCO₂ captured
SORBENT_METHANOL_RATE: float = 0.0834  # kgCO₂eq per kgCO₂ captured


def get_sorbent_degradation_rate() -> float:
    """Return the combined sorbent degradation emission rate (kgCO₂eq per kgCO₂ captured).

    Multiply by actual collected CO2 (kg) to get sorbent-related operational
    emissions for a given period. Covers PEI (0.0688) and methanol (0.0834).
    """
    return SORBENT_PEI_RATE + SORBENT_METHANOL_RATE
