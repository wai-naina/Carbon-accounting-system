from datetime import date
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.auth.authorization import require_admin
from app.components.branding import get_brand_css, render_logo
from app.config import load_config
from app.database.connection import get_session, init_db
from app.database.models import EmbodiedInfrastructure, EmbodiedSorbent, SystemConfig
from app.services.embodied_import import (
    INFRA_ALIASES,
    SORBENT_ALIASES,
    parse_date,
    parse_float,
    parse_int,
    parse_octavia_sorbent_sheet,
    parse_octavia_transport_sheet,
    parse_octavia_zone_sheet,
    suggest_mapping,
)


def get_config(session, key: str, default: float) -> float:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        return default
    try:
        return float(config.value)
    except ValueError:
        return default


def set_config(session, key: str, value: float, description: str) -> None:
    config = session.query(SystemConfig).filter(SystemConfig.key == key).first()
    if not config:
        config = SystemConfig(key=key, value=str(value), value_type="float", description=description)
        session.add(config)
    else:
        config.value = str(value)
    session.commit()


def main() -> None:
    st.set_page_config(page_title="Configuration - Octavia CAS", page_icon="⚙️", layout="wide")
    init_db()
    if not require_admin():
        return

    # Apply brand CSS and logo
    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("⚙️ Configuration & LCA Management")
    st.markdown("Manage emission factors and embodied emissions from Life Cycle Assessment")

    session = get_session()
    try:
        settings = load_config()
        
        # Get current emission factors
        grid_ef = get_config(session, "grid_emission_factor", 0.049)
        geo_ef = get_config(session, "geothermal_emission_factor", 0.008)
        
        # Get current embodied emissions summary
        infra_items = session.query(EmbodiedInfrastructure).all()
        sorbent_batches = session.query(EmbodiedSorbent).all()
        
        total_infra_embodied = sum(i.embodied_co2_kg or 0 for i in infra_items)
        total_infra_weekly = sum(i.weekly_charge_kg or 0 for i in infra_items)
        total_sorbent_embodied = sum(b.total_embodied_kg or 0 for b in sorbent_batches if b.is_active)
        total_sorbent_weekly = sum(b.weekly_charge_kg or 0 for b in sorbent_batches if b.is_active)

        # Overview Cards
        st.markdown("### 📊 Current Configuration Overview")
        
        overview_col1, overview_col2, overview_col3, overview_col4 = st.columns(4)
        
        with overview_col1:
            st.markdown(f"""
            <div style="background:#fff3e0; padding:1rem; border-radius:8px; border-left:4px solid #FD7E14;">
                <div style="font-size:0.8rem; color:#666;">Grid Emission Factor</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#ef6c00;">{grid_ef} kg/kWh</div>
            </div>
            """, unsafe_allow_html=True)
        
        with overview_col2:
            st.markdown(f"""
            <div style="background:#e8f5e9; padding:1rem; border-radius:8px; border-left:4px solid #28A745;">
                <div style="font-size:0.8rem; color:#666;">Geothermal Emission Factor</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#2e7d32;">{geo_ef} kg/kWh</div>
            </div>
            """, unsafe_allow_html=True)
        
        with overview_col3:
            st.markdown(f"""
            <div style="background:#e3f2fd; padding:1rem; border-radius:8px; border-left:4px solid #2196F3;">
                <div style="font-size:0.8rem; color:#666;">Weekly Infra Charge</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#1565c0;">{total_infra_weekly:.2f} kg</div>
                <div style="font-size:0.75rem; color:#888;">{len(infra_items)} items</div>
            </div>
            """, unsafe_allow_html=True)
        
        with overview_col4:
            st.markdown(f"""
            <div style="background:#fce4ec; padding:1rem; border-radius:8px; border-left:4px solid #E91E63;">
                <div style="font-size:0.8rem; color:#666;">Weekly Sorbent Charge</div>
                <div style="font-size:1.5rem; font-weight:bold; color:#c2185b;">{total_sorbent_weekly:.2f} kg</div>
                <div style="font-size:0.75rem; color:#888;">{len([b for b in sorbent_batches if b.is_active])} active batches</div>
            </div>
            """, unsafe_allow_html=True)
        
        total_weekly = total_infra_weekly + total_sorbent_weekly
        st.info(f"📌 **Total Weekly Embodied Charge:** {total_weekly:.2f} kg CO₂/week")

        st.divider()

        # Tabs for different configuration sections
        tab1, tab2, tab3, tab4 = st.tabs([
            "⚡ Emission Factors", "🏗️ Infrastructure", "🧪 Sorbent Batches", "📤 Excel Import"
        ])

        with tab1:
            st.markdown("### Emission Factor Configuration")
            st.markdown("""
            Configure the emission factors for different energy sources. These are used to calculate 
            operational emissions from energy consumption.
            """)
            
            ef_col1, ef_col2 = st.columns(2)
            
            with ef_col1:
                st.markdown("#### Kenya Grid Electricity")
                new_grid = st.number_input(
                    "Grid EF (kg CO₂/kWh)", 
                    value=grid_ef, 
                    step=0.001, 
                    format="%.4f",
                    help="Emission factor for Kenya Power grid electricity"
                )
                st.caption("Source: Kenya Power & Lighting 2024")
            
            with ef_col2:
                st.markdown("#### Geothermal Steam")
                new_geo = st.number_input(
                    "Geothermal EF (kg CO₂/kWh)", 
                    value=geo_ef, 
                    step=0.001, 
                    format="%.4f",
                    help="Emission factor for geothermal steam (Olkaria)"
                )
                st.caption("Source: Kenya Geothermal - IPCC 2023")

            if st.button("💾 Save Emission Factors", type="primary"):
                set_config(session, "grid_emission_factor", new_grid, "Kenya grid EF (kg CO2/kWh)")
                set_config(session, "geothermal_emission_factor", new_geo, "Geothermal EF (kg CO2/kWh)")
                st.success("✅ Emission factors saved!")
                st.rerun()

        with tab2:
            st.markdown("### Infrastructure Embodied Emissions")
            st.markdown("Track embodied emissions from plant infrastructure (10-year lifetime)")
            
            # Summary by zone
            if infra_items:
                zone_data = {}
                for item in infra_items:
                    zone = item.zone or "Other"
                    if zone not in zone_data:
                        zone_data[zone] = {"count": 0, "embodied": 0, "weekly": 0}
                    zone_data[zone]["count"] += 1
                    zone_data[zone]["embodied"] += item.embodied_co2_kg or 0
                    zone_data[zone]["weekly"] += item.weekly_charge_kg or 0
                
                # Zone summary chart
                fig = go.Figure(data=[go.Pie(
                    labels=list(zone_data.keys()),
                    values=[z["embodied"] for z in zone_data.values()],
                    hole=0.4,
                    textinfo="label+percent",
                )])
                fig.update_layout(
                    title="Embodied Emissions by Zone",
                    height=350,
                    template="plotly_white",
                )
                st.plotly_chart(fig, width="stretch")
                
                # Data table
                st.dataframe(
                    [
                        {
                            "Zone": i.zone,
                            "Item": i.item,
                            "Weight (kg)": f"{i.weight_kg or 0:,.1f}",
                            "EF (kg CO₂/kg)": f"{i.emission_factor or 0:.2f}",
                            "Embodied (kg CO₂)": f"{i.embodied_co2_kg or 0:,.1f}",
                            "Weekly (kg CO₂)": f"{i.weekly_charge_kg or 0:.3f}",
                        }
                        for i in infra_items
                    ],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.warning("No infrastructure items configured. Import LCA data below.")
            
            # Add new item form
            with st.expander("➕ Add Infrastructure Item"):
                with st.form("infra_form"):
                    form_col1, form_col2 = st.columns(2)
                    with form_col1:
                        zone = st.text_input("Zone", placeholder="e.g., Zone 1: Capture")
                        item = st.text_input("Item", placeholder="e.g., Container")
                        weight_kg = st.number_input("Weight (kg)", min_value=0.0, step=1.0)
                    with form_col2:
                        emission_factor = st.number_input("Emission Factor (kg CO₂/kg)", min_value=0.0, step=0.01)
                        lifetime_years = st.number_input("Lifetime (years)", min_value=1, step=1, value=10)
                        notes = st.text_area("Notes", value="")
                    
                    submitted = st.form_submit_button("Add Item", type="primary")
                    if submitted:
                        if not zone or not item:
                            st.error("Zone and item are required.")
                        else:
                            embodied = weight_kg * emission_factor
                            weekly_charge = embodied / (lifetime_years * 52)
                            session.add(EmbodiedInfrastructure(
                                zone=zone, item=item, weight_kg=weight_kg,
                                emission_factor=emission_factor, embodied_co2_kg=embodied,
                                lifetime_years=lifetime_years, weekly_charge_kg=weekly_charge,
                                notes=notes or None, updated_by=st.session_state.get("user_id"),
                            ))
                            session.commit()
                            st.success("✅ Infrastructure item added!")
                            st.rerun()
            
            # Clear all button
            if infra_items and st.button("🗑️ Clear All Infrastructure Data", type="secondary"):
                session.query(EmbodiedInfrastructure).delete()
                session.commit()
                st.success("Infrastructure data cleared.")
                st.rerun()

        with tab3:
            st.markdown("### Sorbent Batch Embodied Emissions")
            st.markdown("Track embodied emissions from sorbent materials (3-year lifetime)")
            
            if sorbent_batches:
                for batch in sorbent_batches:
                    status = "🟢 Active" if batch.is_active else "⚪ Inactive"
                    with st.expander(f"Batch #{batch.batch_number} - {status} ({batch.start_date})"):
                        b_col1, b_col2, b_col3 = st.columns(3)
                        
                        with b_col1:
                            st.markdown("**Materials**")
                            st.write(f"- Alumina: {batch.alumina_kg or 0:,.1f} kg")
                            st.write(f"- PEI: {batch.pei_kg or 0:,.1f} kg")
                            st.write(f"- Methanol: {batch.methanol_kg or 0:,.1f} kg")
                        
                        with b_col2:
                            st.markdown("**Embodied Emissions**")
                            st.write(f"- Production: {batch.production_embodied_kg or 0:,.1f} kg CO₂")
                            st.write(f"- End of Life: {batch.eol_embodied_kg or 0:,.1f} kg CO₂")
                            st.write(f"- **Total: {batch.total_embodied_kg or 0:,.1f} kg CO₂**")
                        
                        with b_col3:
                            st.markdown("**Weekly Charge**")
                            st.write(f"- Weekly: {batch.weekly_charge_kg or 0:.2f} kg CO₂")
                            st.write(f"- Lifetime: {batch.lifetime_weeks or 156} weeks")
                            
                            if batch.is_active:
                                if st.button(f"Deactivate Batch {batch.batch_number}"):
                                    batch.is_active = False
                                    session.commit()
                                    st.rerun()
            else:
                st.warning("No sorbent batches configured. Import LCA data or add manually below.")
            
            # Add new batch form
            with st.expander("➕ Add Sorbent Batch"):
                settings = load_config()
                default_alumina = settings.get("emission_factors", "materials", "alumina", default=1.91)
                default_pei = settings.get("emission_factors", "materials", "pei", default=11.05)
                default_methanol = settings.get("emission_factors", "materials", "methanol", default=0.92)
                default_eol = settings.get("emission_factors", "eol", "combustion", default=1.29)

                with st.form("sorbent_form"):
                    s_col1, s_col2 = st.columns(2)
                    with s_col1:
                        batch_number = st.number_input("Batch Number", min_value=1, step=1)
                        start_date = st.date_input("Start Date", value=date.today())
                        alumina_kg = st.number_input("Alumina (kg)", min_value=0.0, step=1.0, value=880.0)
                        pei_kg = st.number_input("PEI (kg)", min_value=0.0, step=1.0, value=880.0)
                        methanol_kg = st.number_input("Methanol (kg)", min_value=0.0, step=1.0, value=1000.0)
                    with s_col2:
                        ef_alumina = st.number_input("EF Alumina", value=float(default_alumina), step=0.01)
                        ef_pei = st.number_input("EF PEI", value=float(default_pei), step=0.01)
                        ef_methanol = st.number_input("EF Methanol", value=float(default_methanol), step=0.01)
                        eol_factor = st.number_input("EOL Factor", value=float(default_eol), step=0.01)
                        notes = st.text_area("Notes", value="", key="sorbent_notes")
                    
                    submitted = st.form_submit_button("Add Sorbent Batch", type="primary")
                    if submitted:
                        existing = session.query(EmbodiedSorbent).filter(
                            EmbodiedSorbent.batch_number == int(batch_number)
                        ).first()
                        if existing:
                            st.error("Batch number already exists.")
                        else:
                            production = (alumina_kg * ef_alumina) + (pei_kg * ef_pei) + (methanol_kg * ef_methanol)
                            eol = (alumina_kg + pei_kg + methanol_kg) * eol_factor
                            total = production + eol
                            weekly_charge = total / 156
                            session.add(EmbodiedSorbent(
                                batch_number=int(batch_number), start_date=start_date,
                                alumina_kg=alumina_kg, pei_kg=pei_kg, methanol_kg=methanol_kg,
                                production_embodied_kg=production, eol_embodied_kg=eol,
                                total_embodied_kg=total, weekly_charge_kg=weekly_charge,
                                is_active=True, notes=notes or None,
                                updated_by=st.session_state.get("user_id"),
                            ))
                            session.commit()
                            st.success("✅ Sorbent batch added!")
                            st.rerun()

        with tab4:
            st.markdown("### Import LCA Data from Excel")
            st.markdown("""
            Import embodied emissions data from the Octavia LCA workbook. This will automatically
            parse the zone sheets and extract infrastructure and sorbent data.
            """)
            
            auto_upload = st.file_uploader(
                "Upload Octavia LCA Workbook (.xlsx)",
                type=["xlsx"],
                key="octavia_lca_upload",
            )
            
            if auto_upload:
                st.success("✅ File uploaded successfully!")
                
                import_col1, import_col2 = st.columns(2)
                
                with import_col1:
                    infra_clear = st.checkbox("🗑️ Clear existing infrastructure data", key="auto_clear_infra")
                    sorbent_clear = st.checkbox("🗑️ Clear existing sorbent batches", key="auto_clear_sorbent")
                
                with import_col2:
                    batch_number = st.number_input("Sorbent Batch Number", min_value=1, step=1, value=1, key="auto_batch_number")
                    batch_start = st.date_input("Sorbent Batch Start Date", value=date.today(), key="auto_batch_start")

                if st.button("🚀 Import LCA Data", type="primary", width="stretch"):
                    with st.spinner("Importing LCA data..."):
                        if infra_clear:
                            session.query(EmbodiedInfrastructure).delete()
                        if sorbent_clear:
                            session.query(EmbodiedSorbent).delete()
                        session.commit()

                        infra_rows = []
                        infra_rows += parse_octavia_zone_sheet(auto_upload, "Zone1_Capture", "Zone 1: Capture")
                        infra_rows += parse_octavia_zone_sheet(auto_upload, "Zone2_Processing", "Zone 2: Processing")
                        infra_rows += parse_octavia_zone_sheet(auto_upload, "Zone3_Liquefaction", "Zone 3: Liquefaction")
                        infra_rows += parse_octavia_transport_sheet(auto_upload)

                        for row in infra_rows:
                            lifetime_years = 10
                            embodied = row.get("embodied_co2_kg")
                            weekly_charge = embodied / (lifetime_years * 52) if embodied is not None else None
                            session.add(EmbodiedInfrastructure(
                                zone=row.get("zone") or "Infrastructure",
                                item=row.get("item") or "Unknown",
                                weight_kg=row.get("weight_kg"),
                                emission_factor=row.get("emission_factor"),
                                embodied_co2_kg=embodied,
                                lifetime_years=lifetime_years,
                                weekly_charge_kg=weekly_charge,
                                updated_by=st.session_state.get("user_id"),
                            ))

                        sorbent_data = parse_octavia_sorbent_sheet(auto_upload)
                        sorbent_added = False
                        if sorbent_data:
                            existing = session.query(EmbodiedSorbent).filter(
                                EmbodiedSorbent.batch_number == int(batch_number)
                            ).first()
                            if not existing:
                                lifetime_years = sorbent_data.get("lifetime_years") or 3
                                lifetime_weeks = int(lifetime_years * 52)
                                total_embodied = sorbent_data.get("total_embodied_kg") or 0
                                weekly_charge = total_embodied / lifetime_weeks if lifetime_weeks else None
                                session.add(EmbodiedSorbent(
                                    batch_number=int(batch_number),
                                    start_date=batch_start,
                                    alumina_kg=sorbent_data.get("alumina_kg"),
                                    pei_kg=sorbent_data.get("pei_kg"),
                                    methanol_kg=sorbent_data.get("methanol_kg"),
                                    production_embodied_kg=sorbent_data.get("production_embodied_kg"),
                                    eol_embodied_kg=sorbent_data.get("eol_embodied_kg"),
                                    total_embodied_kg=total_embodied,
                                    lifetime_weeks=lifetime_weeks,
                                    weekly_charge_kg=weekly_charge,
                                    is_active=True,
                                    updated_by=st.session_state.get("user_id"),
                                ))
                                sorbent_added = True
                        
                        session.commit()
                        
                        st.success(f"""
                        ✅ **Import Complete!**
                        - Infrastructure items: {len(infra_rows)}
                        - Sorbent batches: {'1' if sorbent_added else '0'}
                        """)
                        st.balloons()
                        st.rerun()

    finally:
        session.close()


def _index(df: pd.DataFrame, value: str | None) -> int:
    if not value:
        return 0
    try:
        return list(df.columns).index(value) + 1
    except ValueError:
        return 0


if __name__ == "__main__":
    main()
