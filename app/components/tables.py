import pandas as pd


def weekly_summary_table(df):
    if df.empty:
        return pd.DataFrame()
    columns = [
        "week_label",
        "total_cycles",
        "liquefied_co2_kg",
        "total_emissions_kg",
        "net_removal_kg",
        "status",
    ]
    return df[columns].rename(
        columns={
            "week_label": "Week",
            "total_cycles": "Cycles",
            "liquefied_co2_kg": "Captured (kg)",
            "total_emissions_kg": "Emissions (kg)",
            "net_removal_kg": "Net (kg)",
            "status": "Status",
        }
    )
