from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def safe_value(value: Optional[float]) -> float:
    return float(value or 0)


# Module pair classification
MODULE_PAIRS = {
    "1n3": ["Module 1n3", "Module 1", "Module 3", "NM1", "NM3", "1n3"],
    "2n4": ["Module 2n4", "Module 2", "Module 4", "NM2", "NM4", "2n4"],
}


def classify_module_pair(machine: str) -> Optional[str]:
    """Classify a machine into its Module pair (1n3 or 2n4)."""
    if not machine:
        return None
    machine_lower = machine.lower().strip()
    
    for pair, machines in MODULE_PAIRS.items():
        for m in machines:
            if m.lower() in machine_lower or machine_lower in m.lower():
                return pair
    
    # Check for numeric patterns
    if "1" in machine_lower or "3" in machine_lower:
        if "2" not in machine_lower and "4" not in machine_lower:
            return "1n3"
    if "2" in machine_lower or "4" in machine_lower:
        if "1" not in machine_lower and "3" not in machine_lower:
            return "2n4"
    
    return None


def get_pair_display_name(pair: str) -> str:
    """Get display name for a Module pair."""
    if pair == "1n3":
        return "Module 1&3"
    elif pair == "2n4":
        return "Module 2&4"
    return pair


def calculate_weekly_metrics(
    *,
    ads_co2_kg: float,
    des_co2_kg: float,
    bag_co2_kg: float,
    liquefied_co2_kg: float,
    thermal_energy_kwh: float,
    auxiliary_energy_kwh: float,
    total_energy_kwh: float,
    steam_kg: float,
    grid_ef: float,
    infrastructure_embodied_kg: float,
    sorbent_embodied_kg: float,
) -> Dict[str, Optional[float]]:
    # CO2 losses at each stage
    loss_stage_1 = ads_co2_kg - des_co2_kg  # Adsorbed → Desorbed
    loss_stage_2 = des_co2_kg - bag_co2_kg  # Desorbed → Collected (Bag)
    
    # Stage 3 loss (Collected → Liquefied) only calculated if liquefaction data exists
    # If no liquefaction data, the CO2 is still in the bag - not lost
    if liquefied_co2_kg > 0:
        loss_stage_3 = bag_co2_kg - liquefied_co2_kg  # Bag → Liquefied
        gross_captured = liquefied_co2_kg
    else:
        loss_stage_3 = 0  # No liquefaction yet, so no stage 3 loss
        gross_captured = bag_co2_kg  # Use collected (bag) as the "captured" amount
    
    # Total system loss = Adsorbed - Collected (cumulative from adsorption to final collection point)
    total_loss = ads_co2_kg - gross_captured

    thermal_emissions = thermal_energy_kwh * grid_ef
    auxiliary_emissions = auxiliary_energy_kwh * grid_ef
    total_operational_emissions = total_energy_kwh * grid_ef

    total_embodied = infrastructure_embodied_kg + sorbent_embodied_kg
    total_emissions = total_operational_emissions + total_embodied
    
    # Net removal: use liquefied if available, otherwise use collected (bag)
    net_removal = gross_captured - total_emissions

    # Energy intensity: use liquefied if available, otherwise use BAG (collected) CO2
    energy_intensity = None
    co2_for_intensity = liquefied_co2_kg if liquefied_co2_kg > 0 else bag_co2_kg
    if co2_for_intensity > 0 and total_energy_kwh > 0:
        energy_intensity = total_energy_kwh / (co2_for_intensity / 1000)  # kWh per tonne CO2

    return {
        "loss_stage_1_kg": loss_stage_1,
        "loss_stage_2_kg": loss_stage_2,
        "loss_stage_3_kg": loss_stage_3,
        "total_loss_kg": total_loss,
        "thermal_emissions_kg": thermal_emissions,
        "auxiliary_emissions_kg": auxiliary_emissions,
        "total_operational_emissions_kg": total_operational_emissions,
        "infrastructure_embodied_kg": infrastructure_embodied_kg,
        "sorbent_embodied_kg": sorbent_embodied_kg,
        "total_embodied_emissions_kg": total_embodied,
        "gross_captured_kg": gross_captured,
        "total_emissions_kg": total_emissions,
        "net_removal_kg": net_removal,
        "is_net_positive": net_removal > 0,
        "energy_intensity_kwh_per_tonne": energy_intensity,
        "steam_kg": steam_kg,
    }
