"""The weekly report as a self-contained HTML file, for hosts with no browser.

This is the fallback for the PDF path. The PDF needs Chrome to rasterize its
Plotly figures into PNGs; HTML doesn't need to rasterize anything — the reader's
own browser draws the figures, so this renders on any host, which is the whole
point of it existing. The charts come out interactive rather than flat, which
is a small gain over the PDF rather than a compromise.

Content is deliberately the same week, the same figures and the same sentences
as the PDF: both read one `WeekReportContext`, so switching format changes the
container and nothing inside it.

Plotly's own JavaScript is inlined into the first figure and omitted from the
rest, so the download is one file that opens with no network access — matching
what the PDF gave you. That costs roughly 3.5 MB per report; the `cdn` option
would trade that for a file that renders blank charts offline, which is the
wrong trade for something meant to be forwarded and archived.
"""
from __future__ import annotations

import base64
import html
from datetime import datetime
from typing import Optional

import plotly.graph_objects as go

from app.components.branding import get_logo_path
from app.components.charts import emissions_breakdown_pie, waterfall_chart
from app.services.report_data import (
    BASIS_LABEL,
    CHART_CARD_BG,
    WeekReportContext,
    boundaries_note,
    boundary_note,
    build_narrative,
    build_week_report_context,
    pct,
    recent_weeks_trend_chart,
    single_week_subsystem_chart,
)

import pandas as pd

# Screen palette. The PDF deepens the brand greens/reds for print because thin
# ink on white paper reads washed out; on a screen the live app's own values are
# correct, so this deliberately does not reuse the PDF's print palette.
BRAND_DARK = "#0D3B3B"
BRAND_TEAL = "#3DB3B3"
INK = "#1A2420"
MUTED = "#5B6B72"
LINE = "#D8DEDA"
GREEN = "#16A34A"
RED = "#DC2626"


class _FigureEmbedder:
    """Emits figure divs, inlining plotly.js exactly once.

    Tracked with a flag rather than "is this the first chart" because any
    section's figure can legitimately be None for a given week — a week with no
    liquefaction has no waterfall — so which figure comes out first isn't known
    until it's actually rendered.
    """

    def __init__(self) -> None:
        self._js_emitted = False

    def __call__(self, fig: Optional[go.Figure], caption: str = "") -> str:
        if fig is None:
            return ""
        fig = go.Figure(fig)
        fig.update_layout(paper_bgcolor=CHART_CARD_BG, plot_bgcolor=CHART_CARD_BG)
        div = fig.to_html(
            full_html=False,
            include_plotlyjs=True if not self._js_emitted else False,
            config={"displaylogo": False, "responsive": True},
        )
        self._js_emitted = True
        caption_html = f'<p class="caption">{caption}</p>' if caption else ""
        return f'<div class="chart-card">{div}</div>{caption_html}'


def _logo_data_uri() -> Optional[str]:
    """The logo as a data: URI so the file stays self-contained."""
    logo_path = get_logo_path()
    if logo_path is None:
        return None
    suffix = logo_path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".webp": "image/webp",
    }.get(suffix)
    if mime is None:
        return None
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime};base64,{encoded}"


def _kpi_card(label: str, value: str, sub: str, accent: str) -> str:
    return (
        f'<div class="kpi" style="border-top-color:{accent}">'
        f'<div class="kpi-label">{html.escape(label).upper()}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="kpi-sub">{sub}</div>'
        f"</div>"
    )


def _boundaries_table(row: pd.Series) -> str:
    """Side-by-side capture vs liquefied removal, or empty for series-filtered
    reports, where only one boundary exists and a comparison would mislead."""
    if row.get("boundary") == "capture" or "capture_net_removal_kg" not in row:
        return ""

    def eff(net, product):
        return f"{net / product * 100:+.1f}%" if product else "—"

    def mwh(energy, product):
        return f"{energy / (product / 1000) / 1000:,.1f}" if product else "—"

    cap_product = row["capture_gross_kg"] or 0
    liq_product = row["liquefied_gross_kg"] or 0
    cap_net = row["capture_net_removal_kg"] or 0
    liq_net = row["liquefied_net_removal_kg"] or 0

    headers = [
        "Boundary", "Product (kg)", "Energy (kWh)", "Operational (kg)",
        "Embodied (kg)", "Net removal (kg)", "Efficiency", "MWh/t",
    ]
    rows = [
        (
            "A · Capture<br><span class='dim'>liquefaction excluded</span>",
            f"{cap_product:,.1f}",
            f"{row['capture_energy_kwh'] or 0:,.0f}",
            f"{row['capture_operational_emissions_kg'] or 0:,.1f}",
            f"{row['capture_embodied_emissions_kg'] or 0:,.1f}",
            f"{cap_net:+,.1f}",
            eff(cap_net, cap_product),
            mwh(row["capture_energy_kwh"] or 0, cap_product),
            cap_net,
        ),
        (
            "B · Liquefied<br><span class='dim'>credit-bearing</span>",
            f"{liq_product:,.1f}",
            f"{row['total_energy_kwh'] or 0:,.0f}",
            f"{row['total_operational_emissions_kg'] or 0:,.1f}",
            f"{row['total_embodied_emissions_kg'] or 0:,.1f}",
            f"{liq_net:+,.1f}",
            eff(liq_net, liq_product),
            mwh(row["total_energy_kwh"] or 0, liq_product),
            liq_net,
        ),
    ]

    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = []
    for name, product, energy, op, emb, net, efficiency, intensity, net_value in rows:
        # Each net-removal cell is coloured by its own sign — the two boundaries
        # can legitimately disagree, and that disagreement is the point.
        accent = GREEN if net_value > 0 else RED
        body.append(
            f"<tr><th scope='row'>{name}</th>"
            f"<td>{product}</td><td>{energy}</td><td>{op}</td><td>{emb}</td>"
            f"<td class='net' style='color:{accent}'>{net}</td>"
            f"<td class='net' style='color:{accent}'>{efficiency}</td>"
            f"<td>{intensity}</td></tr>"
        )
    return (
        '<div class="table-scroll"><table class="boundaries">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody>"
        "</table></div>"
    )


def generate_weekly_html_report(
    session,
    week_start: datetime,
    series_filter: Optional[str] = None,
    context: Optional[WeekReportContext] = None,
) -> str:
    """Build the Carbon Nest weekly report as one self-contained HTML document.

    Returns a complete HTML string, ready for st.download_button.
    """
    ctx = context or build_week_report_context(session, week_start, series_filter)
    row = ctx.row
    embed = _FigureEmbedder()

    eff_str = f"{ctx.removal_efficiency:+.1f}%" if ctx.removal_efficiency is not None else "&mdash;"
    eff_color = RED if (ctx.removal_efficiency or 0) <= 0 else GREEN
    logo = _logo_data_uri()
    logo_html = (
        f'<img class="logo" src="{logo}" alt="Octavia Carbon">' if logo
        else '<div class="logo-text">OCTAVIA CARBON</div>'
    )

    cards1 = "".join([
        _kpi_card("Gross Captured", f"{ctx.gross_captured:,.1f} kg",
                  boundary_note(row, ctx.headline_basis), "#0EA5E9"),
        _kpi_card("Operational Emissions", f"{ctx.headline_operational:,.1f} kg",
                  f"Grid EF: {ctx.grid_ef:.4f} kg/kWh", "#F59E0B"),
        _kpi_card("Embodied Emissions", f"{ctx.headline_embodied:,.1f} kg",
                  "Output-based, v0.6 LCA", "#A855F7"),
        _kpi_card("Net Removal", f"{ctx.net_removal:+,.1f} kg", "Captured minus total emissions",
                  GREEN if ctx.net_removal > 0 else RED),
    ])
    # The chain in order, left to right, so the reader walks adsorbed → desorbed
    # → bagged → liquefied and lands on the overall figure last.
    cards2 = "".join([
        _kpi_card("Desorption Efficiency", pct(ctx.desorption_efficiency), "Desorbed ÷ Adsorbed", "#A855F7"),
        _kpi_card("Collection Efficiency", pct(ctx.collection_efficiency), "Collected ÷ Desorbed", BRAND_TEAL),
        _kpi_card("Liquefaction Efficiency", pct(ctx.liquefaction_efficiency), "Liquefied ÷ Collected", "#0EA5E9"),
        _kpi_card("Capture Efficiency", pct(ctx.capture_efficiency), "Liquefied ÷ Adsorbed · overall", BRAND_DARK),
    ])
    # Intensity comes off the resolved headline, not the row: on a week the
    # headline fell back to the capture boundary, the row still holds the
    # liquefied basis and this card printed an em dash beside a boundary table
    # reporting 41.7 MWh/t for the same week.
    intensity = ctx.headline_energy_intensity
    cards3 = "".join([
        _kpi_card("Cycles This Week", f"{int(row['total_cycles'] or 0)}",
                  f"1n3: {ctx.series_1n3['cycles']} · 2n4: {ctx.series_2n4['cycles']}", BRAND_DARK),
        _kpi_card("Energy Intensity",
                  f"{intensity / 1000:.1f} MWh/t" if intensity is not None else "—",
                  f"Metered energy per tonne · {BASIS_LABEL[ctx.headline_basis]}", "#94A3B8"),
    ])

    sections: list[str] = []

    boundaries = _boundaries_table(row)
    if boundaries:
        sections.append(
            "<h2>Removal Efficiency — With and Without Liquefaction</h2>"
            f"{boundaries}<p class='note'>{boundaries_note(row)}</p>"
        )

    sections.append(
        "<h2>What's Driving This Week's Result</h2>"
        f"<p class='body'>{build_narrative(row, ctx.headline_dict())}</p>"
    )

    # --- Sorbent working capacity ---
    wc_cards = []
    for group_key in ("A", "B"):
        group = ctx.working_capacity["groups"][group_key]
        capacity = group["avg_working_capacity_mol_per_m3"]
        wc_cards.append(_kpi_card(
            group["label"],
            f"{capacity:.2f} mol/m³" if capacity is not None else "—",
            f"{group['n_cycles_used']} of {group['n_cycles_in_window']} cycles used",
            BRAND_TEAL if group_key == "A" else "#A855F7",
        ))
    wc_section = [
        "<h2>Sorbent Working Capacity</h2>",
        "<p class='caption'>Desorption-based capacity — mol CO&#8322; released per m&#179; of "
        "sorbent bed, averaged across this week's valid cycles. Not adsorption uptake, not "
        "normalised for hold time.</p>",
        f"<div class='kpi-row kpi-row-2'>{''.join(wc_cards)}</div>",
    ]
    if ctx.anomaly_cycles:
        cycle_word = "cycle" if len(ctx.anomaly_cycles) == 1 else "cycles"
        verb = "has" if len(ctx.anomaly_cycles) == 1 else "have"
        cycle_list = ", ".join(str(n) for n in ctx.anomaly_cycles)
        wc_section.append(
            f"<p class='caption'>Note: {cycle_word} {cycle_list} {verb} an unusual implied "
            "bed volume — check sorbent config</p>"
        )
    sections.append("".join(wc_section))

    # --- Desorption steam ---
    steam_kg = row.get("total_steam_kg", 0) or 0
    if steam_kg > 0:
        steam_intensity = ctx.headline_steam_intensity
        steam_cards = "".join([
            _kpi_card("Steam Used", f"{steam_kg:,.0f} kg",
                      f"1n3: {ctx.series_1n3['steam_kg']:,.0f} kg · "
                      f"2n4: {ctx.series_2n4['steam_kg']:,.0f} kg", "#0EA5E9"),
            _kpi_card("Steam Intensity",
                      f"{steam_intensity:,.0f} kg/t" if steam_intensity is not None else "—",
                      f"kg steam per tonne · {BASIS_LABEL[ctx.headline_basis]}", "#F59E0B"),
        ])
        sections.append(
            "<h2>Desorption Steam</h2>"
            "<p class='caption'>Steam is what releases the captured CO&#8322; from the sorbent bed "
            "during the desorption half-cycle — the main driver of Boiler A/B energy below. "
            "Intensity uses the same per-tonne-captured denominator as Energy Intensity.</p>"
            f"<div class='kpi-row kpi-row-2'>{steam_cards}</div>"
        )

    # --- Charts ---
    balance = embed(
        waterfall_chart(
            ctx.gross_captured,
            ctx.headline_operational,
            ctx.headline_embodied,
        ),
        "Reads left to right: what was captured, what it cost in operational and embodied "
        "emissions, and what's left over.",
    )
    if balance:
        sections.append(f"<h2>Carbon Balance</h2>{balance}")

    subsystem = embed(
        single_week_subsystem_chart(row),
        "Boiler A/B energy use should track roughly with cycle count — a subsystem growing "
        "out of proportion to the others is worth a second look.",
    )
    pie = embed(
        emissions_breakdown_pie(pd.DataFrame([row])),
        "A large Embodied slice usually means captured tonnage is still low relative to the "
        "plant's fixed footprint — not that operations got worse.",
    )
    if subsystem or pie:
        sections.append(f"<h2>Energy &amp; Emissions Breakdown</h2>{subsystem}{pie}")

    trend = embed(recent_weeks_trend_chart(ctx.df, row["start_date"]))
    if trend:
        sections.append(f"<h2>Recent-Week Context</h2>{trend}")

    sections.append(
        "<h2>Methodology</h2>"
        f"<p class='footer-note'>Operational emissions = metered energy × grid emission factor "
        f"({ctx.grid_ef:.4f} kg CO&#8322;/kWh). Embodied emissions are output-based: v0.6 LCA driver "
        "intensities (kg CO&#8322;-eq per tonne) applied to CO&#8322; actually captured this week, "
        "covering infrastructure and sorbent-chain pools only — energy is deliberately excluded "
        "from embodied since real metered energy is charged separately, avoiding double-counting. "
        "Removal efficiency = (Gross Captured − Total Emissions) ÷ Gross Captured. Data: Carbon "
        "Nest cycle exports + Athena weekly report manual utility entries.</p>"
    )

    # Rendered directly under the hero, so the basis cannot be read without
    # also reading why. Empty string when the normal liquefied basis applies.
    fallback_banner = (
        '<p class="basis-note"><strong>Reported on the capture boundary.</strong> '
        f'{html.escape(ctx.headline_note)}</p>'
        if ctx.headline_note else ""
    )

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Carbon Nest Weekly Report — {html.escape(ctx.week_label)}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: #F4F6F5; color: {INK};
    font: 15px/1.55 "Segoe UI", Inter, -apple-system, "Helvetica Neue", Arial, sans-serif;
  }}
  .sheet {{ max-width: 1000px; margin: 0 auto; background: #fff;
            box-shadow: 0 1px 3px rgba(0,0,0,.09); }}
  header.letterhead {{
    background: {BRAND_DARK}; color: #fff; padding: 18px 28px;
    display: flex; align-items: center; justify-content: space-between; gap: 20px;
  }}
  .logo {{ height: 44px; width: auto; }}
  .logo-text {{ font-size: 17px; font-weight: 300; letter-spacing: 4px; color: {BRAND_TEAL}; }}
  .letterhead .title {{ text-align: right; }}
  .letterhead .title h1 {{ margin: 0; font-size: 19px; font-weight: 700; }}
  .letterhead .title p {{ margin: 3px 0 0; font-size: 13px; color: #9FC7C2; }}
  main {{ padding: 28px; }}
  .eyebrow {{ font-size: 11px; font-weight: 700; letter-spacing: 1.2px; color: {MUTED};
              margin: 0 0 6px; }}
  .hero {{ font-size: 54px; font-weight: 700; line-height: 1.05; margin: 0;
           color: {eff_color}; }}
  .hero-sub {{ margin: 8px 0 26px; font-size: 14px; color: {MUTED}; max-width: 68ch; }}
  .basis-note {{ margin: -14px 0 26px; padding: 10px 14px; font-size: 13px;
                 max-width: 78ch; border-left: 4px solid #F59E0B;
                 background: #FEF7E7; color: #6B4E00; border-radius: 3px; }}
  h2 {{ font-size: 17px; color: {BRAND_DARK}; margin: 32px 0 10px;
        padding-bottom: 6px; border-bottom: 1px solid {LINE}; }}
  .kpi-row {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr));
              gap: 10px; margin-bottom: 10px; }}
  .kpi-row-2 {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
  @media (max-width: 760px) {{
    .kpi-row, .kpi-row-2 {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
  }}
  .kpi {{ background: #F7F9F8; border: 1px solid {LINE}; border-top: 3px solid {MUTED};
          padding: 10px 12px 12px; }}
  .kpi-label {{ font-size: 10px; font-weight: 700; letter-spacing: .4px; color: {MUTED}; }}
  .kpi-value {{ font-size: 24px; font-weight: 700; margin: 4px 0 2px; }}
  .kpi-sub {{ font-size: 11px; color: {MUTED}; }}
  .table-scroll {{ overflow-x: auto; }}
  table.boundaries {{ border-collapse: collapse; width: 100%; min-width: 720px;
                      font-size: 13px; }}
  table.boundaries th, table.boundaries td {{ border: 1px solid {LINE};
                                              padding: 7px 9px; text-align: right; }}
  table.boundaries thead th {{ background: #F0F4F3; color: {MUTED}; font-size: 11px;
                               font-weight: 700; text-align: right; }}
  table.boundaries thead th:first-child,
  table.boundaries tbody th {{ text-align: left; }}
  table.boundaries tbody th {{ font-weight: 700; }}
  table.boundaries .net {{ font-weight: 700; }}
  .dim {{ color: {MUTED}; font-weight: 400; font-size: 11px; }}
  .note, .body {{ font-size: 14px; max-width: 78ch; }}
  .caption {{ font-size: 12px; color: {MUTED}; font-style: italic; max-width: 78ch;
              margin: 6px 0 10px; }}
  .footer-note {{ font-size: 12px; color: {MUTED}; max-width: 86ch; }}
  .chart-card {{ background: {CHART_CARD_BG}; border-radius: 6px; padding: 8px;
                 margin: 10px 0 0; overflow-x: auto; }}
  footer.colophon {{ border-top: 1px solid {LINE}; margin-top: 34px; padding: 14px 28px;
                     display: flex; justify-content: space-between; gap: 16px;
                     font-size: 11px; color: {MUTED}; }}
  @media print {{
    body {{ background: #fff; }}
    .sheet {{ box-shadow: none; max-width: none; }}
    h2 {{ break-after: avoid; }}
    .chart-card {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="sheet">
  <header class="letterhead">
    {logo_html}
    <div class="title">
      <h1>Carbon Nest — Weekly Report</h1>
      <p>{html.escape(ctx.week_label)}</p>
    </div>
  </header>
  <main>
    <p class="eyebrow">CAPTURE &amp; REMOVAL EFFICIENCY</p>
    <p class="hero">{eff_str}</p>
    <p class="hero-sub">{ctx.gross_captured:,.1f} kg captured &minus;
      {ctx.total_emissions:,.1f} kg emitted = {ctx.net_removal:+,.1f} kg net removal
      &rarr; {eff_str} of what was captured.</p>
    {fallback_banner}
    <div class="kpi-row">{cards1}</div>
    <div class="kpi-row">{cards2}</div>
    <div class="kpi-row kpi-row-2">{cards3}</div>
    {"".join(sections)}
  </main>
  <footer class="colophon">
    <span>Octavia Carbon &middot; Carbon Nest — Direct Air Capture, Gilgil, Kenya</span>
    <span>Generated {generated}</span>
  </footer>
</div>
</body>
</html>
"""
