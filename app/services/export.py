from __future__ import annotations

import io
from typing import List

import pandas as pd

from app.database.models import WeeklySummary


def weekly_summaries_to_excel(weekly_summaries: List[WeeklySummary]) -> bytes:
    rows = []
    for w in weekly_summaries:
        rows.append(
            {
                "Year": w.year,
                "Week": w.week_number,
                "Start Date": w.start_date,
                "End Date": w.end_date,
                "Liquefied CO2 (kg)": w.liquefied_co2_kg,
                "Operational Emissions (kg)": w.total_operational_emissions_kg,
                "Embodied Emissions (kg)": w.total_embodied_emissions_kg,
                "Net Removal (kg)": w.net_removal_kg,
                "Net Positive": w.is_net_positive,
                "Total Energy (kWh)": w.total_energy_kwh,
                "Energy Intensity (kWh/tCO2)": w.energy_intensity_kwh_per_tonne,
            }
        )
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Weekly Summary")
    return output.getvalue()
