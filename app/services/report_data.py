"""The numbers and the prose behind one week's report, independent of format.

Both the PDF (ReportLab) and the HTML/CSV fallback render this same context, so
a week reported as a PDF and the same week reported as HTML can never disagree.
That matters more than it looks: the efficiency definitions below carry a
one-stage-per-name invariant that took a correction from the site team to get
right, and duplicating the arithmetic per output format is how a fix lands in
one copy and not the other.

The prose helpers return inline markup that is deliberately valid in both
worlds — ReportLab's Paragraph understands `<b>`, `<i>`, `<font>` and HTML
entities, and so does a browser — so the same sentence can be handed to either
renderer unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go

from app.components.charts import CN_ENERGY_SUBSYSTEMS, apply_chart_layout
from app.pages.cn_dashboard import load_weekly_df_cached
from app.services.carbon_nest_aggregation import get_grid_ef_cached, get_weekly_metrics_by_series
from app.services.carbon_nest_working_capacity import weekly_working_capacity_cached


def pct(value: Optional[float]) -> str:
    """A percentage for a KPI card, or an em dash when the ratio is undefined."""
    return f"{value:.1f}%" if value is not None else "—"


# How to name each headline basis in a card subtitle. Every intensity figure
# is per tonne of PRODUCT, and which product that is changes with the boundary
# in force — so the card has to say which, or two weeks' cards silently mean
# different things.
BASIS_LABEL = {
    "liquefied": "liquefied CO₂",
    "collected": "collected CO₂ (capture boundary)",
}


# The plant's own timezone. Every other timestamp in this report is plant-local
# and naive — Athena exports local times, and the Saturday-18:00 week boundary
# is 18:00 in Gilgil — so the footer must be too.
PLANT_TZ = "Africa/Nairobi"
PLANT_TZ_LABEL = "EAT"
PLANT_UTC_OFFSET_HOURS = 3


def report_generated_at(now: Optional[datetime] = None) -> str:
    """When this report was generated, in plant-local time, labelled.

    Previously a bare datetime.now() with no timezone. On a UTC host — which
    is what Streamlit Cloud runs — that rendered a Nairobi afternoon as three
    hours earlier with nothing to say so, and a report generated at 20:14 EAT
    was footed "Generated 2026-09-15 17:14". Every other time in the document
    is plant-local, so the one timestamp a reader might check a report against
    was the one that disagreed with all of them.

    The label matters as much as the conversion: this report goes to verifiers,
    and an unlabelled timestamp is not evidence of anything.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.astimezone()
    try:
        from zoneinfo import ZoneInfo

        local = now.astimezone(ZoneInfo(PLANT_TZ))
    except Exception:
        # No tz database on this host (bare Windows without `tzdata`). EAT has
        # no DST and has been UTC+3 since 1960, so a fixed offset is exact
        # rather than an approximation.
        local = now.astimezone(timezone(timedelta(hours=PLANT_UTC_OFFSET_HOURS)))
    return f"{local:%Y-%m-%d %H:%M} {PLANT_TZ_LABEL}"


def per_tonne(amount: Optional[float], product_kg: Optional[float]) -> Optional[float]:
    """`amount` per tonne of product, or None when the ratio is undefined.

    None rather than 0, for the same reason pct() returns an em dash: a week
    with no product has no intensity, and "0.0 MWh/t" reads as perfect
    efficiency — the most flattering possible misstatement of a week that
    produced nothing.
    """
    amount = amount or 0
    product_kg = product_kg or 0
    if amount <= 0 or product_kg <= 0:
        return None
    return amount / (product_kg / 1000)


def boundary_note(row: pd.Series, headline_basis: Optional[str] = None) -> str:
    """Subtitle for the Gross Captured card, naming the boundary in force.

    Series-filtered reports can only use the capture boundary — liquefaction is
    a single shared downstream process with no per-series liquefied figure.

    `headline_basis` lets a zero-liquefaction week say so explicitly: the
    headline falls back to collected CO₂ (see build_week_report_context) and
    the card must not keep claiming to be the credit-bearing figure.
    """
    if headline_basis == "collected" or row.get("boundary") == "capture":
        return "Collected CO₂ (capture boundary)"
    return "Liquefied CO₂ (credit-bearing)"


def headline_figures(row: pd.Series) -> dict:
    """Which boundary a week's headline is stated on, and its figures.

    Normally boundary B (liquefied, credit-bearing). A week that liquefied
    nothing has no credit-bearing product, so every headline figure collapses
    to zero and the removal efficiency is undefined; such a week is stated on
    boundary A (collected) instead, which already scores the capture work with
    liquefaction excluded from both sides.

    PRESENTATION ONLY. calculate_weekly_metrics() deliberately does not let
    boundary B fall back to bagged CO2, because that made a week which
    liquefied nothing outscore one that liquefied a little — product shrinks
    faster than emissions, so 1 kg liquefied reads about -78,000% against
    about -350% for zero, and the incentive ran backwards. That invariant is
    untouched: boundary B's stored product stays 0, the boundary table still
    reports it, and only the headline's *choice* of boundary moves here.

    Single definition on purpose — the hero sentence, the KPI cards, the
    narrative stat line, the carbon-balance waterfall and the recent-weeks
    trend all read this, so they cannot end up quoting different bases for the
    same week.

    EVERY boundary-dependent quantity belongs in here, including the
    intensities. They were previously read straight off `row`, whose columns
    always hold the boundary the week was LOADED on, not the one the headline
    settled on. On a zero-liquefaction week that produced a report which
    contradicted itself in three places at once: the hero and the boundary
    table said capture boundary at 41.7 MWh/t, while the Energy Intensity and
    Steam Intensity cards rendered "—" and the narrative claimed "0.0 MWh/t"
    and a "100% operational / 0% embodied" mix — all four computed against
    liquefied product, which was zero. Any new boundary-dependent figure must
    be added here rather than read from `row` at the render site.
    """
    liquefied = row.get("liquefied_co2_kg") or 0
    collected = row.get("total_bag_co2_kg") or 0
    steam = row.get("total_steam_kg") or 0

    # Two different routes to the capture boundary, and they must not be
    # conflated. A SERIES-FILTERED row is on it structurally: liquefaction is a
    # single shared downstream process with no per-series split, so
    # load_weekly_df already swapped that row's headline columns to the capture
    # figures. A FALLBACK row is on it circumstantially, because this
    # particular week liquefied nothing.
    #
    # Both are the capture boundary and both must report basis "collected" —
    # this previously returned "liquefied" for series-filtered rows, which was
    # true of neither the columns nor the figures, and left every consumer
    # keyed off `basis` believing liquefaction was in scope.
    #
    # Only the fallback carries the disclosure note. A per-series report is not
    # announcing that the week failed to liquefy; it is reporting a boundary
    # that never had a liquefied figure to begin with.
    series_filtered = row.get("boundary") == "capture"
    fell_back = not series_filtered and liquefied <= 0 and collected > 0

    if series_filtered or fell_back:
        gross = collected
        # Boundary A energy: the site meter with liquefaction backed out of it,
        # exactly as the boundary table's row A reports it, so the card and the
        # table can never print different MWh/t for the same week.
        energy = row.get("capture_energy_kwh") or 0
        return {
            "basis": "collected",
            "note": HEADLINE_FALLBACK_NOTE if fell_back else None,
            "gross_captured": gross,
            "total_emissions": row.get("capture_total_emissions_kg") or 0,
            "net_removal": row.get("capture_net_removal_kg") or 0,
            "operational": row.get("capture_operational_emissions_kg") or 0,
            "embodied": row.get("capture_embodied_emissions_kg") or 0,
            "energy_kwh": energy,
            "energy_intensity_kwh_per_tonne": per_tonne(energy, gross),
            "steam_intensity_kg_per_tonne": per_tonne(steam, gross),
            "removal_efficiency": (
                (row.get("capture_net_removal_kg") or 0) / gross * 100 if gross > 0 else None
            ),
        }

    gross = row.get("collected_co2_kg") or 0
    energy = row.get("total_energy_kwh") or 0
    return {
        "basis": "liquefied",
        "note": None,
        "gross_captured": gross,
        "total_emissions": row.get("total_emissions_kg") or 0,
        "net_removal": row.get("net_removal_kg") or 0,
        "operational": row.get("total_operational_emissions_kg") or 0,
        "embodied": row.get("total_embodied_emissions_kg") or 0,
        "energy_kwh": energy,
        "energy_intensity_kwh_per_tonne": per_tonne(energy, gross),
        "steam_intensity_kg_per_tonne": per_tonne(steam, gross),
        # None, not 0: a week with no product has no removal efficiency, and
        # "+0.0%" reads as break-even — the single most misleading thing this
        # report could print about a week that captured nothing. Matches
        # cn_dashboard.removal_efficiency_pct(), which already did this.
        "removal_efficiency": (
            (row.get("net_removal_kg") or 0) / gross * 100 if gross > 0 else None
        ),
    }


HEADLINE_FALLBACK_NOTE = (
    "No CO₂ was liquefied this week, so there is no credit-bearing product to "
    "report against. The headline figures above are therefore stated on the "
    "capture boundary — product is COLLECTED (bagged) CO₂, with liquefaction "
    "energy excluded from both sides. These numbers are not credit-bearing: "
    "only liquefied CO₂ is. Boundary B in the table below shows the "
    "credit-bearing position for the week, which is zero product."
)


def boundaries_note(row: pd.Series) -> str:
    """Explain the two boundaries against what this week's numbers actually did.

    This was previously a fixed sentence asserting that the liquefied boundary
    always carries lower total emissions. That is only true while liquefaction
    efficiency is at or below 100%. The week of 2026-08-01 liquefied 353.0 kg
    against 349.2 kg collected — a bag inventory carried over from an earlier
    week was drawn down — and boundary B's emissions came out *above* A's, so
    the fixed sentence printed a false statement.
    """
    bag = row.get("capture_gross_kg") or 0
    liq = row.get("liquefied_gross_kg") or 0
    cap_em = row.get("capture_total_emissions_kg") or 0
    liq_em = row.get("liquefied_total_emissions_kg") or 0
    cap_net = row.get("capture_net_removal_kg") or 0
    liq_net = row.get("liquefied_net_removal_kg") or 0

    if liq > bag and bag > 0:
        return (
            f"Liquefaction exceeded collection this week — {liq:,.1f} kg liquefied against "
            f"{bag:,.1f} kg collected, or {liq / bag * 100:,.1f}% — so bagged CO₂ held over "
            f"from an earlier week was drawn down. Liquefaction efficiency above 100% is an "
            f"inventory movement, not a yield: read it across several weeks rather than one. "
            f"Because boundary B's product is the larger of the two, it carries the higher "
            f"embodied charge here, and its total emissions ({liq_em:,.1f} kg) sit above "
            f"boundary A's ({cap_em:,.1f} kg) — the reverse of a normal week."
        )

    # Both comparisons are measured, not assumed. "worse" was previously fixed
    # text sitting beside a computed `direction`, which is the same trap this
    # function's docstring describes: it holds while liquefaction yield is
    # below 100%, and prints a falsehood on the week it is not.
    direction = "lower" if liq_em < cap_em else "higher"
    outcome = "worse" if liq_net < cap_net else "better"
    # "but" only when the two comparisons disagree about which boundary looks
    # better — lower emissions alongside a worse removal is the contrast the
    # sentence is drawing. When they agree, "but" would be a non-sequitur.
    conjunction = "but" if (liq_em < cap_em) != (liq_net > cap_net) else "and"
    return (
        f"The liquefied boundary carries <i>{direction}</i> total emissions {conjunction} a "
        f"<i>{outcome}</i> net removal — embodied emissions are charged per tonne of product, so "
        f"they shrink with the denominator. CO₂ vented during liquefaction reduces product "
        f"without being charged as an emission: it is atmospheric carbon returning to the "
        f"atmosphere, a failure to remove rather than a new release. Note that bagged CO₂ can "
        f"also carry across a week boundary, so a single week's liquefaction efficiency mixes "
        f"yield with inventory timing."
    )


def build_narrative(row: pd.Series, headline: Optional[dict] = None) -> str:
    """A compact, fixed-shape stat line for this week — deliberately not a
    narrative. An earlier version compared each week against a trailing
    baseline ("busier than usual", "well above its typical X kWh"), which was
    more accurate but reads as a growing paragraph of storytelling rather
    than a report a plant operator can scan every week — not scalable as a
    once-a-week generated artifact. This states this week's own numbers only:
    energy intensity, the operational/embodied split, the largest energy
    consumer, and the largest process-loss stage — always the same shape.
    """
    # Read the boundary in force, never the row's own columns — see
    # headline_figures(). Defaulting here keeps the function callable on its
    # own, but every renderer passes the resolved headline.
    headline = headline or headline_figures(row)
    intensity = headline["energy_intensity_kwh_per_tonne"]

    op = headline["operational"] or 0
    em = headline["embodied"] or 0
    total = op + em
    op_share = (op / total * 100) if total else None

    subsystems = [
        (name, row.get(col, 0) or 0)
        for name, col, _ in CN_ENERGY_SUBSYSTEMS
        if name != "Plant Residual"
    ]
    subsystems = [s for s in subsystems if s[1] > 0]
    consumer_stat = "—"
    if subsystems:
        subsystems.sort(key=lambda x: -x[1])
        top_name, top_val = subsystems[0]
        total_energy = sum(v for _, v in subsystems)
        share = (top_val / total_energy * 100) if total_energy else 0
        consumer_stat = f"<b>{top_name}</b> — {top_val:,.0f} kWh ({share:.0f}%)"

    ads = row["total_ads_co2_kg"] or 0
    loss1, loss2, loss3 = row["loss_stage_1_kg"] or 0, row["loss_stage_2_kg"] or 0, row["loss_stage_3_kg"] or 0
    stage_losses = [("Adsorption→Desorption", loss1), ("Desorption→Collection", loss2), ("Collection→Liquefaction", loss3)]
    stage_losses = [s for s in stage_losses if s[1] > 0]
    loss_stat = "—"
    if stage_losses and ads > 0:
        stage_losses.sort(key=lambda x: -x[1])
        top_stage, top_loss = stage_losses[0]
        loss_stat = f"<b>{top_stage}</b> — {top_loss:,.1f} kg ({top_loss / ads * 100:.0f}%)"

    # An undefined ratio prints an em dash rather than a number. A week with no
    # product has no intensity and no meaningful emissions mix; printing "0.0
    # MWh/t · 100% operational / 0% embodied" stated both as facts.
    intensity_stat = f"<b>{intensity / 1000:.1f} MWh/t</b>" if intensity is not None else "—"
    mix_stat = (
        f"<b>{op_share:.0f}% operational</b> / {100 - op_share:.0f}% embodied"
        if op_share is not None else "—"
    )

    stats = [
        f"Energy intensity: {intensity_stat}",
        f"Emissions mix: {mix_stat}",
        f"Largest energy consumer: {consumer_stat}",
        f"Largest process loss: {loss_stat}",
    ]
    return "&nbsp;&nbsp;·&nbsp;&nbsp;".join(stats)


# Chart-card background. `apply_chart_layout` leaves the paper transparent so
# the live app's own card shows through; a standalone report has no such card,
# so both renderers paint this behind the figure instead. It lives here rather
# than in either renderer because the two report formats must agree on it.
CHART_CARD_BG = "#1E293B"


def single_week_subsystem_chart(row: pd.Series) -> Optional[go.Figure]:
    """Horizontal bar of THIS week's energy by subsystem, sorted descending —
    directly answers 'what's using the most energy' for a single-week deep-dive,
    which a multi-week stacked bar (the live dashboard's own chart) isn't built for."""
    items = [
        (name, row.get(col, 0) or 0, color)
        for name, col, color in CN_ENERGY_SUBSYSTEMS
        if name != "Plant Residual"  # instrument error, not something that consumes power
    ]
    items = [item for item in items if item[1] > 0]
    if not items:
        return None
    items.sort(key=lambda x: x[1])

    fig = go.Figure(go.Bar(
        x=[v for _, v, _ in items],
        y=[n for n, _, _ in items],
        orientation="h",
        marker_color=[c for _, _, c in items],
        marker_line_color=CHART_CARD_BG,
        marker_line_width=1,
        text=[f"{v:,.0f} kWh" for _, v, _ in items],
        textposition="outside",
        textfont=dict(color="#F1F5F9", size=11),
        hovertemplate="<b>%{y}</b><br>%{x:,.0f} kWh<extra></extra>",
    ))
    apply_chart_layout(
        fig, title="Energy by Subsystem — This Week", height=max(220, 34 * len(items)),
        xaxis_title="kWh", showlegend=False,
    )
    fig.update_layout(margin=dict(l=110, r=60))
    return fig


def recent_weeks_trend_chart(df: pd.DataFrame, current_start_date) -> Optional[go.Figure]:
    """Removal-efficiency trend over recent weeks, with the reported week highlighted —
    gives context for whether this week is typical, better, or worse than recent history."""
    recent = df.tail(10).copy()
    if len(recent) < 2:
        return None
    # Same basis as the headline, so a zero-liquefaction week isn't plotted at
    # 0% while the hero above it reports the capture-boundary figure.
    recent["removal_efficiency_pct"] = recent.apply(
        lambda r: headline_figures(r)["removal_efficiency"], axis=1,
    )
    recent = recent[recent["removal_efficiency_pct"].notna()]
    if recent.empty:
        return None
    colors_list = [
        "#F97316" if d == current_start_date else "#3DB3B3" for d in recent["start_date"]
    ]
    fig = go.Figure(go.Bar(
        x=recent["week_label"],
        y=recent["removal_efficiency_pct"],
        marker_color=colors_list,
        marker_line_color=CHART_CARD_BG,
        marker_line_width=1,
        text=[f"{v:+.0f}%" for v in recent["removal_efficiency_pct"]],
        textposition="outside",
        textfont=dict(color="#F1F5F9", size=10),
        hovertemplate="<b>%{x}</b><br>%{y:+.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#94A3B8")
    apply_chart_layout(
        fig, title="Removal Efficiency — Recent Weeks (this week in orange)", height=260,
        xaxis_title=None, yaxis_title="Net Removal ÷ Gross Captured (%)", showlegend=False,
    )
    return fig


@dataclass
class WeekReportContext:
    """One week's report inputs, already resolved and computed."""

    df: pd.DataFrame
    row: pd.Series
    week_start: datetime
    week_label: str
    series_filter: Optional[str]
    grid_ef: float
    working_capacity: dict
    series_1n3: dict
    series_2n4: dict

    gross_captured: float
    total_emissions: float
    net_removal: float
    removal_efficiency: Optional[float]
    # The headline's operational/embodied split. Carried explicitly rather than
    # read off `row`, because the row always holds the boundary it was loaded
    # on — reading it directly would print cards that contradict the hero
    # sentence on a week the headline fell back to the capture boundary.
    headline_operational: float
    headline_embodied: float
    # Intensities on the boundary in force, for the same reason. None when the
    # ratio is undefined — renderers must print an em dash, not zero.
    headline_energy_kwh: float
    headline_energy_intensity: Optional[float]
    headline_steam_intensity: Optional[float]
    # "liquefied" (credit-bearing, the norm) or "collected" (this week
    # liquefied nothing). `headline_note` is the disclosure to render, or None.
    headline_basis: str
    headline_note: Optional[str]

    ads_co2: float
    des_co2: float
    bag_co2: float
    liq_co2: float

    desorption_efficiency: Optional[float]
    collection_efficiency: Optional[float]
    liquefaction_efficiency: Optional[float]
    capture_efficiency: Optional[float]

    def headline_dict(self) -> dict:
        """The resolved headline figures reassembled, for helpers that take the
        whole dict rather than individual fields. Keys match headline_figures()
        so either can be passed interchangeably."""
        return {
            "basis": self.headline_basis,
            "operational": self.headline_operational,
            "embodied": self.headline_embodied,
            "energy_kwh": self.headline_energy_kwh,
            "energy_intensity_kwh_per_tonne": self.headline_energy_intensity,
            "steam_intensity_kg_per_tonne": self.headline_steam_intensity,
        }

    @property
    def anomaly_cycles(self) -> list[int]:
        return sorted({
            a["cycle_number"]
            for g in ("A", "B")
            for a in self.working_capacity["groups"][g]["config_anomalies"]
        })

    def get(self, key: str, default: Any = None) -> Any:
        value = self.row.get(key, default)
        return default if value is None else value


def build_week_report_context(
    session, week_start: datetime, series_filter: Optional[str] = None
) -> WeekReportContext:
    """Resolve and compute everything a weekly report needs, in any format.

    Figures come straight from `load_weekly_df_cached` — the exact same function
    the live Dashboard uses — so a report can never silently drift out of sync
    with what the app shows on screen.
    """
    df = load_weekly_df_cached(session, series_filter)
    if df.empty:
        raise ValueError("No Carbon Nest weekly summaries available to report on.")
    matches = df[df["start_date"] == week_start]
    if matches.empty:
        raise ValueError(f"No weekly summary found for week starting {week_start}.")
    row = matches.iloc[0]

    headline = headline_figures(row)
    gross_captured = headline["gross_captured"]
    total_emissions = headline["total_emissions"]
    net_removal = headline["net_removal"]

    # Four process efficiencies, one per physical step of the chain. Each spans
    # exactly one transition and is named after the step it measures:
    #
    #   Desorption    desorbed  / adsorbed   = Athena's per-cycle DES Efficiency
    #   Collection    collected / desorbed   = Athena's per-cycle BAG Efficiency
    #   Liquefaction  liquefied / collected
    #   Capture       liquefied / adsorbed   = the overall chain, and exactly the
    #                                          product of the three above
    #
    # Collection deliberately means collected ÷ DESORBED. It previously meant
    # collected ÷ adsorbed, which silently spanned two stages and reused a name
    # Athena had already assigned to something else — raised by the site team on
    # 2026-08-27, where "collection efficiency" has always meant bag ÷ desorbed.
    # Preserve the one-stage-per-name rule if these are ever edited: it is what
    # makes Desorption × Collection × Liquefaction = Capture hold exactly.
    ads_co2 = row["total_ads_co2_kg"] or 0
    des_co2 = row["total_des_co2_kg"] or 0
    bag_co2 = row["total_bag_co2_kg"] or 0
    liq_co2 = row["liquefied_co2_kg"] or 0

    return WeekReportContext(
        df=df,
        row=row,
        week_start=week_start,
        week_label=(
            f"{row['start_date'].strftime('%b %d')} – {row['end_date'].strftime('%b %d, %Y')}"
        ),
        series_filter=series_filter,
        grid_ef=get_grid_ef_cached(session),
        working_capacity=weekly_working_capacity_cached(session, week_start),
        series_1n3=get_weekly_metrics_by_series(session, week_start, "1n3"),
        series_2n4=get_weekly_metrics_by_series(session, week_start, "2n4"),
        gross_captured=gross_captured,
        total_emissions=total_emissions,
        net_removal=net_removal,
        # None, not 0: a week with no product has no removal efficiency, and
        # "+0.0%" reads as break-even — the single most misleading thing this
        # report could print about a week that captured nothing.
        removal_efficiency=headline["removal_efficiency"],
        headline_operational=headline["operational"],
        headline_embodied=headline["embodied"],
        headline_energy_kwh=headline["energy_kwh"],
        headline_energy_intensity=headline["energy_intensity_kwh_per_tonne"],
        headline_steam_intensity=headline["steam_intensity_kg_per_tonne"],
        headline_basis=headline["basis"],
        headline_note=headline["note"],
        ads_co2=ads_co2,
        des_co2=des_co2,
        bag_co2=bag_co2,
        liq_co2=liq_co2,
        desorption_efficiency=(des_co2 / ads_co2 * 100) if ads_co2 else None,
        collection_efficiency=(bag_co2 / des_co2 * 100) if des_co2 else None,
        # Keyed off collected, not liquefied, so a week that liquefied nothing
        # reports 0.0% rather than "—" — a real and important result, not missing data.
        liquefaction_efficiency=(liq_co2 / bag_co2 * 100) if bag_co2 else None,
        capture_efficiency=(liq_co2 / ads_co2 * 100) if ads_co2 else None,
    )
