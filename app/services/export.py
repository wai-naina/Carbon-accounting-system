from __future__ import annotations

import io
from typing import List

import pandas as pd

from app.database.models import CarbonNestWeeklySummary


def weekly_summaries_to_excel(weekly_summaries: List[CarbonNestWeeklySummary]) -> bytes:
    """Carbon Nest weekly summaries as a three-sheet workbook.

    Only Carbon Nest reaches here — Miniplant 2.0's reports page builds its own
    export inline. The sheets mirror the three-tier energy model so a reviewer
    can follow a week from the meter down to the components without needing the
    app: Summary is the headline plus both removal boundaries, Energy is the
    Tier 1/2 reconciliation, and Components is Tier 3 diagnostics.
    """
    summary_rows, energy_rows, component_rows = [], [], []
    for w in weekly_summaries:
        label = {
            "Year": w.year,
            "Week": w.week_number,
            "Start Date": w.start_date,
            "End Date": w.end_date,
        }
        summary_rows.append({
            **label,
            "Cycles": w.total_cycles,
            "Adsorbed CO2 (kg)": w.total_ads_co2_kg,
            "Desorbed CO2 (kg)": w.total_des_co2_kg,
            "Collected CO2 (kg)": w.total_bag_co2_kg,
            "Liquefied CO2 (kg)": w.liquefied_co2_kg,
            "Vented at Liquefaction (kg)": w.loss_stage_3_kg,
            "Liquefaction Efficiency (%)": w.liquefaction_efficiency_pct,
            # Boundary B — liquefied, credit-bearing
            "B/LIQ Product (kg)": w.gross_captured_kg,
            "B/LIQ Energy (kWh)": w.total_energy_kwh,
            "B/LIQ Operational (kg)": w.total_operational_emissions_kg,
            "B/LIQ Embodied (kg)": w.total_embodied_emissions_kg,
            "B/LIQ Total Emissions (kg)": w.total_emissions_kg,
            "B/LIQ Net Removal (kg)": w.net_removal_kg,
            "B/LIQ Intensity (kWh/t)": w.energy_intensity_kwh_per_tonne,
            "Net Positive": w.is_net_positive,
            # Boundary A — capture, liquefaction excluded from both sides
            "A/CAP Product (kg)": w.capture_gross_kg,
            "A/CAP Energy (kWh)": w.capture_energy_kwh,
            "A/CAP Operational (kg)": w.capture_operational_emissions_kg,
            "A/CAP Embodied (kg)": w.capture_embodied_emissions_kg,
            "A/CAP Total Emissions (kg)": w.capture_total_emissions_kg,
            "A/CAP Net Removal (kg)": w.capture_net_removal_kg,
            "A/CAP Intensity (kWh/t)": w.capture_energy_intensity_kwh_per_tonne,
            "Total Steam (kg)": w.total_steam_kg,
            "Notes": w.notes,
        })
        energy_rows.append({
            **label,
            "T1 Site Meter (kWh)": w.site_energy_kwh,
            "T1 Plant Meter (kWh)": w.plant_energy_kwh,
            "T1 Support Infra (derived)": w.support_infra_kwh,
            "T2 Boilers (kWh)": w.thermal_energy_kwh,
            "T2 Liquefaction (kWh)": w.liquefaction_energy_kwh,
            "T2 Fans (kWh)": w.fans_total_kwh,
            "T2 Utility Skid (kWh)": w.utility_skid_kwh,
            "T2 Plant Residual (derived)": w.plant_residual_kwh,
            "Process Energy / eTotal (kWh)": w.process_energy_kwh,
            "Auxiliary (kWh)": w.auxiliary_energy_kwh,
        })
        component_rows.append({
            **label,
            "Boiler A in-cycle": w.boiler_a_kwh,
            "Boiler A standby": w.boiler_a_standby_kwh,
            "Boiler B in-cycle": w.boiler_b_kwh,
            "Boiler B standby": w.boiler_b_standby_kwh,
            "Liquefaction active transfer": w.liquefaction_active_transfer_kwh,
            "Liquefaction standby/RFU": w.liquefaction_standby_kwh,
            "Fans in-cycle": w.fans_kwh,
            "Fan standby (derived)": w.fan_standby_kwh,
            "Fan N1 M1n2": w.fan_n1_m1n2_kwh,
            "Fan N1 M3n4": w.fan_n1_m3n4_kwh,
            "Fan N2 M1": w.fan_n2_m1_kwh,
            "Fan N2 M2": w.fan_n2_m2_kwh,
            "Fan N2 M3": w.fan_n2_m3_kwh,
            "Fan N2 M4": w.fan_n2_m4_kwh,
            "VP-402 in-cycle": w.vp402_kwh,
            "VP-402 standby": w.vp402_standby_kwh,
            "VP-501 in-cycle": w.vp501_kwh,
            "VP-501 standby": w.vp501_standby_kwh,
            "CT in-cycle": w.ct_kwh,
            "CT Pump in-cycle": w.ct_pump_kwh,
            "CT & CT Pump total": w.ct_ct_pump_total_kwh,
            "CT standby (derived)": w.ct_standby_kwh,
            "Compressor A": w.compressor_a_kwh,
            "Compressor B": w.compressor_b_kwh,
            "Water Pumps": w.water_pumps_kwh,
            "Air Dryer": w.air_dryer_kwh,
            "Others (derived)": w.others_kwh,
            # Excluded from every total — nobody has confirmed what it meters.
            "Main Utility (CSV, unused)": w.main_utility_kwh,
        })

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Summary")
        pd.DataFrame(energy_rows).to_excel(writer, index=False, sheet_name="Energy")
        pd.DataFrame(component_rows).to_excel(writer, index=False, sheet_name="Components")
    return output.getvalue()
