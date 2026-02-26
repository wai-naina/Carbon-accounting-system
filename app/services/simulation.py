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
        # Get emission factors
        grid_ef = get_emission_factor(session, "grid_emission_factor", 0.049)
        # Geothermal steam EF is per kg of steam, not per kWh
        # Default: ~0.005 kg CO2 per kg steam (fugitive emissions from geothermal wells)
        geothermal_steam_ef = get_emission_factor(session, "geothermal_steam_ef_per_kg", 0.005)
        
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
                
                # Proportional allocation of liquefied and embodied
                total_cycles = s.total_cycles or 1
                proportion = pair_metrics["cycles"] / total_cycles
                
                # Proportional liquefied
                liq = s.liquefied_co2_kg or 0
                total_bag = s.total_bag_co2_kg or 0
                if liq > 0 and total_bag > 0:
                    fs.liquefied_co2_kg = liq * (pair_metrics["bag_co2_kg"] / total_bag)
                else:
                    fs.liquefied_co2_kg = 0
                
                fs.total_embodied_emissions_kg = (s.total_embodied_emissions_kg or 0) * proportion
                summaries.append(fs)
            else:
                summaries.append(s)
    finally:
        session.close()

    # Configuration display
    st.markdown("### ⚙️ Emission Factors")
    ef_col1, ef_col2 = st.columns(2)
    
    with ef_col1:
        st.markdown(f"""
        <div style="background:#fff3e0; padding:1rem; border-radius:8px; border-left:4px solid #FD7E14;">
            <div style="font-size:0.8rem; color:#666;">Kenya Grid Electricity</div>
            <div style="font-size:1.5rem; font-weight:bold; color:#ef6c00;">{grid_ef} kg CO₂/kWh</div>
            <div style="font-size:0.75rem; color:#888;">Source: Kenya Power 2024</div>
        </div>
        """, unsafe_allow_html=True)
    
    with ef_col2:
        st.markdown(f"""
        <div style="background:#e8f5e9; padding:1rem; border-radius:8px; border-left:4px solid #28A745;">
            <div style="font-size:0.8rem; color:#666;">Geothermal Steam</div>
            <div style="font-size:1.5rem; font-weight:bold; color:#2e7d32;">{geothermal_steam_ef} kg CO₂/kg steam</div>
            <div style="font-size:0.75rem; color:#888;">Fugitive emissions from geothermal wells</div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    # Tabs for different analysis modes
    tab1, tab2, tab3 = st.tabs(["🧮 Custom Calculator", "📊 Historical What-If", "📈 Monte Carlo"])

    with tab1:
        st.markdown("### Custom Scenario Calculator")
        st.markdown("Enter energy consumption values to compare current vs geothermal scenarios.")
        
        input_col1, input_col2 = st.columns(2)
        
        with input_col1:
            st.markdown("**Current Operations (Grid)**")
            thermal_kwh = st.number_input("Boiler Energy (kWh)", min_value=0.0, value=3540.0, step=100.0,
                                          help="Electricity used by boiler to generate steam")
            auxiliary_kwh = st.number_input("Non-thermal Energy (kWh)", min_value=0.0, value=1460.0, step=100.0,
                                            help="Fans, SRV/LRVP, CT, Liquefaction")
            steam_kg = st.number_input("Steam Used (kg)", min_value=0.0, value=5000.0, step=100.0,
                                       help="From SCADA - this will be used for geothermal calculation")
            total_kwh = thermal_kwh + auxiliary_kwh
            st.caption(f"Total Energy: {total_kwh:.0f} kWh")
        
        with input_col2:
            st.markdown("**CO₂ Capture & Emissions**")
            collected_kg = st.number_input("Collected CO₂ (kg)", min_value=0.0, value=500.0, step=10.0, 
                                           help="Use liquefied if available, otherwise bag/collected CO₂")
            embodied_kg = st.number_input("Weekly Embodied Emissions (kg)", min_value=0.0, value=55.28, step=1.0)

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
                        <span style="color:#666;">Non-thermal:</span> 
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
                        <span style="color:#666;">Non-thermal:</span> 
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
            
            categories = ["Thermal", "Non-thermal", "Embodied", "Total"]
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
        st.markdown("See how your historical data would look with geothermal steam.")
        
        if not summaries:
            st.warning("No weekly data available. Import SCADA data first.")
        else:
            # Build comparison table
            rows = []
            for s in summaries[:12]:  # Last 12 weeks
                thermal = s.thermal_energy_kwh or 0
                auxiliary = s.auxiliary_energy_kwh or 0
                steam = s.total_steam_kg or 0
                embodied = s.total_embodied_emissions_kg or 0
                liquefied = s.liquefied_co2_kg or 0
                bag = s.total_bag_co2_kg or 0
                
                # Use collected (bag) CO2 if liquefied is not available
                collected_co2 = liquefied if liquefied > 0 else bag
                
                if thermal + auxiliary > 0:
                    results = calculate_geothermal_scenario(
                        thermal, auxiliary, steam, grid_ef, geothermal_steam_ef, embodied, collected_co2
                    )
                    
                    rows.append({
                        "Week": f"{s.year}-W{s.week_number:02d}",
                        "Collected": f"{collected_co2:.1f}",
                        "Steam (kg)": f"{steam:.0f}",
                        "Current Net": results["current"]["net_removal"],
                        "Geo Net": results["geothermal"]["net_removal"],
                        "Improvement": results["improvement"]["net_improvement_kg"],
                        "Current Status": "✅" if results["current"]["is_net_positive"] else "❌",
                        "Geo Status": "✅" if results["geothermal"]["is_net_positive"] else "❌",
                    })
            
            if rows:
                df = pd.DataFrame(rows)
                
                # Summary metrics
                sum_col1, sum_col2, sum_col3 = st.columns(3)
                
                with sum_col1:
                    current_positive = sum(1 for r in rows if r["Current Status"] == "✅")
                    st.metric("Weeks Net Positive (Current)", f"{current_positive}/{len(rows)}")
                
                with sum_col2:
                    geo_positive = sum(1 for r in rows if r["Geo Status"] == "✅")
                    st.metric("Weeks Net Positive (Geothermal)", f"{geo_positive}/{len(rows)}")
                
                with sum_col3:
                    total_improvement = sum(r["Improvement"] for r in rows)
                    st.metric("Total Net Improvement", f"+{total_improvement:.1f} kg")
                
                # Chart
                fig = go.Figure()
                
                fig.add_trace(go.Bar(
                    name="Current (Grid)",
                    x=df["Week"],
                    y=df["Current Net"],
                    marker_color="#FD7E14",
                ))
                
                fig.add_trace(go.Bar(
                    name="Geothermal Scenario",
                    x=df["Week"],
                    y=df["Geo Net"],
                    marker_color="#28A745",
                ))
                
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                
                fig.update_layout(
                    title="Net Removal: Current vs Geothermal Scenario",
                    yaxis_title="Net CO₂ Removal (kg)",
                    template="plotly_white",
                    barmode="group",
                    height=450,
                )
                
                st.plotly_chart(fig, width="stretch")
                
                # Table
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
            aux_min = st.number_input("Min electrical kWh", value=1000.0, step=100.0)
            aux_max = st.number_input("Max electrical kWh", value=2000.0, step=100.0)
        
        with param_col2:
            st.markdown("**Steam (for Geothermal)**")
            steam_min = st.number_input("Min Steam kg", value=4000.0, step=100.0)
            steam_max = st.number_input("Max Steam kg", value=8000.0, step=100.0)
            embodied = st.number_input("Embodied Emissions kg", value=55.28, step=1.0)
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


if __name__ == "__main__":
    main()
