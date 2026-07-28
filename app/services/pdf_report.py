"""Professional weekly PDF report for Carbon Nest.

Renders the same headline numbers as the live Home/Dashboard pages — Capture &
Removal Efficiency, the emissions/energy breakdown, and recent-week trend context —
as a standalone, downloadable PDF someone can forward, print, or archive.

All figures are pulled straight from `load_weekly_df` (the exact same function the
live Dashboard uses), so this report can never silently drift out of sync with what
the app shows on screen.
"""
from __future__ import annotations

import copy
import io
from datetime import datetime
from pathlib import Path
from statistics import median
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
from app.pages.cn_dashboard import load_weekly_df
from app.services.carbon_nest_aggregation import get_grid_ef, get_weekly_metrics_by_series
from app.services.carbon_nest_working_capacity import weekly_working_capacity

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
    running server process, not once per report."""
    global _chrome_ready
    if _chrome_ready:
        return
    kaleido.get_chrome_sync()
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
        if name != "Main Utility"  # legacy/being-replaced bucket, not a real subsystem to rank
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


_ANOMALY_LOW, _ANOMALY_HIGH = 0.7, 1.4  # "notably different from typical" thresholds


def _typical(values: pd.Series, min_samples: int = 2) -> Optional[float]:
    """Median of prior weeks' values, ignoring structural zeros (e.g. energy
    intensity is 0 when there was nothing to divide by, not a real reading of
    zero) — None if there isn't enough history yet to call anything "typical"."""
    clean = values[values > 0]
    return median(clean) if len(clean) >= min_samples else None


def _build_narrative(row: pd.Series, df: pd.DataFrame) -> str:
    """A short, data-driven paragraph comparing THIS week against its own recent
    baseline — not just describing proportions within the week in isolation.

    Proportional framing alone ("X was the biggest consumer, Y% of the total")
    is misleading on its own: a week running at a fraction of normal activity
    produces the same-shaped sentence as a full week, without it meaning
    anything close to the same thing (256 kWh of Boiler A in a 13-cycle week
    reads identically to 7,744 kWh in a 57-cycle week if nothing says which is
    which). Every comparison below is against the trailing weeks *before* this
    one, so the reader knows whether a number is normal, unusually small, or
    unusually large for this plant — not just its share of this week's own pie.
    """
    prior = df[df["start_date"] < row["start_date"]]
    parts = []

    if len(prior) < 2:
        parts.append(
            "This is one of the earliest tracked weeks — there isn't enough history yet "
            "to say whether this week's figures are typical, so treat the numbers below "
            "as absolute readings, not as compared against a steady state."
        )

    # --- Activity level first: frames how to read everything that follows ---
    cycles = row["total_cycles"] or 0
    typical_cycles = _typical(prior["total_cycles"]) if "total_cycles" in prior.columns else None
    if typical_cycles:
        ratio = cycles / typical_cycles if typical_cycles else 0
        if ratio < _ANOMALY_LOW:
            parts.append(
                f"This was a <b>light week</b> — {int(cycles)} cycles versus a typical "
                f"~{typical_cycles:.0f} — so the figures below are smaller than usual, and "
                f"proportional shares can shift without reflecting any real process change."
            )
        elif ratio > _ANOMALY_HIGH:
            parts.append(
                f"This was a <b>busier week than usual</b> — {int(cycles)} cycles versus a "
                f"typical ~{typical_cycles:.0f}."
            )

    # --- Energy intensity vs baseline: the actual driver of whether operational
    # emissions per tonne captured got better or worse, as opposed to just
    # naming whichever subsystem happens to be biggest ---
    intensity = row["energy_intensity_kwh_per_tonne"] or 0
    typical_intensity = _typical(prior["energy_intensity_kwh_per_tonne"]) if "energy_intensity_kwh_per_tonne" in prior.columns else None
    if intensity > 0 and typical_intensity:
        ratio = intensity / typical_intensity
        if ratio < _ANOMALY_LOW:
            parts.append(
                f"Energy intensity was {intensity / 1000:.1f} MWh/t this week, well below the "
                f"typical ~{typical_intensity / 1000:.1f} MWh/t — the main reason operational "
                f"emissions per tonne captured were lower than usual."
            )
        elif ratio > _ANOMALY_HIGH:
            parts.append(
                f"Energy intensity was {intensity / 1000:.1f} MWh/t this week, well above the "
                f"typical ~{typical_intensity / 1000:.1f} MWh/t — the main reason operational "
                f"emissions per tonne captured were higher than usual."
            )

    # --- Emissions mix, with the structural reason folded in rather than left
    # for the reader to wrongly infer "embodied got worse" ---
    op = row["total_operational_emissions_kg"] or 0
    em = row["total_embodied_emissions_kg"] or 0
    total = op + em
    if total > 0:
        op_share = op / total * 100
        bigger = "operational" if op >= em else "embodied"
        parts.append(
            f"<b>{bigger}</b> emissions were the larger contributor to the total this week "
            f"({op_share:.0f}% operational vs {100 - op_share:.0f}% embodied) — embodied is a "
            f"near-fixed per-tonne charge, so its share rises whenever less is captured, "
            f"independent of anything operational."
        )

    # --- Top energy consumer, contextualized against its OWN typical usage —
    # not just its share of a pie that may itself be unusually small or large ---
    subsystems = [
        (name, row.get(col, 0) or 0, col)
        for name, col, _ in CN_ENERGY_SUBSYSTEMS
        if name not in ("Main Utility",)
    ]
    subsystems = [s for s in subsystems if s[1] > 0]
    if subsystems:
        subsystems.sort(key=lambda x: -x[1])
        top_name, top_val, top_col = subsystems[0]
        total_energy = sum(v for _, v, _ in subsystems)
        share = (top_val / total_energy * 100) if total_energy else 0
        typical_top = _typical(prior[top_col]) if top_col in prior.columns else None
        context = ""
        if typical_top:
            ratio = top_val / typical_top
            if ratio < 0.6:
                context = f" — well below its typical ~{typical_top:,.0f} kWh"
            elif ratio > _ANOMALY_HIGH:
                context = f" — well above its typical ~{typical_top:,.0f} kWh"
            else:
                context = f", in line with its typical ~{typical_top:,.0f} kWh"
        parts.append(
            f"<b>{top_name}</b> was the largest single energy consumer this week "
            f"({top_val:,.0f} kWh, {share:.0f}% of metered process + liquefaction energy)"
            f"{context}."
        )

    # --- Top process-loss stage — about the physical process itself, not
    # confounded by week-to-week activity scale the same way the above are ---
    ads = row["total_ads_co2_kg"] or 0
    loss1, loss2, loss3 = row["loss_stage_1_kg"] or 0, row["loss_stage_2_kg"] or 0, row["loss_stage_3_kg"] or 0
    stage_losses = [("adsorption → desorption", loss1), ("desorption → collection", loss2), ("collection → liquefaction", loss3)]
    stage_losses = [s for s in stage_losses if s[1] > 0]
    if stage_losses and ads > 0:
        stage_losses.sort(key=lambda x: -x[1])
        top_stage, top_loss = stage_losses[0]
        parts.append(
            f"On the process side, the <b>{top_stage}</b> stage accounted for the largest single "
            f"loss of CO&#8322; ({top_loss:,.1f} kg, {top_loss / ads * 100:.0f}% of gross adsorbed CO&#8322;) "
            f"— this is what limits how much of what's adsorbed ultimately counts as captured."
        )
    return " ".join(parts) if parts else "Not enough data this week to break down contributing factors."


def generate_weekly_pdf_report(session, week_start: datetime, series_filter: Optional[str] = None) -> bytes:
    """Build the Carbon Nest weekly PDF report for the week starting at `week_start`.

    Returns raw PDF bytes, ready for st.download_button.
    """
    df = load_weekly_df(session, series_filter)
    if df.empty:
        raise ValueError("No Carbon Nest weekly summaries available to report on.")
    matches = df[df["start_date"] == week_start]
    if matches.empty:
        raise ValueError(f"No weekly summary found for week starting {week_start}.")
    row = matches.iloc[0]
    wc = weekly_working_capacity(session, week_start)

    grid_ef = get_grid_ef(session)
    s1n3 = get_weekly_metrics_by_series(session, week_start, "1n3")
    s2n4 = get_weekly_metrics_by_series(session, week_start, "2n4")

    styles = _styles()
    week_label = f"{row['start_date'].strftime('%b %d')} – {row['end_date'].strftime('%b %d, %Y')}"

    gross_captured = row["collected_co2_kg"] or 0
    total_emissions = row["total_emissions_kg"] or 0
    net_removal = row["net_removal_kg"] or 0
    removal_efficiency = (net_removal / gross_captured * 100) if gross_captured else 0
    collection_efficiency = (row["total_bag_co2_kg"] / row["total_ads_co2_kg"] * 100) if row["total_ads_co2_kg"] else None
    liquefaction_efficiency = (
        row["liquefied_co2_kg"] / row["total_bag_co2_kg"] * 100
        if row["liquefied_co2_kg"] and row["total_bag_co2_kg"] else None
    )
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
        _kpi_card("Gross Captured", f"{gross_captured:,.1f} kg", "Liquefied if available, else collected", "#0EA5E9", styles),
        _kpi_card("Operational Emissions", f"{row['total_operational_emissions_kg']:,.1f} kg", f"Grid EF: {grid_ef:.4f} kg/kWh", "#F59E0B", styles),
        _kpi_card("Embodied Emissions", f"{row['total_embodied_emissions_kg']:,.1f} kg", "Output-based, v0.6 LCA", "#A855F7", styles),
        _kpi_card("Net Removal", f"{net_removal:+,.1f} kg", "Captured minus total emissions", GREEN if net_removal > 0 else RED, styles),
    ]
    card_row = Table([cards], colWidths=[40 * mm] * 4)
    card_row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    story.append(card_row)
    story.append(Spacer(1, 3 * mm))

    cards2 = [
        _kpi_card("Collection Efficiency", f"{collection_efficiency:.1f}%" if collection_efficiency is not None else "—", "Collected ÷ Adsorbed", "#3DB3B3", styles),
        _kpi_card("Liquefaction Efficiency", f"{liquefaction_efficiency:.1f}%" if liquefaction_efficiency is not None else "—", "Liquefied ÷ Collected", "#0EA5E9", styles),
        _kpi_card("Cycles This Week", f"{int(row['total_cycles'] or 0)}", f"1n3: {s1n3['cycles']} · 2n4: {s2n4['cycles']}", BRAND_TEAL, styles),
        _kpi_card("Energy Intensity", f"{row['energy_intensity_kwh_per_tonne'] / 1000:.1f} MWh/t" if row["energy_intensity_kwh_per_tonne"] else "—", "Process energy per tonne captured", "#94A3B8", styles),
    ]
    card_row2 = Table([cards2], colWidths=[40 * mm] * 4)
    card_row2.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    story.append(card_row2)
    story.append(Spacer(1, 7 * mm))

    # --- Narrative ---
    story.append(Paragraph("What's Driving This Week's Result", styles["h2"]))
    story.append(Paragraph(_build_narrative(row, df), styles["body"]))
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
