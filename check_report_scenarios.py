"""Render the weekly report against every week-shape the plant can produce,
and assert the page agrees with itself.

    python check_report_scenarios.py          # all scenarios, exits 1 on failure
    python check_report_scenarios.py -v       # also print each scenario's figures

Why this exists. The 2026-09-05 report stated four things about one week that
could not all be true: the hero and the boundary table reported the capture
boundary at 41.7 MWh/t, while the Energy Intensity and Steam Intensity cards
rendered "--" and the narrative asserted "0.0 MWh/t" with a "100% operational /
0% embodied" mix. Nothing crashed. Every number was rendered confidently. The
report was simply quoting two different boundaries in one document, because
each site re-derived the boundary for itself instead of reading the one
headline_figures() had resolved.

"It rendered without an exception" is therefore a near-worthless check here --
the failure mode of this report is a plausible wrong number, not a traceback.
So the oracle below is self-consistency: wherever the document states the same
quantity twice, the two statements must match. That is what the original bug
would have failed, and what a future one is most likely to fail again.

Scenarios are built by mutating a real row out of the local database, so column
coverage stays realistic rather than reflecting whatever a hand-written fixture
happened to include. The session-backed helpers are stubbed; everything from
build_week_report_context() down is the genuine code path.

Needs a local database with at least one weekly summary. Runs against SQLite by
default, or Neon if DATABASE_URL is set -- it only reads.
"""
from __future__ import annotations

import datetime
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import app.services.report_data as rd
from app.database.connection import get_session
from app.database.models import CarbonNestWeeklySummary

GRID_EF = 0.0579
# kg CO2e per tonne of product, output-based. Only needs to be representative:
# these scenarios test the report's internal consistency, not the LCA itself.
EMBODIED_RATE = 271.9


def _wc_group(label, cap, used, in_window):
    return {
        "label": label,
        "avg_working_capacity_mol_per_m3": cap,
        "n_cycles_in_window": in_window,
        "n_cycles_used": used,
        "n_cycles_valid": used,
        "excluded_cycle_ids": [],
        "missing_config_cycle_ids": [],
        "missing_config_prefixes": [],
        "config_anomalies": [],
    }


def _wc(week_start, populated: bool):
    """A working-capacity result, either populated or with nothing usable —
    every cycle excluded, or the sorbent config missing for those modules."""
    a = _wc_group("Group A (M1 & M3)", 85.67 if populated else None, 23 if populated else 0, 51)
    b = _wc_group("Group B (M2 & M4)", 60.72 if populated else None, 8 if populated else 0, 26)
    return {"week_start": week_start, "week_end": week_start, "groups": {"A": a, "B": b}}


SERIES_STUB = {"cycles": 0, "steam_kg": 0.0, "bag_co2_kg": 0.0}


def recompute(d: dict) -> dict:
    """Rebuild the derived columns so a mutated scenario stays self-consistent.

    Mirrors calculate_weekly_metrics() and load_weekly_df(): operational is
    metered energy x grid EF on each boundary, embodied is output-based on that
    boundary's own product, and a series-filtered row carries the CAPTURE
    figures in its headline columns because liquefaction has no per-series
    split. Getting that last part wrong makes the capture path untestable.
    """
    bag = d.get("total_bag_co2_kg") or 0
    liq = d.get("liquefied_co2_kg") or 0
    site = d.get("total_energy_kwh") or 0
    liq_energy = d.get("liquefaction_energy_kwh") or 0
    on_capture = d.get("boundary") == "capture"

    cap_energy = max(site - liq_energy, 0.0)
    d["capture_energy_kwh"] = cap_energy
    d["capture_gross_kg"] = bag
    d["capture_operational_emissions_kg"] = cap_energy * GRID_EF
    d["capture_embodied_emissions_kg"] = bag / 1000 * EMBODIED_RATE
    d["capture_total_emissions_kg"] = (
        d["capture_operational_emissions_kg"] + d["capture_embodied_emissions_kg"]
    )
    d["capture_net_removal_kg"] = bag - d["capture_total_emissions_kg"]

    d["collected_co2_kg"] = bag if on_capture else liq
    d["liquefied_gross_kg"] = liq
    d["total_operational_emissions_kg"] = (
        d["capture_operational_emissions_kg"] if on_capture else site * GRID_EF
    )
    d["total_embodied_emissions_kg"] = (
        d["capture_embodied_emissions_kg"] if on_capture else liq / 1000 * EMBODIED_RATE
    )
    d["total_emissions_kg"] = (
        d["total_operational_emissions_kg"] + d["total_embodied_emissions_kg"]
    )
    d["net_removal_kg"] = (bag if on_capture else liq) - d["total_emissions_kg"]
    d["liquefied_net_removal_kg"] = liq - (
        site * GRID_EF + liq / 1000 * EMBODIED_RATE
    )
    d["liquefied_total_emissions_kg"] = site * GRID_EF + liq / 1000 * EMBODIED_RATE
    d["liquefaction_efficiency_pct"] = (liq / bag * 100) if bag else 0
    return d


def build_scenarios(template: dict) -> dict:
    def make(**over):
        d = dict(template)
        d.update(over)
        return recompute(d)

    return {
        # The ordinary case: some of the week's bagged CO2 got liquefied.
        "normal week": make(liquefied_co2_kg=300.0, total_bag_co2_kg=440.0),
        # The week that exposed the boundary bug.
        "zero liquefaction": make(liquefied_co2_kg=0.0, total_bag_co2_kg=440.0),
        # Bag inventory carried over from an earlier week was drawn down, so
        # liquefaction yield exceeds 100% and boundary B's emissions can sit
        # ABOVE boundary A's — the case boundaries_note() has a branch for.
        "liquefied exceeds collected": make(liquefied_co2_kg=460.0, total_bag_co2_kg=440.0),
        # No product on either boundary: every ratio is undefined and must
        # print an em dash, never 0, which would read as break-even.
        "nothing captured at all": make(
            liquefied_co2_kg=0.0, total_bag_co2_kg=0.0, total_ads_co2_kg=0.0,
            total_des_co2_kg=0.0, total_cycles=0, total_steam_kg=0.0,
            loss_stage_1_kg=0.0, loss_stage_2_kg=0.0, loss_stage_3_kg=0.0,
        ),
        # Net POSITIVE removal. Every sign, colour and comparative word in the
        # report has to flip; most of them were written when this had never
        # happened, and it is the outcome the whole plant exists to reach.
        "net positive removal": make(liquefied_co2_kg=3000.0, total_bag_co2_kg=3200.0),
        "zero steam": make(
            liquefied_co2_kg=300.0, total_bag_co2_kg=440.0, total_steam_kg=0.0
        ),
        # Metered energy missing entirely — intensity undefined, but product
        # and embodied emissions still exist.
        "zero energy": make(
            liquefied_co2_kg=300.0, total_bag_co2_kg=440.0, total_energy_kwh=0.0,
            liquefaction_energy_kwh=0.0, boilers_bucket_kwh=0.0, fans_total_kwh=0.0,
            utility_skid_kwh=0.0, support_infra_kwh=0.0, plant_residual_kwh=0.0,
        ),
        # Per-series report: structurally on the capture boundary, and NOT
        # because the week failed to liquefy, so it must not print the
        # zero-liquefaction disclosure.
        "series-filtered (capture)": make(
            boundary="capture", liquefied_co2_kg=0.0, total_bag_co2_kg=220.0
        ),
        # Nulls where floats are expected, as a partially-entered week gives.
        "null-heavy row": make(
            liquefied_co2_kg=None, total_bag_co2_kg=440.0, total_steam_kg=None,
            loss_stage_1_kg=None, loss_stage_2_kg=None, loss_stage_3_kg=None,
            total_des_co2_kg=None,
        ),
        # Tiny product against a full week's energy: the deliberately perverse
        # case calculate_weekly_metrics() refuses to smooth over, because
        # letting boundary B fall back to bagged CO2 made a week that liquefied
        # nothing outscore one that liquefied a little.
        "tiny product": make(liquefied_co2_kg=5.0, total_bag_co2_kg=6.0),
    }


# Text that means the report asserted something it should have declined to
# state. "0.0 MWh/t" is the original bug's exact signature.
RED_FLAGS = [
    (r"\bnan\b", "NaN reached the rendered page"),
    (r"\binf\b", "infinity reached the rendered page"),
    (r">None<|: None|\bNone kg\b", "None reached the rendered page"),
    (r"0\.0 MWh/t", "zero energy intensity stated as fact"),
    (r"\b0 kg/t", "zero steam intensity stated as fact"),
]


def visible_text(doc: str) -> str:
    doc = re.sub(r"<script.*?</script>", " ", doc, flags=re.S)
    doc = re.sub(r"<style.*?</style>", " ", doc, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", doc).replace("&nbsp;", " "))


def cross_check(ctx, text: str) -> list[str]:
    """Wherever the page states one quantity twice, the two must agree."""
    problems = []

    card = re.search(r"ENERGY INTENSITY\s*([\d.,]+|—)\s*MWh/t", text)
    narrative = re.search(r"Energy intensity:\s*([\d.,]+|—)", text)
    if card and narrative and card.group(1) != narrative.group(1):
        problems.append(
            f"Energy Intensity card says {card.group(1)}, narrative says {narrative.group(1)}"
        )

    # The boundary table's row A, against the card and hero — but only when the
    # headline is actually on that row's boundary. A series-filtered report
    # renders no boundary table at all, since only one boundary exists.
    cells = re.search(
        r"A · Capture\s*liquefaction excluded\s*([\d.,]+)\s*([\d.,]+)\s*([\d.,]+)\s*"
        r"([\d.,]+)\s*([+\-\d.,]+)\s*([+\-\d.,%]+|—)\s*([\d.,]+|—)", text)
    if cells and ctx.headline_basis == "collected":
        if card and cells.group(7) != card.group(1):
            problems.append(
                f"card {card.group(1)} MWh/t vs boundary table row A {cells.group(7)}"
            )
        if ctx.removal_efficiency is not None:
            want = f"{ctx.removal_efficiency:+.1f}%"
            if cells.group(6) != want:
                problems.append(f"hero {want} vs boundary table row A {cells.group(6)}")

    # Emissions donut: slices must add to the headline's total, not to whatever
    # subset happened to be plotted.
    from app.components.charts import cn_emissions_breakdown_pie
    fig = cn_emissions_breakdown_pie(ctx.row, ctx.headline_dict(), ctx.grid_ef)
    if fig is not None:
        plotted = sum(fig.data[0].values)
        want = ctx.total_emissions or 0
        if want > 0 and abs(plotted - want) > max(0.5, want * 0.001):
            problems.append(
                f"pie sums to {plotted:,.1f} kg, headline total is {want:,.1f} kg"
            )

    # The zero-liquefaction disclosure belongs only to a week that fell back,
    # never to a per-series report that never had a liquefied figure.
    if ctx.series_filter and ctx.headline_note:
        problems.append("series-filtered report printed the zero-liquefaction disclosure")

    if ctx.removal_efficiency is not None:
        want = f"{ctx.removal_efficiency:+.1f}%"
        if want not in text.replace("−", "-"):
            problems.append(f"hero efficiency {want} absent from the page")

    return problems


def render(week_start, row_dict, series_filter, populated_wc: bool):
    df = pd.DataFrame([row_dict])
    rd.load_weekly_df_cached = lambda *a, **k: df
    rd.get_grid_ef_cached = lambda *a, **k: GRID_EF
    rd.weekly_working_capacity_cached = lambda *a, **k: _wc(week_start, populated_wc)
    rd.get_weekly_metrics_by_series = lambda *a, **k: dict(SERIES_STUB)
    from app.services import html_report

    ctx = rd.build_week_report_context(None, week_start, series_filter)
    doc = html_report.generate_weekly_html_report(None, week_start, series_filter, context=ctx)
    return ctx, doc


def main() -> int:
    verbose = "-v" in sys.argv

    session = get_session()
    try:
        week = (
            session.query(CarbonNestWeeklySummary)
            .order_by(CarbonNestWeeklySummary.start_date.desc())
            .first()
        )
        if week is None:
            print("No weekly summaries in the database — nothing to build scenarios from.")
            return 2
        week_start = week.start_date
        template = rd.load_weekly_df_cached(session, None, None)
    finally:
        session.close()

    matches = template[template["start_date"] == week_start]
    if matches.empty:
        print(f"Week {week_start} missing from the weekly dataframe.")
        return 2
    template_row = matches.iloc[0].to_dict()

    print(f"Template week: {week_start:%Y-%m-%d %H:%M}\n")
    scenarios = build_scenarios(template_row)
    failures = 0

    for name, row in scenarios.items():
        series_filter = "1n3" if "series-filtered" in name else None
        populated_wc = "nothing captured" not in name
        try:
            ctx, doc = render(week_start, row, series_filter, populated_wc)
        except Exception:
            print(f"[CRASH] {name}")
            print("        " + traceback.format_exc().strip().splitlines()[-1])
            failures += 1
            continue

        text = visible_text(doc)
        problems = [msg for pattern, msg in RED_FLAGS if re.search(pattern, text, re.I)]
        problems += cross_check(ctx, text)
        if problems:
            failures += 1

        if verbose or problems:
            eff = (
                f"{ctx.removal_efficiency:+.1f}%"
                if ctx.removal_efficiency is not None else "—"
            )
            mwh = (
                f"{ctx.headline_energy_intensity / 1000:.1f}"
                if ctx.headline_energy_intensity else "—"
            )
            print(
                f"[{'FAIL' if problems else ' ok '}] {name:28} "
                f"basis={ctx.headline_basis:9} eff={eff:>10} MWh/t={mwh:>7}"
            )
            for p in problems:
                print(f"         -> {p}")
        else:
            print(f"[ ok ] {name}")

    print(f"\n{len(scenarios)} scenarios, {failures} failing.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
