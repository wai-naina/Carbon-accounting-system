from __future__ import annotations

from typing import Dict, Optional

from app.services.carbon_nest_embodied import calculate_embodied_kg


def safe_value(value: Optional[float]) -> float:
    return float(value or 0)


SERIES_LABELS = {
    "1n3": "Series 1 & 3",
    "2n4": "Series 2 & 4",
}


def get_series_display_name(series: Optional[str]) -> str:
    if series in SERIES_LABELS:
        return SERIES_LABELS[series]
    return series or "Unknown"


def calculate_weekly_metrics(
    *,
    ads_co2_kg: float,
    des_co2_kg: float,
    bag_co2_kg: float,
    liquefied_co2_kg: float,
    thermal_energy_kwh: float,
    auxiliary_energy_kwh: float,
    total_energy_kwh: float,
    process_energy_kwh: Optional[float] = None,
    steam_kg: float,
    grid_ef: float,
) -> Dict[str, Optional[float]]:
    """Carbon Nest weekly metrics.

    Operational emissions come from actual metered energy (Fans, CT, CT Pump,
    VP402, VP501, Boiler A/B, Main Utility) x grid EF. Embodied emissions are
    output-based: kg CO2-eq/t driver intensities from the v0.6 LCA applied to
    the CO2 actually captured this week (see carbon_nest_embodied.py).

    Energy intensity uses `process_energy_kwh` (Fans/CT/CT Pump/VP402/VP501/
    Boiler A/B only) rather than `total_energy_kwh`, so it matches SCADA's own
    "MWh/tCO2" convention: Main Utility and liquefaction energy are real
    energy (and count toward operational emissions) but are excluded from the
    per-cycle efficiency figure the plant already reports. Falls back to
    total_energy_kwh if process_energy_kwh isn't provided.
    """
    if process_energy_kwh is None:
        process_energy_kwh = total_energy_kwh
    loss_stage_1 = ads_co2_kg - des_co2_kg  # Adsorbed -> Desorbed
    loss_stage_2 = des_co2_kg - bag_co2_kg  # Desorbed -> Collected (Bag)

    if liquefied_co2_kg > 0:
        loss_stage_3 = bag_co2_kg - liquefied_co2_kg
        gross_captured = liquefied_co2_kg
    else:
        loss_stage_3 = 0
        gross_captured = bag_co2_kg

    total_loss = ads_co2_kg - gross_captured

    thermal_emissions = thermal_energy_kwh * grid_ef
    auxiliary_emissions = auxiliary_energy_kwh * grid_ef
    total_operational_emissions = total_energy_kwh * grid_ef

    embodied = calculate_embodied_kg(gross_captured)
    total_embodied = embodied["total_embodied_emissions_kg"]
    total_emissions = total_operational_emissions + total_embodied

    net_removal = gross_captured - total_emissions

    energy_intensity = None
    co2_for_intensity = liquefied_co2_kg if liquefied_co2_kg > 0 else bag_co2_kg
    if co2_for_intensity > 0 and process_energy_kwh > 0:
        energy_intensity = process_energy_kwh / (co2_for_intensity / 1000)

    return {
        "loss_stage_1_kg": loss_stage_1,
        "loss_stage_2_kg": loss_stage_2,
        "loss_stage_3_kg": loss_stage_3,
        "total_loss_kg": total_loss,
        "thermal_emissions_kg": thermal_emissions,
        "auxiliary_emissions_kg": auxiliary_emissions,
        "total_operational_emissions_kg": total_operational_emissions,
        "infrastructure_embodied_kg": embodied["infrastructure_embodied_kg"],
        "sorbent_embodied_kg": embodied["sorbent_embodied_kg"],
        "total_embodied_emissions_kg": total_embodied,
        "gross_captured_kg": gross_captured,
        "total_emissions_kg": total_emissions,
        "net_removal_kg": net_removal,
        "is_net_positive": net_removal > 0,
        "energy_intensity_kwh_per_tonne": energy_intensity,
        "steam_kg": steam_kg,
    }
