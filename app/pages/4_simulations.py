import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.auth.authentication import require_login
from app.components.branding import get_brand_css, render_logo
from app.components.sidebar import render_module_filter, get_filter_display_name
from app.database.connection import get_session, init_db
from app.database.models import WeeklySummary, SystemConfig
from app.services.aggregation import get_weekly_metrics_by_pair
from app.services.embodied_config import (
    get_weekly_embodied_kg,
    get_sorbent_degradation_rate,
    SORBENT_PEI_RATE,
    SORBENT_METHANOL_RATE,
)

SORBENT_RATE = get_sorbent_degradation_rate()  # 0.1522 kgCO₂eq/kgCO₂ — used in Tabs 2, 4, 5


def get_emission_factor(session, key: str, default: float) -> float:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if config:
        try:
            return float(config.value)
        except ValueError:
            pass
    return default


def calculate_geothermal_scenario(
    thermal_kwh: float,
    auxiliary_kwh: float,
    steam_kg: float,
    grid_ef: float,
    geothermal_steam_ef: float,
    embodied_kg: float,
    collected_co2_kg: float,
) -> dict:
    """Calculate what-if geothermal scenario.
    
    Args:
        thermal_kwh: Thermal energy consumption (boiler kWh)
        auxiliary_kwh: Auxiliary energy consumption (fans, pumps, etc.)
        steam_kg: Steam used (kg) - from SCADA
        grid_ef: Grid electricity emission factor (kg CO2/kWh)
        geothermal_steam_ef: Geothermal steam emission factor (kg CO2/kg steam)
        embodied_kg: Weekly embodied emissions (kg CO2)
        collected_co2_kg: Collected CO2 (liquefied if available, otherwise bag)
    
    Current scenario: Boiler uses grid electricity to generate steam
    Geothermal scenario: Steam comes directly from geothermal source
    """
    # Current scenario (all grid electricity)
    current_thermal_emissions = thermal_kwh * grid_ef  # Boiler electricity
    current_auxiliary_emissions = auxiliary_kwh * grid_ef
    current_total_operational = current_thermal_emissions + current_auxiliary_emissions
    current_total = current_total_operational + embodied_kg
    current_net = collected_co2_kg - current_total
    
    # Geothermal scenario:
    # - Thermal: Steam from geothermal (use steam_kg × geothermal EF per kg)
    # - Auxiliary: Still uses grid electricity
    geo_thermal_emissions = steam_kg * geothermal_steam_ef  # Steam × EF per kg
    geo_auxiliary_emissions = auxiliary_kwh * grid_ef
    geo_total_operational = geo_thermal_emissions + geo_auxiliary_emissions
    geo_total = geo_total_operational + embodied_kg
    geo_net = collected_co2_kg - geo_total
    
    # Improvements
    operational_reduction = current_total_operational - geo_total_operational
    operational_reduction_pct = (operational_reduction / current_total_operational * 100) if current_total_operational > 0 else 0
    net_improvement = geo_net - current_net
    
    return {
        "current": {
            "thermal_emissions": current_thermal_emissions,
            "auxiliary_emissions": current_auxiliary_emissions,
            "operational_emissions": current_total_operational,
            "total_emissions": current_total,
            "net_removal": current_net,
            "is_net_positive": current_net > 0,
        },
        "geothermal": {
            "thermal_emissions": geo_thermal_emissions,
            "auxiliary_emissions": geo_auxiliary_emissions,
            "operational_emissions": geo_total_operational,
            "total_emissions": geo_total,
            "net_removal": geo_net,
            "is_net_positive": geo_net > 0,
        },
        "improvement": {
            "operational_reduction_kg": operational_reduction,
            "operational_reduction_pct": operational_reduction_pct,
            "net_improvement_kg": net_improvement,
        }
    }


def main() -> None:
    st.set_page_config(page_title="Energy Scenarios - Octavia CAS", page_icon="🔋", layout="wide")
    init_db()
    if not require_login():
        return

    # Apply brand CSS
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    
    # Sidebar with logo
    render_logo(location="sidebar")
    
    # Render the Module pair filter in sidebar and get selected value
    pair_filter = render_module_filter()

    st.title("🔋 Energy Scenario Analysis")
    
    # Show filter indicator
    if pair_filter:
        pair_name = get_filter_display_name(pair_filter)
        st.info(f"🔬 **Filtered View:** Showing data for **{pair_name}** only. Change filter in sidebar.")
    else:
        st.markdown("""
        Compare current grid electricity operations with potential geothermal steam integration.
        The boiler accounts for ~70% of energy consumption - switching to geothermal steam can 
        dramatically reduce operational emissions.
        """)

    session = get_session()
    try:
        # Emission factors — hardcoded physical/regulatory constants (bypass stale DB values)
        grid_ef = 0.055              # kg CO2/kWh — Kenya Power 2024 (0.055 tCO2/MWh)
        geothermal_steam_ef = 0.001890  # kg CO2/kg steam — 0.886 g/MJ × 2.1334 MJ/kg at 4 bara
        
        # Get weekly summaries for historical analysis
        raw_summaries = (
            session.query(WeeklySummary)
            .order_by(WeeklySummary.year.desc(), WeeklySummary.week_number.desc())
            .all()
        )
        
        # If pair filter is active, recalculate metrics from filtered cycles
        summaries = []
        for s in raw_summaries:
            if pair_filter:
                pair_metrics = get_weekly_metrics_by_pair(session, s.year, s.week_number, pair_filter)
                if pair_metrics["cycles"] == 0:
                    continue  # Skip weeks with no data for this pair
                
                # Create a summary-like object with filtered data
                class FilteredSummary:
                    pass
                
                fs = FilteredSummary()
                fs.year = s.year
                fs.week_number = s.week_number
                fs.thermal_energy_kwh = pair_metrics["boiler_kwh"]
                fs.auxiliary_energy_kwh = pair_metrics["auxiliary_kwh"]
                fs.total_energy_kwh = pair_metrics["total_kwh"]
                fs.total_steam_kg = pair_metrics["steam_kg"]
                fs.total_ads_co2_kg = pair_metrics["ads_co2_kg"]
                fs.total_des_co2_kg = pair_metrics["des_co2_kg"]
                fs.total_bag_co2_kg = pair_metrics["bag_co2_kg"]
                fs.total_cycles = pair_metrics["cycles"]
                
                # Allocate liquefied proportionally by bag CO2 share
                liq = s.liquefied_co2_kg or 0
                total_bag = s.total_bag_co2_kg or 0
                if liq > 0 and total_bag > 0:
                    fs.liquefied_co2_kg = liq * (pair_metrics["bag_co2_kg"] / total_bag)
                else:
                    fs.liquefied_co2_kg = 0
                
                # Embodied split equally between pairs — both share the same infrastructure
                fs.total_embodied_emissions_kg = get_weekly_embodied_kg() / 2
                summaries.append(fs)
            else:
                summaries.append(s)
    finally:
        session.close()

    # Configuration display
    st.markdown("### ⚙️ Emission Factors")
    ef_col1, ef_col2, ef_col3 = st.columns(3)

    with ef_col1:
        st.markdown(f"""
        <div style="background:#fff3e0; padding:1rem; border-radius:8px; border-left:4px solid #FD7E14;">
            <div style="font-size:0.8rem; color:#666;">Kenya Grid Electricity</div>
            <div style="font-size:1.5rem; font-weight:bold; color:#ef6c00;">{grid_ef} kg CO₂/kWh</div>
            <div style="font-size:0.75rem; color:#888;">0.055 tCO₂/MWh — Kenya Power 2024</div>
        </div>
        """, unsafe_allow_html=True)

    with ef_col2:
        st.markdown(f"""
        <div style="background:#e8f5e9; padding:1rem; border-radius:8px; border-left:4px solid #28A745;">
            <div style="font-size:0.8rem; color:#666;">Geothermal Steam (4 bara)</div>
            <div style="font-size:1.5rem; font-weight:bold; color:#2e7d32;">{geothermal_steam_ef:.5f} kg CO₂/kg steam</div>
            <div style="font-size:0.75rem; color:#888;">0.886 g CO₂/MJ × 2133.4 kJ/kg latent heat</div>
        </div>
        """, unsafe_allow_html=True)

    with ef_col3:
        st.markdown(f"""
        <div style="background:#e3f2fd; padding:1rem; border-radius:8px; border-left:4px solid #2196F3;">
            <div style="font-size:0.8rem; color:#666;">Geothermal Electricity</div>
            <div style="font-size:1.5rem; font-weight:bold; color:#1565c0;">0.003 kg CO₂/kWh</div>
            <div style="font-size:0.75rem; color:#888;">3 g CO₂/kWh — geothermal power plant</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Tabs for different analysis modes
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🧮 Custom Calculator",
        "📊 Historical What-If",
        "📈 Monte Carlo",
        "🎯 Break-even Targets",
        "🏆 Credit Target Tracker",
    ])

    with tab1:
        st.markdown("### Custom Scenario Calculator")
        st.markdown("Enter energy consumption values to compare current vs geothermal scenarios.")
        
        input_col1, input_col2 = st.columns(2)
        
        with input_col1:
            st.markdown("**Current Operations (Grid)**")
            thermal_kwh = st.number_input("Boiler Energy (kWh)", min_value=0.0, value=3540.0, step=100.0,
                                          help="Electricity used by boiler to generate steam")
            auxiliary_kwh = st.number_input("Electrical Energy (kWh)", min_value=0.0, value=1460.0, step=100.0,
                                            help="Fans, pumps, compressors, etc.")
            steam_kg = st.number_input("Steam Used (kg)", min_value=0.0, value=5000.0, step=100.0,
                                       help="From SCADA - this will be used for geothermal calculation")
            total_kwh = thermal_kwh + auxiliary_kwh
            st.caption(f"Total Energy: {total_kwh:.0f} kWh")
        
        with input_col2:
            st.markdown("**CO₂ Capture & Emissions**")
            collected_kg = st.number_input("Collected CO₂ (kg)", min_value=0.0, value=500.0, step=10.0, 
                                           help="Use liquefied if available, otherwise bag/collected CO₂")
            embodied_kg = st.number_input("Weekly Embodied Emissions (kg)", min_value=0.0, value=round(get_weekly_embodied_kg(), 2), step=1.0)

        if st.button("🔄 Calculate Scenarios", type="primary", width="stretch"):
            results = calculate_geothermal_scenario(
                thermal_kwh, auxiliary_kwh, steam_kg, grid_ef, geothermal_steam_ef, embodied_kg, collected_kg
            )
            
            st.markdown("### Results")
            
            # Comparison cards
            res_col1, res_col2, res_col3 = st.columns(3)
            
            with res_col1:
                current = results["current"]
                is_pos = current["is_net_positive"]
                st.markdown(f"""
                <div style="background:#fff3e0; padding:1.5rem; border-radius:12px; border:2px solid #FD7E14;">
                    <div style="font-size:1.1rem; font-weight:bold; color:#ef6c00; margin-bottom:1rem;">⚡ Current (Grid)</div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Thermal:</span> 
                        <span style="font-weight:bold;">{current['thermal_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Auxiliary:</span> 
                        <span style="font-weight:bold;">{current['auxiliary_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Total Operational:</span> 
                        <span style="font-weight:bold;">{current['operational_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">+ Embodied:</span> 
                        <span style="font-weight:bold;">{embodied_kg:.1f} kg</span>
                    </div>
                    <hr style="margin:1rem 0;">
                    <div style="font-size:1.2rem; font-weight:bold; color:{'#2e7d32' if is_pos else '#c62828'};">
                        Net: {current['net_removal']:.1f} kg {'✅' if is_pos else '❌'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with res_col2:
                geo = results["geothermal"]
                is_pos = geo["is_net_positive"]
                st.markdown(f"""
                <div style="background:#e8f5e9; padding:1.5rem; border-radius:12px; border:2px solid #28A745;">
                    <div style="font-size:1.1rem; font-weight:bold; color:#2e7d32; margin-bottom:1rem;">🌿 Geothermal</div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Thermal:</span> 
                        <span style="font-weight:bold;">{geo['thermal_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Auxiliary:</span> 
                        <span style="font-weight:bold;">{geo['auxiliary_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Total Operational:</span> 
                        <span style="font-weight:bold;">{geo['operational_emissions']:.1f} kg</span>
                    </div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">+ Embodied:</span> 
                        <span style="font-weight:bold;">{embodied_kg:.1f} kg</span>
                    </div>
                    <hr style="margin:1rem 0;">
                    <div style="font-size:1.2rem; font-weight:bold; color:{'#2e7d32' if is_pos else '#c62828'};">
                        Net: {geo['net_removal']:.1f} kg {'✅' if is_pos else '❌'}
                    </div>
                </div>
                """, unsafe_allow_html=True)
            
            with res_col3:
                imp = results["improvement"]
                st.markdown(f"""
                <div style="background:#e3f2fd; padding:1.5rem; border-radius:12px; border:2px solid #2196F3;">
                    <div style="font-size:1.1rem; font-weight:bold; color:#1565c0; margin-bottom:1rem;">📈 Improvement</div>
                    <div style="margin-bottom:0.5rem;">
                        <span style="color:#666;">Emissions Reduction:</span>
                    </div>
                    <div style="font-size:1.5rem; font-weight:bold; color:#2e7d32; margin-bottom:0.5rem;">
                        -{imp['operational_reduction_kg']:.1f} kg
                    </div>
                    <div style="margin-bottom:1rem;">
                        <span style="font-weight:bold; color:#2e7d32;">({imp['operational_reduction_pct']:.1f}% reduction)</span>
                    </div>
                    <hr style="margin:1rem 0;">
                    <div style="font-size:0.9rem; color:#666;">Net Improvement:</div>
                    <div style="font-size:1.2rem; font-weight:bold; color:#2e7d32;">
                        +{imp['net_improvement_kg']:.1f} kg
                    </div>
                </div>
                """, unsafe_allow_html=True)

            # Comparison chart
            fig = go.Figure()
            
            categories = ["Thermal", "Auxiliary", "Embodied", "Total"]
            current_vals = [
                results["current"]["thermal_emissions"],
                results["current"]["auxiliary_emissions"],
                embodied_kg,
                results["current"]["total_emissions"],
            ]
            geo_vals = [
                results["geothermal"]["thermal_emissions"],
                results["geothermal"]["auxiliary_emissions"],
                embodied_kg,
                results["geothermal"]["total_emissions"],
            ]
            
            fig.add_trace(go.Bar(
                name="Current (Grid)",
                x=categories,
                y=current_vals,
                marker_color="#FD7E14",
                text=[f"{v:.1f}" for v in current_vals],
                textposition="outside",
            ))
            
            fig.add_trace(go.Bar(
                name="Geothermal",
                x=categories,
                y=geo_vals,
                marker_color="#28A745",
                text=[f"{v:.1f}" for v in geo_vals],
                textposition="outside",
            ))
            
            # Add captured line
            fig.add_hline(
                y=collected_kg, 
                line_dash="dash", 
                line_color="#2196F3",
                annotation_text=f"CO₂ Collected: {collected_kg:.0f} kg",
            )
            
            fig.update_layout(
                title="Emissions Comparison by Category",
                yaxis_title="kg CO₂",
                template="plotly_white",
                barmode="group",
                height=450,
            )
            
            st.plotly_chart(fig, width="stretch")

    with tab2:
        st.markdown("### Historical What-If Analysis")
        st.markdown(
            "Net removal figures include **sorbent degradation** "
            "as an operational emission alongside energy-based emissions."
        )

        if not summaries:
            st.warning("No weekly data available. Import SCADA data first.")
        else:
            rows = []
            for s in summaries[:12]:  # Last 12 weeks
                thermal = s.thermal_energy_kwh or 0
                auxiliary = s.auxiliary_energy_kwh or 0
                steam = s.total_steam_kg or 0
                # Use corrected LCA embodied value (not stale DB value)
                embodied = get_weekly_embodied_kg() / 2 if pair_filter else get_weekly_embodied_kg()
                liquefied = s.liquefied_co2_kg or 0
                bag = s.total_bag_co2_kg or 0
                collected_co2 = liquefied if liquefied > 0 else bag

                # Sorbent degradation: combined LCA rate × collected CO2
                sorbent_emissions = SORBENT_RATE * collected_co2

                if thermal + auxiliary > 0:
                    results = calculate_geothermal_scenario(
                        thermal, auxiliary, steam, grid_ef, geothermal_steam_ef, embodied, collected_co2
                    )

                    # Subtract sorbent degradation from net removal
                    current_net = results["current"]["net_removal"] - sorbent_emissions
                    geo_net = results["geothermal"]["net_removal"] - sorbent_emissions

                    rows.append({
                        "Week": f"{s.year}-W{s.week_number:02d}",
                        "Collected (kg)": f"{collected_co2:.1f}",
                        "Steam (kg)": f"{steam:.0f}",
                        "Sorbent Degrad. (kg)": f"{sorbent_emissions:.1f}",
                        "Current Net (kg)": current_net,
                        "Geo Net (kg)": geo_net,
                        "Geo Improvement (kg)": results["improvement"]["net_improvement_kg"],
                        "Current": "✅" if current_net > 0 else "❌",
                        "Geothermal": "✅" if geo_net > 0 else "❌",
                    })

            if rows:
                df = pd.DataFrame(rows)

                sum_col1, sum_col2, sum_col3 = st.columns(3)
                with sum_col1:
                    current_positive = sum(1 for r in rows if r["Current"] == "✅")
                    st.metric("Weeks Net Positive (Current)", f"{current_positive}/{len(rows)}")
                with sum_col2:
                    geo_positive = sum(1 for r in rows if r["Geothermal"] == "✅")
                    st.metric("Weeks Net Positive (Geothermal)", f"{geo_positive}/{len(rows)}")
                with sum_col3:
                    total_improvement = sum(r["Geo Improvement (kg)"] for r in rows)
                    st.metric("Total Geo Improvement", f"+{total_improvement:.1f} kg")

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name="Current (Grid)",
                    x=df["Week"],
                    y=df["Current Net (kg)"],
                    marker_color="#FD7E14",
                ))
                fig.add_trace(go.Bar(
                    name="Geothermal Scenario",
                    x=df["Week"],
                    y=df["Geo Net (kg)"],
                    marker_color="#28A745",
                ))
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.update_layout(
                    title="Net Removal (incl. Sorbent Degradation): Current vs Geothermal",
                    yaxis_title="Net CO₂ Removal (kg)",
                    template="plotly_white",
                    barmode="group",
                    height=430,
                )
                st.plotly_chart(fig, width="stretch")
                st.dataframe(df, width="stretch", hide_index=True)
            else:
                st.warning("No weeks with energy data available for analysis.")

    with tab3:
        st.markdown("### Monte Carlo Simulation")
        st.markdown("""
        Run simulations with variable parameters to understand the range of possible outcomes
        when transitioning to geothermal steam.
        """)
        
        st.markdown("#### Simulation Parameters")
        
        param_col1, param_col2, param_col3 = st.columns(3)
        
        with param_col1:
            st.markdown("**Current Operations (Grid)**")
            thermal_min = st.number_input("Min Boiler kWh", value=2500.0, step=100.0)
            thermal_max = st.number_input("Max Boiler kWh", value=4500.0, step=100.0)
            aux_min = st.number_input("Min Electrical kWh", value=1000.0, step=100.0)
            aux_max = st.number_input("Max Electrical kWh", value=2000.0, step=100.0)
        
        with param_col2:
            st.markdown("**Steam (for Geothermal)**")
            steam_min = st.number_input("Min Steam kg", value=4000.0, step=100.0)
            steam_max = st.number_input("Max Steam kg", value=8000.0, step=100.0)
            embodied = st.number_input("Embodied Emissions kg", value=round(get_weekly_embodied_kg(), 2), step=1.0)
            n_simulations = st.number_input("Simulations", min_value=100, max_value=10000, value=1000, step=100)
        
        with param_col3:
            st.markdown("**CO₂ Collected**")
            collected_min = st.number_input("Min Collected kg", value=100.0, step=50.0)
            collected_max = st.number_input("Max Collected kg", value=300.0, step=50.0)

        if st.button("🎲 Run Monte Carlo Simulation", type="primary", width="stretch"):
            import numpy as np
            
            # Generate random samples
            np.random.seed(42)
            thermal_samples = np.random.uniform(thermal_min, thermal_max, n_simulations)
            aux_samples = np.random.uniform(aux_min, aux_max, n_simulations)
            steam_samples = np.random.uniform(steam_min, steam_max, n_simulations)
            collected_samples = np.random.uniform(collected_min, collected_max, n_simulations)
            
            current_nets = []
            geo_nets = []
            improvements = []
            
            for i in range(n_simulations):
                results = calculate_geothermal_scenario(
                    thermal_samples[i],
                    aux_samples[i],
                    steam_samples[i],
                    grid_ef,
                    geothermal_steam_ef,
                    embodied,
                    collected_samples[i],
                )
                current_nets.append(results["current"]["net_removal"])
                geo_nets.append(results["geothermal"]["net_removal"])
                improvements.append(results["improvement"]["net_improvement_kg"])
            
            current_nets = np.array(current_nets)
            geo_nets = np.array(geo_nets)
            improvements = np.array(improvements)
            
            # Statistics
            st.markdown("### Simulation Results")
            
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            
            with stat_col1:
                st.markdown("**Current Scenario**")
                st.write(f"Mean Net: {current_nets.mean():.1f} kg")
                st.write(f"Std Dev: {current_nets.std():.1f} kg")
                st.write(f"% Net Positive: {(current_nets > 0).mean() * 100:.1f}%")
            
            with stat_col2:
                st.markdown("**Geothermal Scenario**")
                st.write(f"Mean Net: {geo_nets.mean():.1f} kg")
                st.write(f"Std Dev: {geo_nets.std():.1f} kg")
                st.write(f"% Net Positive: {(geo_nets > 0).mean() * 100:.1f}%")
            
            with stat_col3:
                st.markdown("**Improvement**")
                st.write(f"Mean: +{improvements.mean():.1f} kg")
                st.write(f"Min: +{improvements.min():.1f} kg")
                st.write(f"Max: +{improvements.max():.1f} kg")
            
            # Distribution chart
            fig = go.Figure()
            
            fig.add_trace(go.Histogram(
                x=current_nets,
                name="Current (Grid)",
                marker_color="#FD7E14",
                opacity=0.7,
                nbinsx=50,
            ))
            
            fig.add_trace(go.Histogram(
                x=geo_nets,
                name="Geothermal",
                marker_color="#28A745",
                opacity=0.7,
                nbinsx=50,
            ))
            
            fig.add_vline(x=0, line_dash="dash", line_color="red", annotation_text="Break-even")
            
            fig.update_layout(
                title=f"Net Removal Distribution ({n_simulations} simulations)",
                xaxis_title="Net CO₂ Removal (kg)",
                yaxis_title="Frequency",
                template="plotly_white",
                barmode="overlay",
                height=450,
            )
            
            st.plotly_chart(fig, width="stretch")
            
            # Box plot comparison
            fig2 = go.Figure()
            
            fig2.add_trace(go.Box(
                y=current_nets,
                name="Current (Grid)",
                marker_color="#FD7E14",
            ))
            
            fig2.add_trace(go.Box(
                y=geo_nets,
                name="Geothermal",
                marker_color="#28A745",
            ))
            
            fig2.add_hline(y=0, line_dash="dash", line_color="red")
            
            fig2.update_layout(
                title="Net Removal Distribution Comparison",
                yaxis_title="Net CO₂ Removal (kg)",
                template="plotly_white",
                height=400,
            )
            
            st.plotly_chart(fig2, width="stretch")


    with tab4:
        st.markdown("### 🎯 Break-even Targets")
        st.markdown(
            "Compare three energy configurations to see which keeps the plant net carbon positive. "
            "All figures are **normalised per tonne of CO₂ captured** — the same units your team reads from the meter."
        )

        # ── Constants (corrected EFs) ───────────────────────────────────────────────────
        GEO_ELEC_EF         = 0.003                          # kg CO₂/kWh — geothermal electricity
        STEAM_HFG_MJ_PER_KG = 2.1334                         # MJ/kg — 4 bara saturated latent heat
        STEAM_EF_PER_MJ     = 0.000886                       # kg CO₂/MJ
        STEAM_EF_PER_KG     = STEAM_EF_PER_MJ * STEAM_HFG_MJ_PER_KG  # = 0.001890 kg CO₂/kg steam

        # ── Inputs (all normalised — no kWh/week shown) ──────────────────────────────────
        annual_target_t = st.number_input(
            "Annual capture target (tonnes CO₂/yr)",
            min_value=1.0, max_value=10000.0, value=25.0, step=5.0,
            help="Design capacity is 25 t/yr.",
        )

        be_col1, be_col2, be_col3 = st.columns(3)
        with be_col1:
            s1_elec_mwh_t = st.number_input(
                "Scenario 1 — Electricity intensity (MWh / tonne CO₂)",
                min_value=0.0, value=32.0, step=0.5,
                help="Total electricity per tonne CO₂ when the boiler is electric (boiler + all other loads). Your current reading is ~32 MWh/t.",
            )
        with be_col2:
            s23_elec_mwh_t = st.number_input(
                "Scenarios 2 & 3 — Electricity intensity (MWh / tonne CO₂)",
                min_value=0.0, value=3.0, step=0.5,
                help="Electricity per tonne CO₂ when the boiler is replaced by steam (non-boiler loads only).",
            )
        with be_col3:
            steam_kg_per_kgco2 = st.number_input(
                "Scenarios 2 & 3 — Steam intensity (kg steam / kg CO₂)",
                min_value=0.0, value=4.5, step=0.5,
                help="Geothermal steam consumed per kg of CO₂ captured. Heat content from 4 bara steam tables: hfg = 2133.4 kJ/kg.",
            )

        # ── Common budget (backend — users see only normalised outputs) ──────────────────
        weekly_target_kg = (annual_target_t * 1000) / 52    # kg CO₂/week
        weekly_target_t  = annual_target_t / 52              # tonnes/week

        # Normalised → weekly absolutes
        s1_elec_kwh_week  = s1_elec_mwh_t  * 1000 * weekly_target_t
        s23_elec_kwh_week = s23_elec_mwh_t * 1000 * weekly_target_t
        steam_kg_week     = steam_kg_per_kgco2 * weekly_target_kg

        embodied_weekly = get_weekly_embodied_kg()           # 67.27 kg/week (ramp-up phase: 26% over 5 yrs)
        sorbent_weekly  = SORBENT_RATE * weekly_target_kg    # 0.1522 × captured kg
        ops_budget      = weekly_target_kg - embodied_weekly - sorbent_weekly

        # ── Scenario emissions ────────────────────────────────────────────────────────
        s1_emis = s1_elec_kwh_week * grid_ef                 # S1: all electricity at grid EF
        s1_net  = ops_budget - s1_emis

        s2_steam_emis = steam_kg_week * STEAM_EF_PER_KG      # S2: steam + grid elec
        s2_elec_emis  = s23_elec_kwh_week * grid_ef
        s2_emis       = s2_elec_emis + s2_steam_emis
        s2_net        = ops_budget - s2_emis

        s3_steam_emis = steam_kg_week * STEAM_EF_PER_KG      # S3: steam + geo elec
        s3_elec_emis  = s23_elec_kwh_week * GEO_ELEC_EF
        s3_emis       = s3_elec_emis + s3_steam_emis
        s3_net        = ops_budget - s3_emis

        # ── Break-even limits (returned normalised) ─────────────────────────────────────────
        def _safe_div(num, den):
            return num / den if (den > 0 and num > 0) else 0.0

        s1_max_mwh_t         = _safe_div(ops_budget, grid_ef * weekly_target_t * 1000)
        s2_max_elec_mwh_t    = _safe_div(ops_budget - s2_steam_emis, grid_ef * weekly_target_t * 1000)
        s2_max_steam_kgkgco2 = _safe_div(ops_budget - s2_elec_emis,  STEAM_EF_PER_KG * weekly_target_kg)
        s3_max_elec_mwh_t    = _safe_div(ops_budget - s3_steam_emis, GEO_ELEC_EF * weekly_target_t * 1000)
        s3_max_steam_kgkgco2 = _safe_div(ops_budget - s3_elec_emis,  STEAM_EF_PER_KG * weekly_target_kg)

        st.markdown("---")

        if ops_budget <= 0:
            st.error(
                "The fixed embodied and sorbent costs already exceed the weekly CO₂ captured. "
                "There is no room for any energy — increase the capture target."
            )
        else:
            st.markdown("#### How each energy configuration compares at design capacity")
            sc1, sc2, sc3 = st.columns(3)

            def _card_colors(net: float):
                return ("#c62828", "#ffebee", "#ef9a9a") if net < 0 else ("#2e7d32", "#e8f5e9", "#a5d6a7")

            # S1 card
            tc1, bg1, bd1 = _card_colors(s1_net)
            with sc1:
                ou1 = "✅ under limit" if s1_net >= 0 else f"❌ {s1_elec_mwh_t - s1_max_mwh_t:.1f} MWh/t over"
                st.markdown(f"""
                <div style="background:{bg1}; padding:1.4rem; border-radius:12px; border:2px solid {bd1};">
                    <div style="font-size:0.9rem; font-weight:bold; color:{tc1}; margin-bottom:0.4rem;">
                        ⚡ Scenario 1 — Grid (current)
                    </div>
                    <div style="font-size:0.75rem; color:#555; margin-bottom:0.5rem;">
                        Electric boiler + grid electricity &nbsp;|&nbsp; EF = {grid_ef} kg CO₂/kWh
                    </div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Break-even electricity limit:</div>
                    <div style="font-size:1.8rem; font-weight:bold; color:{tc1};">{s1_max_mwh_t:.1f} MWh/t</div>
                    <div style="font-size:0.72rem; color:#777; margin-bottom:0.4rem;">Input: {s1_elec_mwh_t:.1f} MWh/t — {ou1}</div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Net CO₂ removed / week:</div>
                    <div style="font-size:1.3rem; font-weight:bold; color:{tc1};">{s1_net:+,.0f} kg</div>
                </div>
                """, unsafe_allow_html=True)

            # S2 card
            tc2, bg2, bd2 = _card_colors(s2_net)
            with sc2:
                st.markdown(f"""
                <div style="background:{bg2}; padding:1.4rem; border-radius:12px; border:2px solid {bd2};">
                    <div style="font-size:0.9rem; font-weight:bold; color:{tc2}; margin-bottom:0.4rem;">
                        🌿 Scenario 2 — Geo Steam + Grid Elec
                    </div>
                    <div style="font-size:0.75rem; color:#555; margin-bottom:0.5rem;">
                        Steam: {STEAM_EF_PER_KG:.5f} kg CO₂/kg &nbsp;|&nbsp; Electricity: {grid_ef} kg CO₂/kWh
                    </div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Max electricity (at current steam):</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{tc2};">{s2_max_elec_mwh_t:.1f} MWh/t</div>
                    <div style="font-size:0.75rem; color:#666; margin-top:0.3rem;">Max steam (at current electricity):</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{tc2};">{s2_max_steam_kgkgco2:.1f} kg/kg CO₂</div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Net CO₂ removed / week:</div>
                    <div style="font-size:1.3rem; font-weight:bold; color:{tc2};">{s2_net:+,.0f} kg</div>
                </div>
                """, unsafe_allow_html=True)

            # S3 card
            tc3, bg3, bd3 = _card_colors(s3_net)
            with sc3:
                st.markdown(f"""
                <div style="background:{bg3}; padding:1.4rem; border-radius:12px; border:2px solid {bd3};">
                    <div style="font-size:0.9rem; font-weight:bold; color:{tc3}; margin-bottom:0.4rem;">
                        ♻️ Scenario 3 — Geo Steam + Geo Elec
                    </div>
                    <div style="font-size:0.75rem; color:#555; margin-bottom:0.5rem;">
                        Steam: {STEAM_EF_PER_KG:.5f} kg CO₂/kg &nbsp;|&nbsp; Electricity: {GEO_ELEC_EF} kg CO₂/kWh
                    </div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Max electricity (at current steam):</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{tc3};">{s3_max_elec_mwh_t:.1f} MWh/t</div>
                    <div style="font-size:0.75rem; color:#666; margin-top:0.3rem;">Max steam (at current electricity):</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{tc3};">{s3_max_steam_kgkgco2:.1f} kg/kg CO₂</div>
                    <hr style="margin:0.4rem 0; border-color:#ddd;">
                    <div style="font-size:0.75rem; color:#666;">Net CO₂ removed / week:</div>
                    <div style="font-size:1.3rem; font-weight:bold; color:{tc3};">{s3_net:+,.0f} kg</div>
                </div>
                """, unsafe_allow_html=True)

        # ── Budget breakdown ──────────────────────────────────────────────────────────
        with st.expander("📐 Where the carbon budget comes from", expanded=False):
            st.markdown(f"""
| | kg CO₂eq / week | Notes |
|---|---|---|
| CO₂ captured (at {annual_target_t:.0f} t/yr) | **{weekly_target_kg:.0f} kg** | {annual_target_t:.0f} t ÷ 52 weeks — your "income" |
| − Facility build cost (embodied) | **{embodied_weekly:.1f} kg** | 67.3 t over 10 years — fixed every week |
| − Chemical wear (sorbent) | **{sorbent_weekly:.1f} kg** | 0.1522 kg CO₂eq per kg CO₂ captured |
| = Energy budget | **{ops_budget:.1f} kg** | Maximum all energy can emit to stay net positive |
            """)

        # ── Scenario 1 slider ──────────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Scenario 1 — Sensitivity to electricity intensity")
        st.caption(
            f"Break-even limit is **{s1_max_mwh_t:.1f} MWh/t**. "
            "Slide to see what happens at different intensities."
        )

        slider_max_s1 = max(50.0, round(s1_max_mwh_t * 2, 0))
        trial_s1_mwh_t = st.slider(
            "Electricity intensity — Scenario 1 (MWh / tonne CO₂)",
            min_value=0.0, max_value=slider_max_s1,
            value=min(s1_elec_mwh_t, slider_max_s1),
            step=0.5,
            help="Total electrical energy per tonne CO₂ (boiler + all loads).",
        )

        trial_s1_kwh  = trial_s1_mwh_t * 1000 * weekly_target_t
        trial_s1_emis = trial_s1_kwh * grid_ef
        trial_s1_net  = ops_budget - trial_s1_emis
        vs_s1 = trial_s1_mwh_t - s1_max_mwh_t
        nc_s1 = "#2e7d32" if trial_s1_net >= 0 else "#c62828"
        lc_s1 = "#2e7d32" if vs_s1 <= 0 else "#c62828"

        r1, r2, r3 = st.columns(3)
        with r1:
            st.markdown(f"""
            <div style="background:#fff3e0; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.75rem; color:#666;">Electricity intensity</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{lc_s1};">{trial_s1_mwh_t:.1f} MWh/t</div>
                <div style="font-size:0.7rem; color:{lc_s1};">{'✅ Under limit' if vs_s1 <= 0 else f'❌ {vs_s1:.1f} MWh/t over'}</div>
            </div>""", unsafe_allow_html=True)
        with r2:
            st.markdown(f"""
            <div style="background:#fff3e0; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.75rem; color:#666;">Energy emissions</div>
                <div style="font-size:1.3rem; font-weight:bold; color:#444;">{trial_s1_emis:.1f} kg/wk</div>
                <div style="font-size:0.7rem; color:#888;">Budget: {ops_budget:.1f} kg/wk</div>
            </div>""", unsafe_allow_html=True)
        with r3:
            st.markdown(f"""
            <div style="background:#fff3e0; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.75rem; color:#666;">Net CO₂ removed</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{nc_s1};">{trial_s1_net:+,.0f} kg/wk</div>
                <div style="font-size:0.7rem; color:{nc_s1};">{'✓ Net positive' if trial_s1_net >= 0 else '✗ Net emitting'}</div>
            </div>""", unsafe_allow_html=True)

        # ── Scenarios 2 & 3 sliders ───────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### Scenarios 2 & 3 — Sensitivity to electricity and steam intensity")
        st.caption(
            f"Steam EF = {STEAM_EF_PER_KG:.5f} kg CO₂/kg (0.886 g CO₂/MJ × 2133.4 kJ/kg at 4 bara). "
            "Adjust both sliders to compare S2 and S3."
        )

        sl_col1, sl_col2 = st.columns(2)
        with sl_col1:
            trial_s23_elec = st.slider(
                "Electricity intensity — Scenarios 2 & 3 (MWh / tonne CO₂)",
                min_value=0.0, max_value=20.0,
                value=s23_elec_mwh_t, step=0.5,
                help="Non-boiler electrical loads per tonne CO₂.",
            )
        with sl_col2:
            trial_steam = st.slider(
                "Steam intensity — Scenarios 2 & 3 (kg steam / kg CO₂)",
                min_value=0.0, max_value=500.0,
                value=steam_kg_per_kgco2, step=0.5,
                help="Geothermal steam per kg CO₂ captured.",
            )

        t_elec_kwh   = trial_s23_elec * 1000 * weekly_target_t
        t_steam_emis = trial_steam * weekly_target_kg * STEAM_EF_PER_KG
        t_s2_net = ops_budget - (t_elec_kwh * grid_ef     + t_steam_emis)
        t_s3_net = ops_budget - (t_elec_kwh * GEO_ELEC_EF + t_steam_emis)
        nc_s2 = "#2e7d32" if t_s2_net >= 0 else "#c62828"
        nc_s3 = "#2e7d32" if t_s3_net >= 0 else "#c62828"
        vs_steam = trial_steam - s2_max_steam_kgkgco2
        sc_steam = "#2e7d32" if vs_steam <= 0 else "#c62828"
        vs_elec  = trial_s23_elec - s1_max_mwh_t
        ec       = "#2e7d32" if vs_elec <= 0 else "#c62828"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f"""
            <div style="background:#e8f5e9; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.72rem; color:#666;">S2 net CO₂ removed</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{nc_s2};">{t_s2_net:+,.0f} kg/wk</div>
                <div style="font-size:0.68rem; color:{nc_s2};">{'✓ Positive' if t_s2_net >= 0 else '✗ Emitting'}</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""
            <div style="background:#e3f2fd; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.72rem; color:#666;">S3 net CO₂ removed</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{nc_s3};">{t_s3_net:+,.0f} kg/wk</div>
                <div style="font-size:0.68rem; color:{nc_s3};">{'✓ Positive' if t_s3_net >= 0 else '✗ Emitting'}</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""
            <div style="background:#e8f5e9; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.72rem; color:#666;">Steam vs S2 limit ({s2_max_steam_kgkgco2:.1f} kg/kg)</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{sc_steam};">{trial_steam:.1f} kg/kg</div>
                <div style="font-size:0.68rem; color:{sc_steam};">{'✅ Under' if vs_steam <= 0 else f'❌ {vs_steam:.1f} over'}</div>
            </div>""", unsafe_allow_html=True)
        with c4:
            st.markdown(f"""
            <div style="background:#e3f2fd; padding:0.9rem; border-radius:8px; text-align:center;">
                <div style="font-size:0.72rem; color:#666;">Elec vs S1 limit ({s1_max_mwh_t:.1f} MWh/t)</div>
                <div style="font-size:1.3rem; font-weight:bold; color:{ec};">{trial_s23_elec:.1f} MWh/t</div>
                <div style="font-size:0.68rem; color:{ec};">{'✅ Under' if vs_elec <= 0 else f'❌ {vs_elec:.1f} over'}</div>
            </div>""", unsafe_allow_html=True)
    with tab5:
        st.markdown("### 🏆 Credit Target Tracker")
        st.markdown(
            "Track progress toward the year's goal of **10 carbon credits** "
            "(1 credit = 1 tonne net CO₂ removed)."
        )

        CREDIT_TARGET_KG = 10_000.0  # 10 credits × 1,000 kg each

        # Build chronological series from stored net_removal_kg
        historical = []
        for s in reversed(raw_summaries):
            net_kg = getattr(s, "net_removal_kg", None)
            if net_kg is not None:
                historical.append({
                    "week": f"{s.year}-W{s.week_number:02d}",
                    "net_removal_kg": float(net_kg),
                })

        if not historical:
            st.warning("No weekly summary data available. Import SCADA data and save weekly summaries first.")
        else:
            cumulative = 0.0
            for row in historical:
                cumulative += row["net_removal_kg"]
                row["cumulative_kg"] = cumulative

            total_cumulative = cumulative
            n_weeks = len(historical)
            avg_weekly = total_cumulative / n_weeks if n_weeks > 0 else 0.0
            remaining_kg = max(CREDIT_TARGET_KG - total_cumulative, 0.0)
            pct_complete = min(total_cumulative / CREDIT_TARGET_KG * 100, 100.0)
            weeks_to_target = remaining_kg / avg_weekly if avg_weekly > 0 else None

            # KPI cards
            kpi1, kpi2, kpi3, kpi4 = st.columns(4)
            with kpi1:
                c = "#2e7d32" if total_cumulative > 0 else "#c62828"
                st.markdown(f"""
                <div style="background:#e8f5e9; padding:1rem; border-radius:8px; border-left:4px solid #28A745;">
                    <div style="font-size:0.8rem; color:#666;">Cumulative Net Removal</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{c};">{total_cumulative:.0f} kg</div>
                    <div style="font-size:0.75rem; color:#888;">{total_cumulative / 1000:.3f} tCO₂</div>
                </div>
                """, unsafe_allow_html=True)
            with kpi2:
                st.markdown(f"""
                <div style="background:#e3f2fd; padding:1rem; border-radius:8px; border-left:4px solid #2196F3;">
                    <div style="font-size:0.8rem; color:#666;">Avg Weekly Run Rate</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:#1565c0;">{avg_weekly:.0f} kg/wk</div>
                    <div style="font-size:0.75rem; color:#888;">across {n_weeks} weeks</div>
                </div>
                """, unsafe_allow_html=True)
            with kpi3:
                if weeks_to_target is not None:
                    wc = "#2e7d32" if weeks_to_target < 52 else "#ef6c00"
                    wlabel = f"{weeks_to_target:.0f} weeks"
                else:
                    wc, wlabel = "#c62828", "N/A"
                st.markdown(f"""
                <div style="background:#fff3e0; padding:1rem; border-radius:8px; border-left:4px solid #FD7E14;">
                    <div style="font-size:0.8rem; color:#666;">Weeks to 10-Credit Target</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{wc};">{wlabel}</div>
                    <div style="font-size:0.75rem; color:#888;">{remaining_kg:.0f} kg remaining</div>
                </div>
                """, unsafe_allow_html=True)
            with kpi4:
                gc = "#28A745" if pct_complete >= 100 else ("#FD7E14" if pct_complete > 10 else "#DC3545")
                st.markdown(f"""
                <div style="background:#f3e5f5; padding:1rem; border-radius:8px; border-left:4px solid #9C27B0;">
                    <div style="font-size:0.8rem; color:#666;">Progress to 10 Credits</div>
                    <div style="font-size:1.5rem; font-weight:bold; color:{gc};">{pct_complete:.1f}%</div>
                    <div style="font-size:0.75rem; color:#888;">Target: 10,000 kg</div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown("")

            # Gauge
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=total_cumulative,
                delta={"reference": CREDIT_TARGET_KG, "increasing": {"color": "#28A745"}},
                gauge={
                    "axis": {"range": [0, CREDIT_TARGET_KG]},
                    "bar": {"color": "#28A745" if total_cumulative >= 0 else "#DC3545"},
                    "steps": [
                        {"range": [0, CREDIT_TARGET_KG * 0.33], "color": "#ffebee"},
                        {"range": [CREDIT_TARGET_KG * 0.33, CREDIT_TARGET_KG * 0.66], "color": "#fff3e0"},
                        {"range": [CREDIT_TARGET_KG * 0.66, CREDIT_TARGET_KG], "color": "#e8f5e9"},
                    ],
                    "threshold": {
                        "line": {"color": "#1565c0", "width": 4},
                        "thickness": 0.75,
                        "value": CREDIT_TARGET_KG,
                    },
                },
                title={"text": "Net CO₂ Removed (kg)"},
                number={"suffix": " kg"},
            ))
            fig_gauge.update_layout(height=280, template="plotly_white")
            st.plotly_chart(fig_gauge, width="stretch")

            # Cumulative line chart
            weeks_labels = [r["week"] for r in historical]
            cumulatives = [r["cumulative_kg"] for r in historical]
            weekly_nets = [r["net_removal_kg"] for r in historical]

            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=weeks_labels, y=cumulatives,
                mode="lines+markers", name="Cumulative Net Removal",
                line={"color": "#28A745", "width": 2}, marker={"size": 6},
            ))
            fig_cum.add_hline(
                y=CREDIT_TARGET_KG, line_dash="dash", line_color="#1565c0",
                annotation_text="10-Credit Target (10,000 kg)", annotation_position="top left",
            )
            fig_cum.add_hline(y=0, line_dash="dot", line_color="#999")
            fig_cum.update_layout(
                title="Cumulative Net CO₂ Removal vs 10-Credit Target",
                xaxis_title="Week", yaxis_title="Cumulative Net Removal (kg)",
                template="plotly_white", height=370,
            )
            st.plotly_chart(fig_cum, width="stretch")

            # Weekly bar chart
            bar_colors = ["#28A745" if v >= 0 else "#DC3545" for v in weekly_nets]
            fig_weekly = go.Figure(go.Bar(
                x=weeks_labels, y=weekly_nets,
                marker_color=bar_colors, name="Weekly Net Removal",
            ))
            fig_weekly.add_hline(y=0, line_dash="dash", line_color="gray")
            fig_weekly.update_layout(
                title="Weekly Net Removal",
                xaxis_title="Week", yaxis_title="Net CO₂ Removal (kg)",
                template="plotly_white", height=310,
            )
            st.plotly_chart(fig_weekly, width="stretch")

            # Status message
            design_weekly_kg = (25 * 1000) / 52  # 25 t/yr design capacity
            if avg_weekly <= 0:
                st.error(
                    "Current operations are net emitting on average. "
                    "No carbon credits can be issued at this run rate."
                )
                max_ops_budget = max(design_weekly_kg - get_weekly_embodied_kg() - SORBENT_RATE * design_weekly_kg, 0)
                max_grid_be = max_ops_budget / (grid_ef * design_weekly_kg) if design_weekly_kg > 0 else 0
                st.markdown(f"""
                **To become net positive**, total weekly emissions must be below **{design_weekly_kg:.0f} kg** at design capture (25 t/yr).

                | Source | Weekly kg | Notes |
                |---|---|---|
                | Fixed embodied | {get_weekly_embodied_kg():.0f} | Cannot reduce without plant redesign |
                | Sorbent degradation | {SORBENT_RATE * design_weekly_kg:.0f} | Reduces if sorption efficiency improves |
                | Operational budget | {max_ops_budget:.0f} | Energy must emit less than this |
                | Grid break-even intensity | {max_grid_be:.1f} kWh/kgCO₂ | vs LCA current: 30 kWh/kgCO₂ |

                **Key lever:** Switch to geothermal steam — removes ~70% of operational emissions.
                See the **Break-even Targets** tab for full analysis.
                """)
            else:
                eta = f"**{weeks_to_target:.0f} weeks** ({weeks_to_target / 52:.1f} years)" if weeks_to_target else "on track"
                st.success(
                    f"At the current run rate of **{avg_weekly:.0f} kg/week**, "
                    f"the 10-credit target would be reached in approximately {eta}."
                )

            st.info(
                "ℹ️ Net removal values here come from stored weekly summaries. "
                "Sorbent degradation is applied in the Historical What-If tab only."
            )


if __name__ == "__main__":
    main()
