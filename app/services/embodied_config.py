"""
Hard-coded embodied emissions configuration.

Embodied emissions are amortized over a ramp-up phase using a fixed
weekly value, independent of actual output or captured CO2.

Source: Carbon Nest LCA Workbook (IPCC 2021 GWP100)
  - Total lifetime embodied:        67,267.5 kgCO₂eq (facility construction:
                                    steel, shipping containers, aluminium,
                                    mild steel, equipment, land use)
  - Lifetime capture (design):      250,000 kg CO₂ (25 t/yr × 10 yr)
  - Plant lifetime:                 10 years

Ramp-up phase adjustment (current):
  The plant is in an early ramp-up phase and is not yet operating at full
  design capacity. Only 35% of total lifetime embodied emissions are
  allocated to this phase, amortized over 5 years.

  - Ramp-up fraction:               26%
  - Ramp-up embodied total:         67,267.5 × 0.26 = 17,489.6 kgCO₂eq
  - Ramp-up period:                 5 years = 260 weeks
  - Weekly ramp-up value:           17,489.6 / 260 = 67.27 kg CO₂eq/week

  (Full-scale reference: 67,267.5 / 520 = 129.36 kg CO₂eq/week)
"""

TOTAL_LIFETIME_EMBODIED_KG = 67_267.5   # kgCO₂eq — from LCA (67.2675 tonnes, facility construction only)
PLANT_LIFETIME_YEARS = 10
WEEKS_IN_PLANT_LIFETIME = 520           # 10 years × 52 weeks

# Ramp-up phase parameters
RAMP_UP_FRACTION = 0.26                 # 26% of total embodied allocated to ramp-up phase
RAMP_UP_YEARS = 5
RAMP_UP_WEEKS = RAMP_UP_YEARS * 52     # 260 weeks
RAMP_UP_EMBODIED_KG = TOTAL_LIFETIME_EMBODIED_KG * RAMP_UP_FRACTION  # 23,543.6 kg


def get_weekly_embodied_kg() -> float:
    """Return the fixed amortized weekly embodied emissions (kg CO2eq).

    Currently reflects the ramp-up phase: 26% of total lifetime embodied
    emissions spread over 5 years (260 weeks) = 67.27 kg/week.

    This value is constant — it does not vary with actual output,
    captured CO2, or number of cycles in a given week.
    """
    return RAMP_UP_EMBODIED_KG / RAMP_UP_WEEKS if RAMP_UP_WEEKS > 0 else 0.0


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
