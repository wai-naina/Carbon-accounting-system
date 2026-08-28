"""Professional weekly PDF report for Carbon Nest.

Renders the same headline numbers as the live Home/Dashboard pages — Capture &
Removal Efficiency, the emissions/energy breakdown, and recent-week trend context —
as a standalone, downloadable PDF someone can forward, print, or archive.

All figures are pulled straight from `load_weekly_df` (via its cached wrapper —
the exact same function the live Dashboard uses), so this report can never
silently drift out of sync with what the app shows on screen.
"""
from __future__ import annotations

import copy
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

import kaleido
import pandas as pd
import plotly.graph_objects as go
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    Paragraph,
    PageTemplate,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)

from app.components.branding import get_logo_path
from app.components.charts import (
    CN_ENERGY_SUBSYSTEMS,
    apply_chart_layout,
    emissions_breakdown_pie,
    waterfall_chart,
)
from app.database.models import CarbonNestWeeklySummary
from app.pages.cn_dashboard import load_weekly_df_cached
from app.services.carbon_nest_aggregation import get_grid_ef_cached, get_weekly_metrics_by_series
from app.services.carbon_nest_working_capacity import weekly_working_capacity_cached

# --- Print-safe brand palette -------------------------------------------------
# The live app's neon greens/reds/teals are tuned for a dark screen background;
# on white paper the same hex values read as washed-out and fail contrast, so
# these are deliberately deepened equivalents for print use only.
BRAND_DARK = "#0D3B3B"
BRAND_TEAL = "#1A5F5F"
INK = "#1A2420"
MUTED = "#5B6B72"
LINE = "#D8DEDA"
GREEN = "#15803D"
RED = "#B91C1C"
CARD_BG = "#1E293B"  # dark chart-card background — matches the live app's own chart theme
CARD_LINE = "#334155"
PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
HEADER_H = 26 * mm
FOOTER_H = 12 * mm


def _register_unicode_font() -> tuple[str, str, str]:
    """Register a real Unicode-capable TrueType font and return (regular, bold,
    italic) font names to use throughout the document.

    ReportLab's built-in "Helvetica" is a base-14 PDF font limited to roughly the
    WinAnsi/Latin-1 glyph set — arrows (→), the mathematical minus sign (−), and
    subscript numerals (₂) all fall outside it and render as invisible/.notdef
    glyphs (the text is still extractable, it just doesn't draw). A real TTF with
    broad Unicode coverage avoids that and looks more professional than base
    Helvetica. Falls back gracefully to Helvetica if no such font is found (e.g.
    on a non-Windows deployment target), just with reduced glyph coverage there.
    """
    candidates = [
        (
            "PDFReportSans",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\segoeuib.ttf",
            r"C:\Windows\Fonts\segoeuii.ttf",
        ),
        (
            "PDFReportSans",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\ariali.ttf",
        ),
        (
            # Installed via packages.txt's `fonts-liberation` on the hosted
            # deployment (Streamlit Cloud's base image has no fonts of its
            # own beyond the bare minimum) — checked first on Linux since
            # it's guaranteed present there, unlike DejaVu below.
            "PDFReportSans",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        ),
        (
            # Installed via packages.txt's `fonts-dejavu-core` as a second
            # option in case the Liberation path above ever differs.
            "PDFReportSans",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        ),
        (
            "PDFReportSans",
            "/Library/Fonts/Arial.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial Italic.ttf",
        ),
    ]
    for name, regular_path, bold_path, italic_path in candidates:
        if Path(regular_path).exists() and Path(bold_path).exists():
            try:
                pdfmetrics.registerFont(TTFont(name, regular_path))
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", bold_path))
                italic_name = f"{name}-Italic"
                if Path(italic_path).exists():
                    pdfmetrics.registerFont(TTFont(italic_name, italic_path))
                else:
                    italic_name = name
                return name, f"{name}-Bold", italic_name
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"


FONT_REGULAR, FONT_BOLD, FONT_ITALIC = _register_unicode_font()


_chrome_ready = False


def _ensure_chrome() -> None:
    """Kaleido (the library used to rasterize Plotly figures to PNG) needs an
    actual Chrome/Chromium binary to render with, and doesn't bundle one —
    on a bare hosting environment like Streamlit Cloud there's no browser
    pre-installed, which surfaces as `RuntimeError: Kaleido requires Google
    Chrome to be installed`. get_chrome_sync() is Plotly's own documented
    fix (the programmatic equivalent of running `plotly_get_chrome`): it
    downloads a managed, self-contained Chrome build on first use and skips
    the download on every call after, so this only costs time once per
    running server process, not once per report.

    start_sync_server() keeps that one browser alive and reused for every
    chart render after this. Without it, kaleido's default "one-shot" mode
    (confirmed in its own source: calc_fig_sync opens a fresh browser context
    and tears it down per call unless a persistent server is running) means
    a report with ~5 charts launches and kills Chrome 5 separate times
    instead of once. Trade-off: the browser now stays resident in memory for
    the lifetime of the server process instead of only during rendering —
    worth watching if the hosting tier is memory-constrained.
    """
    global _chrome_ready
    if _chrome_ready:
        return
    kaleido.get_chrome_sync()
    kaleido.start_sync_server(silence_warnings=True)
    _chrome_ready = True


def _fig_png(fig: go.Figure, width: int = 1000, height: int = 480, scale: float = 2.0) -> bytes:
    """Rasterize a Plotly figure with a solid dark card background instead of the
    live app's transparent one, which would be unreadable against a white PDF page."""
    _ensure_chrome()
    fig = copy.deepcopy(fig)
    fig.update_layout(paper_bgcolor=CARD_BG, plot_bgcolor=CARD_BG)
    return fig.to_image(format="png", width=width, height=height, scale=scale)


def _styles() -> dict:
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName=FONT_BOLD, fontSize=8.5, leading=11,
            textColor=colors.HexColor(MUTED), tracking=1.2,
        ),
        "hero": ParagraphStyle("hero", fontName=FONT_BOLD, fontSize=40, leading=42),
        "sub": ParagraphStyle("sub", fontName=FONT_REGULAR, fontSize=9, leading=13, textColor=colors.HexColor(MUTED)),
        "h2": ParagraphStyle(
            "h2", fontName=FONT_BOLD, fontSize=13, leading=16,
            textColor=colors.HexColor(BRAND_DARK), spaceBefore=4, spaceAfter=6,
        ),
        "body": ParagraphStyle("body", fontName=FONT_REGULAR, fontSize=9.5, leading=14, textColor=colors.HexColor(INK)),
        "card_label": ParagraphStyle(
            "card_label", fontName=FONT_BOLD, fontSize=7, leading=9,
            textColor=colors.HexColor(MUTED),
        ),
        "card_value": ParagraphStyle("card_value", fontName=FONT_BOLD, fontSize=16, leading=19, textColor=colors.HexColor(INK)),
        "card_sub": ParagraphStyle("card_sub", fontName=FONT_REGULAR, fontSize=6.5, leading=8.5, textColor=colors.HexColor(MUTED)),
        "chart_caption": ParagraphStyle("chart_caption", fontName=FONT_ITALIC, fontSize=8, leading=11, textColor=colors.HexColor(MUTED)),
        "footer_note": ParagraphStyle("footer_note", fontName=FONT_REGULAR, fontSize=7.5, leading=11, textColor=colors.HexColor(MUTED)),
    }


def _kpi_card(label: str, value: str, sub: str, accent_hex: str, styles: dict) -> Table:
    inner = Table(
        [
            [Paragraph(label.upper(), styles["card_label"])],
            [Paragraph(value, styles["card_value"])],
            [Paragraph(sub, styles["card_sub"])] if sub else [Paragraph("", styles["card_sub"])],
        ],
        colWidths=[38 * mm],
    )
    inner.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEABOVE", (0, 0), (-1, 0), 2.5, colors.HexColor(accent_hex)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F9F8")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(LINE)),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ]))
    return inner


def _pct(value: Optional[float]) -> str:
    """A percentage for a KPI card, or an em dash when the ratio is undefined."""
    return f"{value:.1f}%" if value is not None else "—"


def _boundary_note(row: pd.Series) -> str:
    """Subtitle for the Gross Captured card, naming the boundary in force.

    Series-filtered reports can only use the capture boundary — liquefaction is
    a single shared downstream process with no per-series liquefied figure.
    """
    if row.get("boundary") == "capture":
        return "Collected CO₂ (capture boundary)"
    return "Liquefied CO₂ (credit-bearing)"


def _boundaries_note(row: pd.Series) -> str:
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

    direction = "lower" if liq_em < cap_em else "higher"
    return (
        f"The liquefied boundary carries <i>{direction}</i> total emissions but a "
        f"<i>worse</i> net removal — embodied emissions are charged per tonne of product, so "
        f"they shrink with the denominator. CO₂ vented during liquefaction reduces product "
        f"without being charged as an emission: it is atmospheric carbon returning to the "
        f"atmosphere, a failure to remove rather than a new release. Note that bagged CO₂ can "
        f"also carry across a week boundary, so a single week's liquefaction efficiency mixes "
        f"yield with inventory timing."
    )


def _boundaries_table(row: pd.Series, styles: dict) -> Optional[Table]:
    """Side-by-side capture vs liquefied removal, or None if unavailable.

    Returns None for series-filtered reports, where only one boundary exists
    and a comparison would be misleading rather than informative.
    """
    if row.get("boundary") == "capture" or "capture_net_removal_kg" not in row:
        return None

    def eff(net, product):
        return f"{net / product * 100:+.1f}%" if product else "—"

    def mwh(energy, product):
        return f"{energy / (product / 1000) / 1000:,.1f}" if product else "—"

    cap_product = row["capture_gross_kg"] or 0
    liq_product = row["liquefied_gross_kg"] or 0

    header = [
        "Boundary", "Product\n(kg)", "Energy\n(kWh)", "Operational\n(kg)",
        "Embodied\n(kg)", "Net removal\n(kg)", "Efficiency", "MWh/t",
    ]
    body = [
        [
            "A · Capture\n(liquefaction excluded)",
            f"{cap_product:,.1f}",
            f"{row['capture_energy_kwh'] or 0:,.0f}",
            f"{row['capture_operational_emissions_kg'] or 0:,.1f}",
            f"{row['capture_embodied_emissions_kg'] or 0:,.1f}",
            f"{row['capture_net_removal_kg'] or 0:+,.1f}",
            eff(row["capture_net_removal_kg"] or 0, cap_product),
            mwh(row["capture_energy_kwh"] or 0, cap_product),
        ],
        [
            "B · Liquefied\n(credit-bearing)",
            f"{liq_product:,.1f}",
            f"{row['total_energy_kwh'] or 0:,.0f}",
            f"{row['total_operational_emissions_kg'] or 0:,.1f}",
            f"{row['total_embodied_emissions_kg'] or 0:,.1f}",
            f"{row['liquefied_net_removal_kg'] or 0:+,.1f}",
            eff(row["liquefied_net_removal_kg"] or 0, liq_product),
            mwh(row["total_energy_kwh"] or 0, liq_product),
        ],
    ]

    table = Table(
        [header] + body,
        colWidths=[34 * mm, 16 * mm, 18 * mm, 21 * mm, 18 * mm, 21 * mm, 18 * mm, 14 * mm],
    )
    style = [
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor(MUTED)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F0F4F3")),
        ("FONTNAME", (0, 1), (0, -1), FONT_BOLD),
        ("FONTNAME", (1, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 1), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor(INK)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(LINE)),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor(LINE)),
    ]
    # Colour each net-removal cell by its own sign — the two boundaries can
    # legitimately disagree, and that disagreement is the point of the table.
    for offset, net in enumerate((row["capture_net_removal_kg"] or 0, row["liquefied_net_removal_kg"] or 0)):
        accent = GREEN if net > 0 else RED
        style.append(("TEXTCOLOR", (5, 1 + offset), (6, 1 + offset), colors.HexColor(accent)))
        style.append(("FONTNAME", (5, 1 + offset), (6, 1 + offset), FONT_BOLD))
    table.setStyle(TableStyle(style))
    return table


def _draw_letterhead(canvas_obj, doc, week_label: str) -> None:
    canvas_obj.saveState()
    canvas_obj.setFillColor(colors.HexColor(BRAND_DARK))
    canvas_obj.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)

    logo_path = get_logo_path()
    if logo_path:
        try:
            canvas_obj.drawImage(
                str(logo_path), MARGIN, PAGE_H - HEADER_H + 6 * mm,
                width=32 * mm, height=13 * mm, mask="auto", preserveAspectRatio=True, anchor="sw",
            )
        except Exception:
            pass

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(FONT_BOLD, 14)
    canvas_obj.drawRightString(PAGE_W - MARGIN, PAGE_H - 11 * mm, "Carbon Nest — Weekly Report")
    canvas_obj.setFont(FONT_REGULAR, 8.5)
    canvas_obj.setFillColor(colors.HexColor("#9FC7C2"))
    canvas_obj.drawRightString(PAGE_W - MARGIN, PAGE_H - 17 * mm, week_label)

    canvas_obj.setFillColor(colors.HexColor(MUTED))
    canvas_obj.setFont(FONT_REGULAR, 7)
    canvas_obj.drawString(MARGIN, 8 * mm, "Octavia Carbon · Carbon Nest — Direct Air Capture, Gilgil, Kenya")
    canvas_obj.drawRightString(
        PAGE_W - MARGIN, 8 * mm,
        f"Page {doc.page} · Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    )
    canvas_obj.restoreState()


def _single_week_subsystem_chart(row: pd.Series) -> Optional[go.Figure]:
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
        marker_line_color=CARD_BG,
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


def _trend_chart(df: pd.DataFrame, current_start_date) -> Optional[go.Figure]:
    """Removal-efficiency trend over recent weeks, with the reported week highlighted —
    gives context for whether this week is typical, better, or worse than recent history."""
    recent = df.tail(10).copy()
    if len(recent) < 2:
        return None
    recent["removal_efficiency_pct"] = recent.apply(
        lambda r: (r["net_removal_kg"] / r["collected_co2_kg"] * 100) if r["collected_co2_kg"] else 0,
        axis=1,
    )
    colors_list = [
        "#F97316" if d == current_start_date else "#3DB3B3" for d in recent["start_date"]
    ]
    fig = go.Figure(go.Bar(
        x=recent["week_label"],
        y=recent["removal_efficiency_pct"],
        marker_color=colors_list,
        marker_line_color=CARD_BG,
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


def _build_narrative(row: pd.Series) -> str:
    """A compact, fixed-shape stat line for this week — deliberately not a
    narrative. An earlier version compared each week against a trailing
    baseline ("busier than usual", "well above its typical X kWh"), which was
    more accurate but reads as a growing paragraph of storytelling rather
    than a report a plant operator can scan every week — not scalable as a
    once-a-week generated artifact. This states this week's own numbers only:
    energy intensity, the operational/embodied split, the largest energy
    consumer, and the largest process-loss stage — always the same shape.
    """
    intensity = row["energy_intensity_kwh_per_tonne"] or 0

    op = row["total_operational_emissions_kg"] or 0
    em = row["total_embodied_emissions_kg"] or 0
    total = op + em
    op_share = (op / total * 100) if total else 0

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

    stats = [
        f"Energy intensity: <b>{intensity / 1000:.1f} MWh/t</b>",
        f"Emissions mix: <b>{op_share:.0f}% operational</b> / {100 - op_share:.0f}% embodied",
        f"Largest energy consumer: {consumer_stat}",
        f"Largest process loss: {loss_stat}",
    ]
    return "&nbsp;&nbsp;·&nbsp;&nbsp;".join(stats)


def generate_weekly_pdf_report(session, week_start: datetime, series_filter: Optional[str] = None) -> bytes:
    """Build the Carbon Nest weekly PDF report for the week starting at `week_start`.

    Returns raw PDF bytes, ready for st.download_button.
    """
    df = load_weekly_df_cached(session, series_filter)
    if df.empty:
        raise ValueError("No Carbon Nest weekly summaries available to report on.")
    matches = df[df["start_date"] == week_start]
    if matches.empty:
        raise ValueError(f"No weekly summary found for week starting {week_start}.")
    row = matches.iloc[0]
    wc = weekly_working_capacity_cached(session, week_start)

    grid_ef = get_grid_ef_cached(session)
    s1n3 = get_weekly_metrics_by_series(session, week_start, "1n3")
    s2n4 = get_weekly_metrics_by_series(session, week_start, "2n4")

    styles = _styles()
    week_label = f"{row['start_date'].strftime('%b %d')} – {row['end_date'].strftime('%b %d, %Y')}"

    gross_captured = row["collected_co2_kg"] or 0
    total_emissions = row["total_emissions_kg"] or 0
    net_removal = row["net_removal_kg"] or 0
    removal_efficiency = (net_removal / gross_captured * 100) if gross_captured else 0
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
    desorption_efficiency = (des_co2 / ads_co2 * 100) if ads_co2 else None
    collection_efficiency = (bag_co2 / des_co2 * 100) if des_co2 else None
    # Keyed off collected, not liquefied, so a week that liquefied nothing
    # reports 0.0% rather than "—" — a real and important result, not missing data.
    liquefaction_efficiency = (liq_co2 / bag_co2 * 100) if bag_co2 else None
    capture_efficiency = (liq_co2 / ads_co2 * 100) if ads_co2 else None
    eff_color = GREEN if removal_efficiency > 0 else RED

    story = []

    # --- Hero ---
    story.append(Paragraph("CAPTURE &amp; REMOVAL EFFICIENCY", styles["eyebrow"]))
    story.append(Paragraph(
        f'<font color="{eff_color}">{removal_efficiency:+.1f}%</font>', styles["hero"],
    ))
    story.append(Paragraph(
        f"{gross_captured:,.1f} kg captured − {total_emissions:,.1f} kg emitted = "
        f"{net_removal:+,.1f} kg net removal → {removal_efficiency:+.1f}% of what was captured.",
        styles["sub"],
    ))
    story.append(Spacer(1, 8 * mm))

    # --- KPI card row ---
    cards = [
        _kpi_card("Gross Captured", f"{gross_captured:,.1f} kg", _boundary_note(row), "#0EA5E9", styles),
        _kpi_card("Operational Emissions", f"{row['total_operational_emissions_kg']:,.1f} kg", f"Grid EF: {grid_ef:.4f} kg/kWh", "#F59E0B", styles),
        _kpi_card("Embodied Emissions", f"{row['total_embodied_emissions_kg']:,.1f} kg", "Output-based, v0.6 LCA", "#A855F7", styles),
        _kpi_card("Net Removal", f"{net_removal:+,.1f} kg", "Captured minus total emissions", GREEN if net_removal > 0 else RED, styles),
    ]
    card_row = Table([cards], colWidths=[40 * mm] * 4)
    card_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    story.append(card_row)
    story.append(Spacer(1, 3 * mm))

    # The chain in order, left to right, so the reader walks adsorbed → desorbed
    # → bagged → liquefied and lands on the overall figure last.
    cards2 = [
        _kpi_card("Desorption Efficiency", _pct(desorption_efficiency), "Desorbed ÷ Adsorbed", "#A855F7", styles),
        _kpi_card("Collection Efficiency", _pct(collection_efficiency), "Collected ÷ Desorbed", "#3DB3B3", styles),
        _kpi_card("Liquefaction Efficiency", _pct(liquefaction_efficiency), "Liquefied ÷ Collected", "#0EA5E9", styles),
        _kpi_card("Capture Efficiency", _pct(capture_efficiency), "Liquefied ÷ Adsorbed · overall", BRAND_TEAL, styles),
    ]
    card_row2 = Table([cards2], colWidths=[40 * mm] * 4)
    card_row2.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(card_row2)
    story.append(Spacer(1, 3 * mm))

    cards3 = [
        _kpi_card("Cycles This Week", f"{int(row['total_cycles'] or 0)}", f"1n3: {s1n3['cycles']} · 2n4: {s2n4['cycles']}", BRAND_TEAL, styles),
        _kpi_card("Energy Intensity", f"{row['energy_intensity_kwh_per_tonne'] / 1000:.1f} MWh/t" if row["energy_intensity_kwh_per_tonne"] else "—", "Process energy per tonne captured", "#94A3B8", styles),
    ]
    card_row3 = Table([cards3], colWidths=[40 * mm] * 2, hAlign="LEFT")
    # VALIGN TOP so the two cards' accent rules line up even when one card's
    # value wraps to a second line and the other's doesn't.
    card_row3.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(card_row3)
    story.append(Spacer(1, 5 * mm))

    boundaries = _boundaries_table(row, styles)
    if boundaries is not None:
        story.append(Paragraph("Removal Efficiency — With and Without Liquefaction", styles["h2"]))
        story.append(boundaries)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(_boundaries_note(row), styles["sub"]))
        story.append(Spacer(1, 6 * mm))
    else:
        story.append(Spacer(1, 2 * mm))

    # --- Narrative ---
    story.append(Paragraph("What's Driving This Week's Result", styles["h2"]))
    story.append(Paragraph(_build_narrative(row), styles["body"]))
    story.append(Spacer(1, 6 * mm))

    # --- Sorbent working capacity ---
    wc_block = [
        Paragraph("Sorbent Working Capacity", styles["h2"]),
        Paragraph(
            "Desorption-based capacity — mol CO&#8322; released per m&#179; of sorbent bed, "
            "averaged across this week's valid cycles. Not adsorption uptake, not normalised "
            "for hold time.", styles["chart_caption"],
        ),
    ]
    wc_cards = []
    for g in ("A", "B"):
        gr = wc["groups"][g]
        cap = gr["avg_working_capacity_mol_per_m3"]
        value_str = f"{cap:.2f} mol/m³" if cap is not None else "—"
        sub = f"{gr['n_cycles_used']} of {gr['n_cycles_in_window']} cycles used"
        wc_cards.append(_kpi_card(gr["label"], value_str, sub, "#3DB3B3" if g == "A" else "#A855F7", styles))
    wc_row = Table([wc_cards], colWidths=[80 * mm] * 2)
    wc_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    wc_block.append(wc_row)
    anomaly_cycles = sorted({
        a["cycle_number"]
        for g in ("A", "B")
        for a in wc["groups"][g]["config_anomalies"]
    })
    if anomaly_cycles:
        cycle_word = "cycle" if len(anomaly_cycles) == 1 else "cycles"
        verb = "has" if len(anomaly_cycles) == 1 else "have"
        cycle_list = ", ".join(str(n) for n in anomaly_cycles)
        wc_block.append(Paragraph(
            f"Note: {cycle_word} {cycle_list} {verb} an unusual implied bed volume — check sorbent config",
            styles["chart_caption"],
        ))
    story.append(KeepTogether(wc_block))
    story.append(Spacer(1, 6 * mm))

    # --- Desorption steam ---
    steam_kg = row.get("total_steam_kg", 0) or 0
    if steam_kg > 0:
        steam_intensity = row.get("steam_intensity_kg_per_tonne", 0) or 0
        steam_block = [
            Paragraph("Desorption Steam", styles["h2"]),
            Paragraph(
                "Steam is what releases the captured CO&#8322; from the sorbent bed during the "
                "desorption half-cycle — the main driver of Boiler A/B energy below. Intensity "
                "uses the same per-tonne-captured denominator as Energy Intensity.",
                styles["chart_caption"],
            ),
        ]
        steam_cards = [
            _kpi_card(
                "Steam Used", f"{steam_kg:,.0f} kg",
                f"1n3: {s1n3['steam_kg']:,.0f} kg · 2n4: {s2n4['steam_kg']:,.0f} kg",
                "#0EA5E9", styles,
            ),
            _kpi_card(
                "Steam Intensity",
                f"{steam_intensity:,.0f} kg/t" if steam_intensity else "—",
                "kg steam per tonne CO&#8322; captured", "#F59E0B", styles,
            ),
        ]
        steam_row = Table([steam_cards], colWidths=[80 * mm] * 2)
        steam_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
        steam_block.append(steam_row)
        story.append(KeepTogether(steam_block))
        story.append(Spacer(1, 6 * mm))

    # --- Carbon balance waterfall ---
    # Each heading is kept together with its own first chart/paragraph (KeepTogether)
    # so a page break can never strand a heading alone at the bottom of a page with
    # its content pushed to the next one.
    balance_block = [Paragraph("Carbon Balance", styles["h2"])]
    wf = waterfall_chart(gross_captured, row["total_operational_emissions_kg"], row["total_embodied_emissions_kg"])
    if wf:
        png = _fig_png(wf, width=1000, height=420)
        balance_block.append(RLImage(io.BytesIO(png), width=170 * mm, height=170 * mm * 420 / 1000))
        balance_block.append(Paragraph(
            "Reads left to right: what was captured, what it cost in operational and embodied "
            "emissions, and what's left over.", styles["chart_caption"],
        ))
    story.append(KeepTogether(balance_block))
    story.append(Spacer(1, 6 * mm))

    # --- Energy by subsystem (this week) + emissions split ---
    subsystem_block = [Paragraph("Energy &amp; Emissions Breakdown", styles["h2"])]
    subsystem_fig = _single_week_subsystem_chart(row)
    if subsystem_fig:
        png = _fig_png(subsystem_fig, width=1000, height=max(220, 34 * 8))
        h = 170 * mm * subsystem_fig.layout.height / 1000
        subsystem_block.append(RLImage(io.BytesIO(png), width=170 * mm, height=h))
        subsystem_block.append(Paragraph(
            "Boiler A/B energy use should track roughly with cycle count — a subsystem growing "
            "out of proportion to the others is worth a second look.", styles["chart_caption"],
        ))
    story.append(KeepTogether(subsystem_block))
    story.append(Spacer(1, 5 * mm))

    pie = emissions_breakdown_pie(pd.DataFrame([row]))
    if pie:
        pie_block = []
        png = _fig_png(pie, width=900, height=420)
        pie_block.append(RLImage(io.BytesIO(png), width=140 * mm, height=140 * mm * 420 / 900))
        pie_block.append(Paragraph(
            "A large Embodied slice usually means captured tonnage is still low relative to the "
            "plant's fixed footprint — not that operations got worse.", styles["chart_caption"],
        ))
        story.append(KeepTogether(pie_block))
    story.append(Spacer(1, 6 * mm))

    # --- Trend context ---
    trend_fig = _trend_chart(df, row["start_date"])
    if trend_fig is not None:
        trend_block = [Paragraph("Recent-Week Context", styles["h2"])]
        png = _fig_png(trend_fig, width=1000, height=260)
        trend_block.append(RLImage(io.BytesIO(png), width=170 * mm, height=170 * mm * 260 / 1000))
        story.append(KeepTogether(trend_block))
        story.append(Spacer(1, 6 * mm))

    # --- Methodology footer ---
    story.append(KeepTogether([
        Paragraph("Methodology", styles["h2"]),
        Paragraph(
            f"Operational emissions = metered energy × grid emission factor ({grid_ef:.4f} kg CO&#8322;/kWh). "
            "Embodied emissions are output-based: v0.6 LCA driver intensities (kg CO&#8322;-eq per tonne) applied "
            "to CO&#8322; actually captured this week, covering infrastructure and sorbent-chain pools only — "
            "energy is deliberately excluded from embodied since real metered energy is charged separately, "
            "avoiding double-counting. Removal efficiency = (Gross Captured − Total Emissions) ÷ Gross "
            "Captured. Data: Carbon Nest cycle exports + Athena weekly report manual utility entries.",
            styles["footer_note"],
        ),
    ]))

    buf = io.BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=A4,
        topMargin=HEADER_H + 4 * mm, bottomMargin=FOOTER_H + 4 * mm,
        leftMargin=MARGIN, rightMargin=MARGIN,
        title=f"Carbon Nest Weekly Report — {week_label}",
        author="Octavia Carbon — Carbon Accounting System",
    )
    frame = Frame(
        MARGIN, FOOTER_H + 4 * mm, PAGE_W - 2 * MARGIN, PAGE_H - HEADER_H - FOOTER_H - 8 * mm,
        id="body",
    )
    doc.addPageTemplates([
        PageTemplate(id="main", frames=[frame], onPage=lambda c, d: _draw_letterhead(c, d, week_label)),
    ])
    doc.build(story)
    return buf.getvalue()
