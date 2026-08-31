import sys
from pathlib import Path
import uuid
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from app.auth.authorization import require_admin
from app.components.branding import get_brand_css, render_logo
from app.database.connection import get_session, init_db
from app.database.models import CarbonNestWeeklySummary, CarbonNestCycleData
from app.services.carbon_nest_aggregation import (
    WEEK_ATTRIBUTION,
    create_or_update_weekly_summary,
    get_filtered_cycles,
    list_week_options,
)
from app.services.carbon_nest_calculations import get_series_display_name, safe_value
from app.services.carbon_nest_import import (
    import_cycles,
    load_cycle_energy,
    load_plant_cycles,
    merge_plant_cycles_energy,
)


def format_week_option(bounds: tuple) -> str:
    start, end = bounds
    return f"{start.strftime('%b %d %H:%M')} → {end.strftime('%b %d %H:%M, %Y')}"


def main() -> None:
    st.set_page_config(page_title="Data Entry - Carbon Nest", page_icon="📥", layout="wide")
    init_db()
    if not require_admin():
        return

    st.markdown(get_brand_css(), unsafe_allow_html=True)
    render_logo(location="sidebar")

    st.title("📥 Carbon Nest — Data Entry")
    st.markdown("Import Carbon Nest cycle & energy exports and enter weekly liquefied CO₂ measurements")
    st.caption(
        "This data is stored completely separately from Miniplant 2.0 — cycle numbers "
        "never collide between the two systems."
    )

    session = get_session()
    try:
        total_cycles = session.query(CarbonNestCycleData).count()
        total_weeks = session.query(CarbonNestWeeklySummary).count()

        from sqlalchemy import func
        cycle_dates = session.query(
            func.min(CarbonNestCycleData.start_time),
            func.max(CarbonNestCycleData.start_time),
        ).first()
    finally:
        session.close()

    st.markdown("### 📊 Data Status")
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Cycles Imported", total_cycles)
    with stat_col2:
        st.metric("Weeks Calculated", total_weeks)
    with stat_col3:
        st.metric("Earliest Cycle", cycle_dates[0].strftime("%Y-%m-%d") if cycle_dates[0] else "No data")
    with stat_col4:
        st.metric("Latest Cycle", cycle_dates[1].strftime("%Y-%m-%d") if cycle_dates[1] else "No data")

    st.divider()

    tab1, tab2, tab3 = st.tabs(["📤 Carbon Nest Import", "✍️ Weekly Entry", "📋 View Data"])

    with tab1:
        st.markdown("### Step 1: Import Carbon Nest Exports")
        st.markdown("""
        Upload the two CSV exports from Carbon Nest.

        **Plant Cycles CSV columns:**
        `Cycle #`, `Module`, `Start Time`, `End Time`, `Type`, `ADS CO2 (kg)`, `ADS Hours`,
        `ADS Lost CO2 (kg)`, `ADS Efficiency`, `ADS Mass Cap`, `ADS Vol Cap`, `DES CO2 (kg)`,
        `DES Hours`, `BAG CO2 (kg)`, `DES Efficiency`, `BAG Efficiency`, `DES Vol Cap`,
        `eTotal kWh`, `Steam (kg)`

        **Cycle Energy CSV columns:**
        `Cycle #`, `Module`, `MWh/tCO2`, `Fans (kWh)`, `CT (kWh)`, `CT Pump (kWh)`,
        `VP402 (kWh)`, `VP501 (kWh)`, `Boiler A (kWh)`, `Boiler B (kWh)`, `Main Utility (kWh)`
        """)

        import_col1, import_col2 = st.columns(2)
        with import_col1:
            st.markdown("**Plant Cycles CSV**")
            cycles_file = st.file_uploader("Upload Plant Cycles", type=["csv"], key="cn_cycles")
        with import_col2:
            st.markdown("**Cycle Energy CSV**")
            energy_file = st.file_uploader("Upload Cycle Energy", type=["csv"], key="cn_energy")

        if cycles_file and energy_file:
            cycles_df, cycle_errors = load_plant_cycles(cycles_file)
            energy_df, energy_errors = load_cycle_energy(energy_file)
            errors = cycle_errors + energy_errors

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.success("✅ Files parsed successfully!")

                preview_col1, preview_col2 = st.columns(2)
                with preview_col1:
                    st.markdown("**Plant Cycles Preview**")
                    st.dataframe(cycles_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(cycles_df)}")
                with preview_col2:
                    st.markdown("**Cycle Energy Preview**")
                    st.dataframe(energy_df.head(), width="stretch")
                    st.caption(f"Total rows: {len(energy_df)}")

                # Series breakdown preview so admins can sanity-check before importing
                series_counts = cycles_df["raw_module"].value_counts()
                st.markdown("#### Detected Modules")
                st.dataframe(series_counts.rename("cycles").reset_index().rename(columns={"index": "Module"}), width="stretch", hide_index=True)

                st.markdown("#### Data Summary (from CSV)")
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    ads_total = cycles_df["ads_co2_kg"].sum() if "ads_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Adsorbed CO₂", f"{ads_total:.1f} kg")
                with sum_col2:
                    des_total = cycles_df["des_co2_kg"].sum() if "des_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Desorbed CO₂", f"{des_total:.1f} kg")
                with sum_col3:
                    bag_total = cycles_df["bag_co2_kg"].sum() if "bag_co2_kg" in cycles_df.columns else 0
                    st.metric("Total Collected CO₂", f"{bag_total:.1f} kg")
                with sum_col4:
                    if "start_time" in cycles_df.columns:
                        min_date = cycles_df["start_time"].min()
                        max_date = cycles_df["start_time"].max()
                        if pd.notna(min_date) and pd.notna(max_date):
                            st.metric("Date Range", f"{min_date.strftime('%m/%d')} - {max_date.strftime('%m/%d')}")

                if st.button("🚀 Import to Carbon Nest Database", type="primary", width="stretch"):
                    merged = merge_plant_cycles_energy(cycles_df, energy_df)
                    session = get_session()
                    try:
                        report = import_cycles(session, merged, import_batch_id=str(uuid.uuid4()))
                    finally:
                        session.close()

                    if report.errors:
                        for err in report.errors:
                            st.error(err)

                    st.success(f"✅ Imported **{report.added}** cycles, skipped {report.skipped} (already imported)")

                    if report.date_range[0] and report.date_range[1]:
                        st.info(f"📅 Date range: {report.date_range[0].date()} to {report.date_range[1].date()}")
                        st.balloons()

    with tab2:
        st.markdown("### Step 2: Calculate Weekly Summary")
        st.markdown("""
        Carbon Nest weeks run **Saturday 18:00 → Saturday 18:00**, matching Athena's
        own weekly report cadence. Select the week, enter the **liquefied CO₂** amount,
        and fill in the utility/standby figures from that week's Athena weekly PDF
        report (SCADA's "Main Utility" export column is known to be incomplete/buggy
        right now, so these are entered by hand until that's fixed).
        """)

        st.markdown("#### Select Week")
        week_options = list_week_options(count_back=12, count_forward=1)
        selected_week_idx = st.selectbox(
            "Week (Saturday 18:00 → Saturday 18:00)",
            options=list(range(len(week_options))),
            format_func=lambda i: format_week_option(week_options[i]),
            index=2,  # most recently COMPLETED week by default (index 0 = next week, 1 = current/in-progress week)
            key="cn_week_select",
        )
        week_start, week_end = week_options[selected_week_idx]
        week_key = week_start.strftime("%Y%m%d%H%M")
        st.caption(f"📅 Selected: {week_start.strftime('%Y-%m-%d %H:%M')} to {week_end.strftime('%Y-%m-%d %H:%M')}")

        session = get_session()
        try:
            # Cycles belonging to this week under the module's attribution rule
            # — the same set the weekly summary will store, so this preview
            # always matches what gets saved. See cycle_week_timestamp().
            cycles_in_week = get_filtered_cycles(session, week_start, week_end)

            if cycles_in_week:
                ads_sum = sum(safe_value(c.ads_co2_kg) for c in cycles_in_week)
                des_sum = sum(safe_value(c.des_co2_kg) for c in cycles_in_week)
                bag_sum = sum(safe_value(c.bag_co2_kg) for c in cycles_in_week)
                total_kwh_sum = sum(safe_value(c.total_kwh) for c in cycles_in_week)

                st.success(f"✅ Found **{len(cycles_in_week)}** cycles in this week")

                # The straddling cycle sits at whichever edge the attribution rule
                # leaves it on: under "start" it began inside this week and runs
                # past the closing rollover; under "end" it began before the
                # opening rollover and finished inside. Either way it counts here
                # whole, and naming it explains any off-by-one against Athena.
                if WEEK_ATTRIBUTION == "start":
                    straddlers = [c for c in cycles_in_week if c.end_time and c.end_time >= week_end]
                    straddle_note = (
                        "↪️ Runs past the 18:00 rollover into next week but counts here "
                        "in full (it started inside this week): "
                    )
                else:
                    straddlers = [
                        c for c in cycles_in_week
                        if c.end_time and c.start_time < week_start <= c.end_time
                    ]
                    straddle_note = (
                        "↪️ Carried in from the previous week (started before the "
                        "18:00 rollover, completed after it): "
                    )
                if straddlers:
                    st.caption(
                        straddle_note
                        + " · ".join(f"cycle {c.cycle_number}" for c in straddlers)
                    )

                series_counts: dict = {}
                for c in cycles_in_week:
                    series_counts.setdefault(c.series, 0)
                    series_counts[c.series] += 1
                st.caption(
                    " · ".join(
                        f"{get_series_display_name(s)}: {n} cycles" for s, n in series_counts.items()
                    )
                )

                preview_col1, preview_col2, preview_col3, preview_col4 = st.columns(4)
                with preview_col1:
                    st.metric("Adsorbed CO₂", f"{ads_sum:.1f} kg")
                with preview_col2:
                    st.metric("Desorbed CO₂", f"{des_sum:.1f} kg")
                with preview_col3:
                    st.metric("Collected CO₂", f"{bag_sum:.1f} kg")
                with preview_col4:
                    st.metric("Process Energy (CSV)", f"{total_kwh_sum:.1f} kWh")
            else:
                st.warning("⚠️ No cycles found for this week. Check if your Carbon Nest export covers this period.")

            existing = session.query(CarbonNestWeeklySummary).filter(
                CarbonNestWeeklySummary.start_date == week_start
            ).first()

            # CSV-side sums for this week — the derived residuals below are all
            # measured against these, so they're needed before the form renders.
            csv_fans = sum(safe_value(c.fans_kwh) for c in cycles_in_week)
            csv_ct = sum(safe_value(c.ct_kwh) for c in cycles_in_week)
            csv_ct_pump = sum(safe_value(c.ct_pump_kwh) for c in cycles_in_week)
            csv_vp402 = sum(safe_value(c.vp402_kwh) for c in cycles_in_week)
            csv_vp501 = sum(safe_value(c.vp501_kwh) for c in cycles_in_week)
            csv_boiler_a = sum(safe_value(c.boiler_a_kwh) for c in cycles_in_week)
            csv_boiler_b = sum(safe_value(c.boiler_b_kwh) for c in cycles_in_week)
            csv_main_utility = sum(safe_value(c.main_utility_kwh) for c in cycles_in_week)
            csv_bag = sum(safe_value(c.bag_co2_kg) for c in cycles_in_week)

            FIELD_DEFAULTS = {
                "liq": "liquefied_co2_kg",
                "site_energy": "site_energy_kwh",
                "plant_energy": "plant_energy_kwh",
                "utility_skid": "utility_skid_kwh",
                "fan_n1_m1n2": "fan_n1_m1n2_kwh",
                "fan_n1_m3n4": "fan_n1_m3n4_kwh",
                "fan_n2_m1": "fan_n2_m1_kwh",
                "fan_n2_m2": "fan_n2_m2_kwh",
                "fan_n2_m3": "fan_n2_m3_kwh",
                "fan_n2_m4": "fan_n2_m4_kwh",
                "water_pumps": "water_pumps_kwh",
                "compressor_a": "compressor_a_kwh",
                "compressor_b": "compressor_b_kwh",
                "air_dryer": "air_dryer_kwh",
                "boiler_a_standby": "boiler_a_standby_kwh",
                "boiler_b_standby": "boiler_b_standby_kwh",
                "vp402_standby": "vp402_standby_kwh",
                "vp501_standby": "vp501_standby_kwh",
                "ct_ct_pump_total": "ct_ct_pump_total_kwh",
                "liq_active": "liquefaction_active_transfer_kwh",
                "liq_standby": "liquefaction_standby_kwh",
            }
            if existing:
                st.info(f"📌 This week already has a summary. Current liquefied: {existing.liquefied_co2_kg or 0:.1f} kg")
                defaults = {
                    key: safe_value(getattr(existing, column))
                    for key, column in FIELD_DEFAULTS.items()
                }
                defaults["notes"] = existing.notes or ""
            else:
                defaults = {key: 0.0 for key in FIELD_DEFAULTS}
                defaults["notes"] = ""
        finally:
            session.close()

        def pdf_input(label: str, key: str, where: str):
            """A field transcribed verbatim from the Athena weekly PDF.

            Every manual field on this form is a number printed on the report —
            no operator ever subtracts, sums or converts anything, because each
            residual (support infra, fan standby, CT standby, others, plant
            instrument error) is derived below instead. `where` names the exact
            page/row so the value can be found and checked without guesswork.
            """
            return st.number_input(
                label, min_value=0.0, value=defaults[key], step=0.1,
                key=f"cn_{key}_{week_key}", help=f"Athena weekly PDF → {where}",
            )

        st.markdown("#### CO₂ Output")
        liquefied = pdf_input(
            "Liquefied CO₂ (kg)", "liq", "WEEKLY SUMMARY → Mass liquefied"
        )

        st.markdown("#### Tier 1 — Trusted meters")
        st.caption(
            "These two drive every emissions figure. Everything below them is "
            "attribution and diagnostics, and cannot change the total."
        )
        t1_col1, t1_col2 = st.columns(2)
        with t1_col1:
            site_energy = pdf_input(
                "Site Energy (kWh)", "site_energy", "WEEKLY ENERGY & RUNTIME → SITE ENERGY"
            )
        with t1_col2:
            plant_energy = pdf_input(
                "Plant Energy (kWh)", "plant_energy", "WEEKLY ENERGY & RUNTIME → ENERGY table, Plant row"
            )

        st.markdown("#### Tier 2 — Utility skid")
        utility_skid = pdf_input(
            "Utility Skid Energy (kWh)", "utility_skid",
            "COMPONENT CONSUMPTIONS → Utility Skid Energy",
        )

        st.markdown("#### Tier 2 — Fans")
        st.caption(
            "All six readings, unrolled. N1's two fans each serve a module pair "
            "spanning both series (N1 M1n2 covers M1 and M2), so series "
            "attribution isn't extractable from these meters — keeping them "
            "separate is the groundwork for doing it per-Nelion later."
        )
        fan_col1, fan_col2, fan_col3 = st.columns(3)
        with fan_col1:
            fan_n1_m1n2 = pdf_input("N1 M1n2 Fan (kWh)", "fan_n1_m1n2", "COMPONENT CONSUMPTIONS → N1 M1n2 Fan")
            fan_n2_m2 = pdf_input("N2 M2 Fan (kWh)", "fan_n2_m2", "COMPONENT CONSUMPTIONS → N2 M2 Fan")
        with fan_col2:
            fan_n1_m3n4 = pdf_input("N1 M3n4 Fan (kWh)", "fan_n1_m3n4", "COMPONENT CONSUMPTIONS → N1 M3n4 Fan")
            fan_n2_m3 = pdf_input("N2 M3 Fan (kWh)", "fan_n2_m3", "COMPONENT CONSUMPTIONS → N2 M3 Fan")
        with fan_col3:
            fan_n2_m1 = pdf_input("N2 M1 Fan (kWh)", "fan_n2_m1", "COMPONENT CONSUMPTIONS → N2 M1 Fan")
            fan_n2_m4 = pdf_input("N2 M4 Fan (kWh)", "fan_n2_m4", "COMPONENT CONSUMPTIONS → N2 M4 Fan")

        st.markdown("#### Tier 3 — Skid components")
        util_col1, util_col2, util_col3 = st.columns(3)
        with util_col1:
            vp402_standby = pdf_input("VP-402 Standby (kWh)", "vp402_standby", "COMPONENT CONSUMPTIONS → VP-402, Standby consumption")
            vp501_standby = pdf_input("VP-501 Standby (kWh)", "vp501_standby", "COMPONENT CONSUMPTIONS → VP-501, Standby consumption")
            ct_ct_pump_total = pdf_input(
                "CT & CT Pump TOTAL (kWh)", "ct_ct_pump_total",
                "COMPONENT CONSUMPTIONS → CT & CT Pump (the total; standby is derived)",
            )
        with util_col2:
            compressor_a = pdf_input("Compressor A (kWh)", "compressor_a", "COMPONENT CONSUMPTIONS → Compressor A")
            compressor_b = pdf_input("Compressor B (kWh)", "compressor_b", "COMPONENT CONSUMPTIONS → Compressor B")
            air_dryer = pdf_input("Air Dryer (kWh)", "air_dryer", "COMPONENT CONSUMPTIONS → Air Dryer")
        with util_col3:
            water_pumps = pdf_input("Water Pumps (kWh)", "water_pumps", "COMPONENT CONSUMPTIONS → Water Pumps")
            boiler_a_standby = pdf_input("Boiler A Standby (kWh)", "boiler_a_standby", "COMPONENT CONSUMPTIONS → Boiler A, Standby consumption")
            boiler_b_standby = pdf_input("Boiler B Standby (kWh)", "boiler_b_standby", "COMPONENT CONSUMPTIONS → Boiler B, Standby consumption")

        st.markdown("#### Tier 3 — Liquefaction")
        liq_col1, liq_col2 = st.columns(2)
        with liq_col1:
            liq_active = pdf_input("Active Transfer (kWh)", "liq_active", "COMPONENT CONSUMPTIONS → Liquefaction, Active transfer")
        with liq_col2:
            liq_standby = pdf_input("Standby/RFU (kWh)", "liq_standby", "COMPONENT CONSUMPTIONS → Liquefaction, Standby/RFU")

        # ------------------------------------------------------------------
        # Live reconciliation. Mirrors create_or_update_weekly_summary()'s
        # derivation so the operator sees exactly what will be stored, before
        # storing it. A week that doesn't add up to the report it was copied
        # from is caught here rather than discovered in a quarterly review.
        # ------------------------------------------------------------------
        st.markdown("#### Reconciliation")

        fans_total = fan_n1_m1n2 + fan_n1_m3n4 + fan_n2_m1 + fan_n2_m2 + fan_n2_m3 + fan_n2_m4
        fans_total_eff = fans_total or csv_fans
        fan_standby = fans_total_eff - csv_fans

        csv_ct_sum = csv_ct + csv_ct_pump
        ct_total_eff = ct_ct_pump_total or csv_ct_sum
        ct_standby = ct_total_eff - csv_ct_sum

        vp402_total = csv_vp402 + vp402_standby
        vp501_total = csv_vp501 + vp501_standby
        skid_children = (
            vp402_total + vp501_total + ct_total_eff
            + compressor_a + compressor_b + water_pumps + air_dryer
        )
        skid_eff = utility_skid or skid_children
        others = skid_eff - skid_children

        boilers = csv_boiler_a + csv_boiler_b + boiler_a_standby + boiler_b_standby
        liq_energy = liq_active + liq_standby
        buckets = boilers + liq_energy + fans_total_eff + skid_eff

        plant_eff = plant_energy or buckets
        site_eff = site_energy or plant_eff
        support_infra = site_eff - plant_eff
        plant_residual = plant_eff - buckets

        st.dataframe(
            [
                {"Bucket": "Boilers (electric)", "kWh": f"{boilers:,.2f}"},
                {"Bucket": "Liquefaction", "kWh": f"{liq_energy:,.2f}"},
                {"Bucket": "Fans", "kWh": f"{fans_total_eff:,.2f}"},
                {"Bucket": "Utility Skid", "kWh": f"{skid_eff:,.2f}"},
                {"Bucket": "— of which Others (derived)", "kWh": f"{others:,.2f}"},
                {"Bucket": "Support infrastructure (derived)", "kWh": f"{support_infra:,.2f}"},
                {"Bucket": "Plant instrument residual (derived)", "kWh": f"{plant_residual:,.2f}"},
                {"Bucket": "TOTAL = Site meter", "kWh": f"{site_eff:,.2f}"},
            ],
            width="stretch", hide_index=True,
        )

        rec_col1, rec_col2, rec_col3, rec_col4 = st.columns(4)
        with rec_col1:
            st.metric("Fan standby (derived)", f"{fan_standby:,.1f} kWh")
        with rec_col2:
            st.metric("CT standby (derived)", f"{ct_standby:,.1f} kWh")
        with rec_col3:
            st.metric("Others (derived)", f"{others:,.1f} kWh",
                      delta=f"{others / skid_eff * 100:.0f}% of skid" if skid_eff else None,
                      delta_color="off")
        with rec_col4:
            residual_pct = (plant_residual / plant_eff * 100) if plant_eff else 0.0
            st.metric("Plant residual", f"{plant_residual:,.1f} kWh", delta=f"{residual_pct:+.2f}%",
                      delta_color="off")

        # Negative residuals are the signal that a parent meter was typed lower
        # than the children it contains — always a transcription error, never a
        # physical reading, so they block the save rather than just warn.
        blocking = []
        if others < 0:
            blocking.append(
                f"**Others is negative ({others:,.1f} kWh).** The Utility Skid total "
                f"({skid_eff:,.1f}) is less than its listed components ({skid_children:,.1f})."
            )
        if support_infra < 0:
            blocking.append(
                f"**Support infrastructure is negative ({support_infra:,.1f} kWh).** "
                f"Site ({site_eff:,.1f}) is below Plant ({plant_eff:,.1f})."
            )
        if fan_standby < 0:
            blocking.append(
                f"**Fan standby is negative ({fan_standby:,.1f} kWh).** The six fan "
                f"readings ({fans_total_eff:,.1f}) total less than the CSV's in-cycle "
                f"fan energy ({csv_fans:,.1f})."
            )
        if ct_standby < 0:
            blocking.append(
                f"**CT standby is negative ({ct_standby:,.1f} kWh).** The CT & CT Pump "
                f"total ({ct_total_eff:,.1f}) is below the CSV's in-cycle sum ({csv_ct_sum:,.1f})."
            )
        if abs(residual_pct) > 5:
            blocking.append(
                f"**Plant residual is {residual_pct:+.1f}%** ({plant_residual:,.1f} kWh). "
                "Above 5% this is too large to be instrument error — check the Plant "
                "and bucket figures."
            )

        for msg in blocking:
            st.error(msg)
        if not blocking and abs(residual_pct) > 1:
            st.warning(
                f"Plant residual is {residual_pct:+.1f}% ({plant_residual:,.1f} kWh). "
                "Instrument error normally lands under 1% — worth a second look, but "
                "not blocking."
            )
        if not blocking and site_energy and plant_energy:
            st.success(
                f"Reconciles: buckets {buckets:,.1f} + residual {plant_residual:,.1f} "
                f"= plant {plant_eff:,.1f}; + support {support_infra:,.1f} = site {site_eff:,.1f} kWh"
            )
        if not site_energy or not plant_energy:
            st.info(
                "Site and/or Plant energy not entered — the total falls back to the sum "
                "of the buckets, so support infrastructure and the plant residual will "
                "read as zero rather than as reconciled."
            )

        # Main Utility diagnostic: the CSV column is excluded from every total
        # (nobody has confirmed what it meters). It sits between the in-cycle
        # skid children and the full skid total, which is where a skid parent
        # meter sampled in-cycle only would sit. Tracking the ratio week over
        # week is how we find out cheaply — see notes for 2026-08-25.
        if csv_main_utility:
            csv_skid_children = csv_vp402 + csv_vp501 + csv_ct_sum
            st.caption(
                f"🔍 Main Utility diagnostic (excluded from all totals): CSV "
                f"{csv_main_utility:,.1f} kWh vs in-cycle skid children "
                f"{csv_skid_children:,.1f} kWh (ratio "
                f"{csv_main_utility / csv_skid_children:.2f}×) vs skid total "
                f"{skid_eff:,.1f} kWh. Consistent with a skid parent meter sampled "
                f"in-cycle only, if the ratio holds steady across weeks."
            )

        notes = st.text_area("Notes (optional)", value=defaults["notes"], key=f"cn_notes_{week_key}")

        if st.button(
            "💾 Calculate & Save Weekly Summary", type="primary", width="stretch",
            key="cn_save_summary", disabled=bool(blocking),
        ):
            session = get_session()
            try:
                summary = create_or_update_weekly_summary(
                    session,
                    week_start=week_start,
                    liquefied_co2_kg=liquefied,
                    site_energy_kwh=site_energy,
                    plant_energy_kwh=plant_energy,
                    utility_skid_kwh=utility_skid,
                    fan_n1_m1n2_kwh=fan_n1_m1n2,
                    fan_n1_m3n4_kwh=fan_n1_m3n4,
                    fan_n2_m1_kwh=fan_n2_m1,
                    fan_n2_m2_kwh=fan_n2_m2,
                    fan_n2_m3_kwh=fan_n2_m3,
                    fan_n2_m4_kwh=fan_n2_m4,
                    water_pumps_kwh=water_pumps,
                    compressor_a_kwh=compressor_a,
                    compressor_b_kwh=compressor_b,
                    air_dryer_kwh=air_dryer,
                    boiler_a_standby_kwh=boiler_a_standby,
                    boiler_b_standby_kwh=boiler_b_standby,
                    vp402_standby_kwh=vp402_standby,
                    vp501_standby_kwh=vp501_standby,
                    ct_ct_pump_total_kwh=ct_ct_pump_total,
                    liquefaction_active_transfer_kwh=liq_active,
                    liquefaction_standby_kwh=liq_standby,
                    notes=notes,
                    created_by=st.session_state.get("user_id"),
                )

                st.success(f"✅ Saved week {summary.start_date.strftime('%Y-%m-%d')} → {summary.end_date.strftime('%Y-%m-%d')}")

                st.markdown("#### Removal — both boundaries")
                # Only true at or below 100% liquefaction efficiency — above it,
                # boundary B's product is the larger of the two and it carries the
                # higher embodied charge. See _boundaries_note() in pdf_report.py.
                if (summary.gross_captured_kg or 0) > (summary.capture_gross_kg or 0):
                    st.caption(
                        "⚠️ Liquefaction exceeded collection this week, so bagged CO₂ held "
                        "over from an earlier week was drawn down. Above 100% this is an "
                        "inventory movement rather than a yield — read it across several "
                        "weeks. Boundary B carries the higher embodied charge here, the "
                        "reverse of a normal week."
                    )
                else:
                    st.caption(
                        "The liquefied boundary shows *lower* total emissions but *worse* "
                        "net removal. That's correct: embodied is charged per tonne of "
                        "product, so it shrinks with the denominator."
                    )
                st.dataframe(
                    [
                        {
                            "Boundary": "A · Capture (liquefaction excluded)",
                            "Product (kg)": f"{summary.capture_gross_kg or 0:,.2f}",
                            "Energy (kWh)": f"{summary.capture_energy_kwh or 0:,.1f}",
                            "Operational (kg)": f"{summary.capture_operational_emissions_kg or 0:,.2f}",
                            "Embodied (kg)": f"{summary.capture_embodied_emissions_kg or 0:,.2f}",
                            "Net removal (kg)": f"{summary.capture_net_removal_kg or 0:+,.2f}",
                            "MWh/t": f"{(summary.capture_energy_intensity_kwh_per_tonne or 0) / 1000:,.1f}",
                        },
                        {
                            "Boundary": "B · Liquefied (credit-bearing)",
                            "Product (kg)": f"{summary.gross_captured_kg or 0:,.2f}",
                            "Energy (kWh)": f"{summary.total_energy_kwh or 0:,.1f}",
                            "Operational (kg)": f"{summary.total_operational_emissions_kg or 0:,.2f}",
                            "Embodied (kg)": f"{summary.total_embodied_emissions_kg or 0:,.2f}",
                            "Net removal (kg)": f"{summary.net_removal_kg or 0:+,.2f}",
                            "MWh/t": f"{(summary.energy_intensity_kwh_per_tonne or 0) / 1000:,.1f}",
                        },
                    ],
                    width="stretch", hide_index=True,
                )

                eff_col1, eff_col2, eff_col3 = st.columns(3)
                with eff_col1:
                    liq_eff = summary.liquefaction_efficiency_pct
                    st.metric(
                        "Liquefaction efficiency",
                        f"{liq_eff:.1f}%" if liq_eff is not None else "—",
                        help="Liquefied ÷ collected. The shortfall is CO₂ vented during "
                             "liquefaction — it reduces product but is never charged as "
                             "an emission, since it's atmospheric carbon going back to "
                             "the atmosphere rather than a new release.",
                    )
                with eff_col2:
                    st.metric("Vented at liquefaction", f"{summary.loss_stage_3_kg or 0:,.1f} kg")
                with eff_col3:
                    st.metric("Operational emissions", f"{summary.total_operational_emissions_kg or 0:,.1f} kg")

            finally:
                session.close()

    with tab3:
        st.markdown("### View & Manage Data")
        view_tab1, view_tab2 = st.tabs(["📅 Weekly Summaries", "🔄 Cycle Data"])

        with view_tab1:
            session = get_session()
            try:
                all_weeks = (
                    session.query(CarbonNestWeeklySummary)
                    .order_by(CarbonNestWeeklySummary.start_date.desc())
                    .all()
                )
                if all_weeks:
                    st.caption(f"Total: {len(all_weeks)} weekly summaries")
                    for week in all_weeks:
                        status_emoji = "✅" if week.is_net_positive else "❌"
                        week_label = f"{week.start_date.strftime('%Y-%m-%d %H:%M')} → {week.end_date.strftime('%Y-%m-%d %H:%M')}"
                        with st.expander(f"{status_emoji} {week_label}"):
                            r_col1, r_col2, r_col3, r_col4 = st.columns([1, 1, 1, 0.5])
                            with r_col1:
                                st.markdown("**CO₂ Flow (kg)**")
                                st.write(f"- Adsorbed: {week.total_ads_co2_kg or 0:.1f}")
                                st.write(f"- Desorbed: {week.total_des_co2_kg or 0:.1f}")
                                st.write(f"- Collected: {week.total_bag_co2_kg or 0:.1f}")
                                st.write(f"- Liquefied: {week.liquefied_co2_kg or 0:.1f}")
                            with r_col2:
                                st.markdown("**Emissions (kg CO₂)**")
                                st.write(f"- Operational: {week.total_operational_emissions_kg or 0:.1f}")
                                st.write(f"- Embodied: {week.total_embodied_emissions_kg or 0:.1f}")
                                st.write(f"- Total: {week.total_emissions_kg or 0:.1f}")
                            with r_col3:
                                st.markdown("**Result**")
                                net = week.net_removal_kg or 0
                                status = "✅ Net Positive" if net > 0 else "❌ Net Negative"
                                st.write(f"- Net Removal: {net:.1f} kg")
                                st.write(f"- Status: {status}")
                                st.write(f"- Cycles: {week.total_cycles or 0}")
                            with r_col4:
                                st.markdown("**Actions**")
                                if st.button("🗑️ Delete", key=f"cn_del_{week.id}", type="secondary"):
                                    del_session = get_session()
                                    try:
                                        del_session.query(CarbonNestCycleData).filter(
                                            CarbonNestCycleData.weekly_summary_id == week.id
                                        ).delete()
                                        del_session.query(CarbonNestWeeklySummary).filter(
                                            CarbonNestWeeklySummary.id == week.id
                                        ).delete()
                                        del_session.commit()
                                        st.success(f"Deleted {week_label}")
                                        st.rerun()
                                    finally:
                                        del_session.close()
                            if week.notes:
                                st.caption(f"Notes: {week.notes}")
                else:
                    st.info("No weekly summaries yet.")
            finally:
                session.close()

        with view_tab2:
            session = get_session()
            try:
                recent_cycles = (
                    session.query(CarbonNestCycleData)
                    .order_by(CarbonNestCycleData.start_time.desc())
                    .limit(20)
                    .all()
                )
                if recent_cycles:
                    st.caption(f"Showing most recent 20 of {total_cycles} total cycles")
                    cycle_data = []
                    for c in recent_cycles:
                        cycle_data.append({
                            "Date": c.start_time.strftime("%Y-%m-%d %H:%M") if c.start_time else "N/A",
                            "Cycle": c.cycle_number,
                            "Module": c.raw_module,
                            "Series": get_series_display_name(c.series),
                            "Nelion": c.nelion or "Combined/unattributed",
                            "ADS CO₂": f"{c.ads_co2_kg or 0:.2f}",
                            "DES CO₂": f"{c.des_co2_kg or 0:.2f}",
                            "BAG CO₂": f"{c.bag_co2_kg or 0:.2f}",
                            "Total kWh": f"{c.total_kwh or 0:.1f}",
                        })
                    st.dataframe(cycle_data, width="stretch", hide_index=True)
                else:
                    st.info("No cycle data imported yet. Use the Carbon Nest Import tab above.")
            finally:
                session.close()


if __name__ == "__main__":
    main()
