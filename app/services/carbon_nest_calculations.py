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


def _intensity(energy_kwh: float, co2_kg: float) -> Optional[float]:
    """kWh per tonne CO2, or None when the ratio is undefined.

    None rather than 0: a week that captured nothing has no intensity, and
    reporting 0 kWh/t would read as perfect efficiency.
    """
    if co2_kg <= 0 or energy_kwh <= 0:
        return None
    return energy_kwh / (co2_kg / 1000)


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
    liquefaction_energy_kwh: float = 0.0,
    steam_kg: float,
    grid_ef: float,
) -> Dict[str, Optional[float]]:
    """Carbon Nest weekly metrics, on both removal boundaries.

    Operational emissions are charged on `total_energy_kwh` — the site utility
    meter — x grid EF. Every load is electric (the boilers included, confirmed
    2026-08-25), so one factor covers the whole facility. Embodied emissions
    are output-based: kg CO2-eq/t driver intensities from the v0.6 LCA applied
    to the CO2 captured this week (see carbon_nest_embodied.py).

    Two boundaries are computed unconditionally, never as an either/or:

      B. LIQUEFIED (credit-bearing) — product = liquefied, energy = full site
         meter. The headline: what actually ends up in the cryogenic tank.
      A. CAPTURE — product = collected/bagged, energy = site less
         liquefaction. Isolates capture performance, so a bad liquefaction
         week can't mask a good capture week.

    Boundary B deliberately does NOT fall back to bag CO2 when nothing was
    liquefied. The previous version did, which made a week that liquefied
    nothing score better than one that liquefied a little — the incentive ran
    backwards. A zero-liquefaction week now reads as zero product, which is
    what it is; boundary A is where that week's capture work shows up.

    Expect boundary B to show *lower* total emissions but *worse* net removal
    than A. That's correct, not a bug: embodied is charged per tonne of
    product, so it shrinks with the denominator. Always present the two with
    their product masses attached.

    `loss_stage_3` (collected - liquefied) is CO2 vented during liquefaction.
    It reduces product but is never added to emissions: it's atmospheric carbon
    returning to the atmosphere, a failure to remove rather than a new release,
    and charging it as an emission as well would double-penalise it.

    `process_energy_kwh` (Fans/CT/CT Pump/VP402/VP501/Boiler A/B from the CSV)
    only feeds the reported-alongside intensities that reproduce the Athena
    weekly PDF's "BAG/LIQ MWh efficiency" figures. It never drives emissions.
    """
    if process_energy_kwh is None:
        process_energy_kwh = total_energy_kwh

    loss_stage_1 = ads_co2_kg - des_co2_kg  # Adsorbed -> Desorbed
    loss_stage_2 = des_co2_kg - bag_co2_kg  # Desorbed -> Collected (Bag)
    loss_stage_3 = bag_co2_kg - liquefied_co2_kg  # Collected -> Liquefied (vented)

    liquefaction_efficiency = (
        (liquefied_co2_kg / bag_co2_kg * 100) if bag_co2_kg > 0 else None
    )

    # --- Boundary B: liquefied (credit-bearing) ---------------------------
    gross_captured = liquefied_co2_kg
    total_loss = ads_co2_kg - gross_captured

    thermal_emissions = thermal_energy_kwh * grid_ef
    auxiliary_emissions = auxiliary_energy_kwh * grid_ef
    total_operational_emissions = total_energy_kwh * grid_ef

    embodied = calculate_embodied_kg(gross_captured)
    total_embodied = embodied["total_embodied_emissions_kg"]
    total_emissions = total_operational_emissions + total_embodied
    net_removal = gross_captured - total_emissions

    # --- Boundary A: capture (liquefaction excluded, both sides) -----------
    capture_energy = max(total_energy_kwh - liquefaction_energy_kwh, 0.0)
    capture_operational = capture_energy * grid_ef
    capture_embodied = calculate_embodied_kg(bag_co2_kg)["total_embodied_emissions_kg"]
    capture_total_emissions = capture_operational + capture_embodied
    capture_net_removal = bag_co2_kg - capture_total_emissions

    return {
        "loss_stage_1_kg": loss_stage_1,
        "loss_stage_2_kg": loss_stage_2,
        "loss_stage_3_kg": loss_stage_3,
        "total_loss_kg": total_loss,
        "liquefaction_efficiency_pct": liquefaction_efficiency,
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
        "energy_intensity_kwh_per_tonne": _intensity(total_energy_kwh, gross_captured),
        "capture_gross_kg": bag_co2_kg,
        "capture_operational_emissions_kg": capture_operational,
        "capture_embodied_emissions_kg": capture_embodied,
        "capture_total_emissions_kg": capture_total_emissions,
        "capture_net_removal_kg": capture_net_removal,
        "capture_energy_kwh": capture_energy,
        "capture_energy_intensity_kwh_per_tonne": _intensity(capture_energy, bag_co2_kg),
        # Athena-comparable, process-energy basis — reproduces the weekly PDF's
        # "BAG MWh efficiency" / "LIQ MWh efficiency" exactly. Display only.
        "process_intensity_bag_kwh_per_tonne": _intensity(process_energy_kwh, bag_co2_kg),
        "process_intensity_liq_kwh_per_tonne": _intensity(process_energy_kwh, liquefied_co2_kg),
        "steam_kg": steam_kg,
    }
