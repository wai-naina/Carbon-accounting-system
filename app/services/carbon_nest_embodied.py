"""Carbon Nest embodied emissions — output-based per-tonne driver method.

Source: Carbon_Nest_LCA_v0.6_split.xlsx (IPCC 2021 GWP100 / ecoinvent 3.12,
Isometric DAC Protocol v1.3 structure), sheets LCA CALC / DASHBOARD / MATERIALS.
Nelion x4 fleet baseline (Nelion 2 bill of materials scaled to all 4 units).

Unlike the legacy Miniplant 2.0 model (a fixed weekly ramp-up charge,
independent of output — see embodied_config.py), Carbon Nest embodied
emissions are charged as kg CO2-eq per tonne of CO2 actually captured that
week. This is standard functional-unit amortization: the per-tonne rate
already assumes the full 4-Nelion lifetime capture as its denominator, so
multiplying it by *actual* captured CO2 naturally scales down while only
part of the fleet is deployed, and ramps up as more Nelions come online and
cumulative output grows — no separate partial-fleet discount is needed.

Two embodied pools are tracked, mirroring the existing infrastructure/sorbent
split used elsewhere in the CAS:

  - Infrastructure (one-time capital): structural materials & infrastructure
    + equipment (machinery) + land use change.
  - Sorbent (production/replenishment chain): sorbent production +
    sorbent transportation + sorbent processing (direct process CO2, HQ prep
    energy, residual end-of-life).

The LCA's "Energy" driver (1,085.34 kg CO2-eq/t) is deliberately excluded
here — CAS already computes operational emissions from actual metered
Carbon Nest energy (Fans/CT/CT Pump/VP402/VP501/Boiler A/B/Main Utility)
times the grid emission factor, which is more accurate for a live plant than
the LCA's modeled average. Charging both would double-count energy.
"""

from __future__ import annotations

from typing import Dict, List, TypedDict


class DriverIntensity(TypedDict):
    label: str
    kg_co2_per_tonne: float
    pool: str  # "infrastructure" | "sorbent" | "energy" (excluded from CAS charges)
    data_quality: str
    note: str


# All figures: kg CO2-eq per gross tonne CO2 captured. LCA CALC!C7:C13, v0.6.
DRIVER_INTENSITIES: List[DriverIntensity] = [
    {
        "label": "Sorbent production",
        "kg_co2_per_tonne": 39.618670902332894,
        "pool": "sorbent",
        "data_quality": "Measured",
        "note": "Support once + PEI/methanol per functionalization, amortized",
    },
    {
        "label": "Sorbent transportation",
        "kg_co2_per_tonne": 3.9224986737506726,
        "pool": "sorbent",
        "data_quality": "Measured",
        "note": "Shipping + trucking for sorbent chain materials",
    },
    {
        "label": "Sorbent processing",
        "kg_co2_per_tonne": 10.505116320045099,
        "pool": "sorbent",
        "data_quality": "Measured + Placeholder",
        "note": (
            "Fossil CO2 from PEI burn-off (2.04 kg/kg) and lost methanol (1.37 kg/kg) "
            "+ oven/incinerator electricity at HQ grid EF + support landfill "
            "(incinerator energy is a 300 kWh placeholder)"
        ),
    },
    {
        "label": "Structural materials & infrastructure",
        "kg_co2_per_tonne": 193.51376296516094,
        "pool": "infrastructure",
        "data_quality": "Measured",
        "note": "Nelion x4 + BOP + site, incl. transport & EoL",
    },
    {
        "label": "Equipment (machinery)",
        "kg_co2_per_tonne": 10.049237452307475,
        "pool": "infrastructure",
        "data_quality": "Mixed (datasheet + placeholder weights)",
        "note": "Amortized over plant life (basis 1: full embodied over plant life)",
    },
    {
        "label": "Land use change",
        "kg_co2_per_tonne": 14.292772593757523,
        "pool": "infrastructure",
        "data_quality": "Measured",
        "note": "Carbon stock loss (1.0117 ha shrubland, IPCC Tier 1) + conversion machinery",
    },
    {
        "label": "Energy",
        "kg_co2_per_tonne": 1085.338539544387,
        "pool": "energy",
        "data_quality": "Modeled (LCA average)",
        "note": (
            "Excluded from CAS embodied charges — operational emissions are computed "
            "from actual metered Carbon Nest energy instead (see carbon_nest_calculations.py)"
        ),
    },
]

LCA_SOURCE_LABEL = "Carbon Nest LCA v0.6 (Nelion x4 fleet baseline)"


def _sum_pool(pool: str) -> float:
    return sum(d["kg_co2_per_tonne"] for d in DRIVER_INTENSITIES if d["pool"] == pool)


INFRASTRUCTURE_INTENSITY_KG_PER_TONNE = _sum_pool("infrastructure")
SORBENT_INTENSITY_KG_PER_TONNE = _sum_pool("sorbent")
NON_ENERGY_INTENSITY_KG_PER_TONNE = INFRASTRUCTURE_INTENSITY_KG_PER_TONNE + SORBENT_INTENSITY_KG_PER_TONNE


def get_infrastructure_intensity_kg_per_tonne() -> float:
    """kg CO2-eq per tonne captured for structural + equipment + land use."""
    return INFRASTRUCTURE_INTENSITY_KG_PER_TONNE


def get_sorbent_intensity_kg_per_tonne() -> float:
    """kg CO2-eq per tonne captured for sorbent production + transport + processing."""
    return SORBENT_INTENSITY_KG_PER_TONNE


def calculate_embodied_kg(captured_co2_kg: float) -> Dict[str, float]:
    """Return (infrastructure_kg, sorbent_kg, total_kg) embodied charge for a period.

    `captured_co2_kg` is the actual gross CO2 captured in that period
    (liquefied if available, otherwise collected/bag), matching how
    Miniplant's calculate_weekly_metrics() defines gross_captured_kg.
    """
    tonnes = max(captured_co2_kg, 0.0) / 1000.0
    infra = tonnes * INFRASTRUCTURE_INTENSITY_KG_PER_TONNE
    sorbent = tonnes * SORBENT_INTENSITY_KG_PER_TONNE
    return {
        "infrastructure_embodied_kg": infra,
        "sorbent_embodied_kg": sorbent,
        "total_embodied_emissions_kg": infra + sorbent,
    }


def get_driver_breakdown() -> List[DriverIntensity]:
    """Full driver-by-driver breakdown for the embodied emissions visualization."""
    return DRIVER_INTENSITIES
