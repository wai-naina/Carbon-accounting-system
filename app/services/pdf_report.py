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
from app.components.charts import cn_emissions_breakdown_pie, waterfall_chart
from app.services.report_data import (
    BASIS_LABEL,
    WeekReportContext,
    boundaries_note,
    boundary_note,
    build_narrative,
    build_week_report_context,
    pct,
    recent_weeks_trend_chart,
    report_generated_at,
    single_week_subsystem_chart,
)

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
            # Was installed via packages.txt's `fonts-liberation` on the hosted
            # deployment (Streamlit Cloud's base image has no fonts of its own
            # beyond the bare minimum). That file is currently parked as
            # packages.txt.disabled — see README — so this path is absent on
            # cloud for now, which is harmless while the PDF path is disabled
            # there too. Still checked first on Linux: restoring packages.txt
            # brings it back, and it's guaranteed present then, unlike DejaVu.
            "PDFReportSans",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        ),
        (
            # Was installed via packages.txt's `fonts-dejavu-core` as a second
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

    kaleido is imported here rather than at module scope so that importing this
    module — which the reports page does unconditionally, to decide whether to
    offer a PDF at all — cannot fail on a host where kaleido isn't installed.
    The page needs to render its fallback there, not raise on import.
    """
    global _chrome_ready
    if _chrome_ready:
        return
    import kaleido

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


# Card geometry. The outer row table pads each cell by CARD_GUTTER on both
# sides, so a card's own width is its column minus that — previously the inner
# width was hardcoded to 38mm no matter how wide the column was, which left the
# 80mm working-capacity and steam cards filling less than half their column and
# forced values like "85.67 mol/m³" to wrap inside a box with room to spare.
CARD_GUTTER = 3
# Four cards across the 180mm text block, and the wide two-up variant used by
# the working-capacity and steam sections. A two-card row of CARD_COL_W keeps
# the narrow width and is left-aligned, so it shares a left edge and a card
# width with the four-card rows above it.
CARD_COL_W = 44 * mm
WIDE_CARD_COL_W = 88 * mm
CARD_PAD_X = 8
CARD_PAD_TOP = 8
CARD_PAD_Y = 2
CARD_PAD_BOTTOM = 1


def _kpi_card_row(
    specs: list[tuple[str, str, str, str]],
    styles: dict,
    col_width: float,
    h_align: str = "CENTER",
) -> Table:
    """One row of KPI cards, all the same height, with their labels, values and
    subtitles on shared baselines.

    Each card used to size its own three rows independently against its own
    content. A label that wrapped where its neighbours' did not — "LIQUEFACTION
    EFFICIENCY" is the one that does — pushed that card's value a line lower
    than every other value in the row, and a subtitle that wrapped made that one
    card taller than the rest. The row came out visibly ragged, and which card
    was the odd one out changed with the week's numbers.

    Heights are measured across every card in the row and applied uniformly, so
    wrapping grows the whole row instead of breaking the alignment inside it.
    `specs` is a list of (label, value, sub, accent_hex).
    """
    inner_w = col_width - 2 * CARD_GUTTER
    text_w = inner_w - 2 * CARD_PAD_X

    lines = [
        (
            Paragraph(label.upper(), styles["card_label"]),
            Paragraph(value, styles["card_value"]),
            Paragraph(sub or "", styles["card_sub"]),
        )
        for label, value, sub, _ in specs
    ]
    # Tallest label, tallest value and tallest subtitle anywhere in this row.
    # Measured rather than assumed, so a value that legitimately needs two lines
    # gets them instead of being clipped.
    natural = [max(card[i].wrap(text_w, 0)[1] for card in lines) for i in range(3)]
    row_heights = [
        natural[0] + CARD_PAD_TOP + CARD_PAD_BOTTOM,
        natural[1] + CARD_PAD_Y + CARD_PAD_BOTTOM,
        natural[2] + CARD_PAD_Y + CARD_PAD_BOTTOM,
    ]

    cards = []
    for (_, _, _, accent_hex), card in zip(specs, lines):
        inner = Table(
            [[card[0]], [card[1]], [card[2]]],
            colWidths=[inner_w],
            rowHeights=row_heights,
        )
        inner.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), CARD_PAD_Y),
            ("BOTTOMPADDING", (0, 0), (-1, -1), CARD_PAD_BOTTOM),
            ("LEFTPADDING", (0, 0), (-1, -1), CARD_PAD_X),
            ("RIGHTPADDING", (0, 0), (-1, -1), CARD_PAD_X),
            ("LINEABOVE", (0, 0), (-1, 0), 2.5, colors.HexColor(accent_hex)),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F9F8")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(LINE)),
            ("TOPPADDING", (0, 0), (-1, 0), CARD_PAD_TOP),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        cards.append(inner)

    row = Table([cards], colWidths=[col_width] * len(cards), hAlign=h_align)
    row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), CARD_GUTTER),
        ("RIGHTPADDING", (0, 0), (-1, -1), CARD_GUTTER),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return row


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
        f"Page {doc.page} · Generated {report_generated_at()}",
    )
    canvas_obj.restoreState()


def generate_weekly_pdf_report(
    session,
    week_start: datetime,
    series_filter: Optional[str] = None,
    context: Optional[WeekReportContext] = None,
) -> bytes:
    """Build the Carbon Nest weekly PDF report for the week starting at `week_start`.

    Returns raw PDF bytes, ready for st.download_button. Pass `context` to reuse
    an already-built WeekReportContext (the HTML fallback path builds one too);
    omit it and this resolves its own.
    """
    ctx = context or build_week_report_context(session, week_start, series_filter)
    df, row = ctx.df, ctx.row
    wc = ctx.working_capacity
    grid_ef = ctx.grid_ef
    s1n3, s2n4 = ctx.series_1n3, ctx.series_2n4

    styles = _styles()
    week_label = ctx.week_label

    gross_captured = ctx.gross_captured
    total_emissions = ctx.total_emissions
    net_removal = ctx.net_removal
    removal_efficiency = ctx.removal_efficiency
    eff_str = f"{removal_efficiency:+.1f}%" if removal_efficiency is not None else "—"
    eff_color = RED if (removal_efficiency or 0) <= 0 else GREEN

    story = []

    # --- Hero ---
    story.append(Paragraph("CAPTURE &amp; REMOVAL EFFICIENCY", styles["eyebrow"]))
    story.append(Paragraph(
        f'<font color="{eff_color}">{eff_str}</font>', styles["hero"],
    ))
    story.append(Paragraph(
        f"{gross_captured:,.1f} kg captured − {total_emissions:,.1f} kg emitted = "
        f"{net_removal:+,.1f} kg net removal → {eff_str} of what was captured.",
        styles["sub"],
    ))
    if ctx.headline_note:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"<b>Reported on the capture boundary.</b> {ctx.headline_note}",
            styles["sub"],
        ))
    story.append(Spacer(1, 8 * mm))

    # --- KPI card row ---
    card_row = _kpi_card_row([
        ("Gross Captured", f"{gross_captured:,.1f} kg", boundary_note(row, ctx.headline_basis), "#0EA5E9"),
        ("Operational Emissions", f"{ctx.headline_operational:,.1f} kg", f"Grid EF: {grid_ef:.4f} kg/kWh", "#F59E0B"),
        ("Embodied Emissions", f"{ctx.headline_embodied:,.1f} kg", "Output-based, v0.6 LCA", "#A855F7"),
        ("Net Removal", f"{net_removal:+,.1f} kg", "Captured minus total emissions", GREEN if net_removal > 0 else RED),
    ], styles, CARD_COL_W)
    story.append(card_row)
    story.append(Spacer(1, 3 * mm))

    # The chain in order, left to right, so the reader walks adsorbed → desorbed
    # → bagged → liquefied and lands on the overall figure last.
    card_row2 = _kpi_card_row([
        ("Desorption Efficiency", pct(ctx.desorption_efficiency), "Desorbed ÷ Adsorbed", "#A855F7"),
        ("Collection Efficiency", pct(ctx.collection_efficiency), "Collected ÷ Desorbed", "#3DB3B3"),
        ("Liquefaction Efficiency", pct(ctx.liquefaction_efficiency), "Liquefied ÷ Collected", "#0EA5E9"),
        ("Capture Efficiency", pct(ctx.capture_efficiency), "Liquefied ÷ Adsorbed · overall", BRAND_TEAL),
    ], styles, CARD_COL_W)
    story.append(card_row2)
    story.append(Spacer(1, 3 * mm))

    # Intensity comes off the resolved headline, not the row: on a week the
    # headline fell back to the capture boundary, the row still holds the
    # liquefied basis and this card printed an em dash beside a boundary table
    # reporting 41.7 MWh/t for the same week.
    intensity = ctx.headline_energy_intensity
    # Left-aligned: a two-card row keeps the column width of the four-card rows
    # above it, so all three rows share one left edge and one card width rather
    # than stretching these two across the full page.
    card_row3 = _kpi_card_row([
        ("Cycles This Week", f"{int(row['total_cycles'] or 0)}", f"1n3: {s1n3['cycles']} · 2n4: {s2n4['cycles']}", BRAND_TEAL),
        (
            "Energy Intensity",
            f"{intensity / 1000:.1f} MWh/t" if intensity is not None else "—",
            f"Metered energy per tonne · {BASIS_LABEL[ctx.headline_basis]}", "#94A3B8",
        ),
    ], styles, CARD_COL_W, h_align="LEFT")
    story.append(card_row3)
    story.append(Spacer(1, 5 * mm))

    boundaries = _boundaries_table(row, styles)
    if boundaries is not None:
        story.append(Paragraph("Removal Efficiency — With and Without Liquefaction", styles["h2"]))
        story.append(boundaries)
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(boundaries_note(row), styles["sub"]))
        story.append(Spacer(1, 6 * mm))
    else:
        story.append(Spacer(1, 2 * mm))

    # --- Narrative ---
    story.append(Paragraph("What's Driving This Week's Result", styles["h2"]))
    story.append(Paragraph(build_narrative(row, ctx.headline_dict()), styles["body"]))
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
    wc_specs = []
    for g in ("A", "B"):
        gr = wc["groups"][g]
        cap = gr["avg_working_capacity_mol_per_m3"]
        value_str = f"{cap:.2f} mol/m³" if cap is not None else "—"
        sub = f"{gr['n_cycles_used']} of {gr['n_cycles_in_window']} cycles used"
        wc_specs.append((gr["label"], value_str, sub, "#3DB3B3" if g == "A" else "#A855F7"))
    wc_block.append(_kpi_card_row(wc_specs, styles, WIDE_CARD_COL_W))
    anomaly_cycles = ctx.anomaly_cycles
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
        steam_intensity = ctx.headline_steam_intensity
        steam_block = [
            Paragraph("Desorption Steam", styles["h2"]),
            Paragraph(
                "Steam is what releases the captured CO&#8322; from the sorbent bed during the "
                "desorption half-cycle — the main driver of Boiler A/B energy below. Intensity "
                "uses the same per-tonne-captured denominator as Energy Intensity.",
                styles["chart_caption"],
            ),
        ]
        steam_row = _kpi_card_row([
            (
                "Steam Used", f"{steam_kg:,.0f} kg",
                f"1n3: {s1n3['steam_kg']:,.0f} kg · 2n4: {s2n4['steam_kg']:,.0f} kg",
                "#0EA5E9",
            ),
            (
                "Steam Intensity",
                f"{steam_intensity:,.0f} kg/t" if steam_intensity is not None else "—",
                f"kg steam per tonne · {BASIS_LABEL[ctx.headline_basis]}", "#F59E0B",
            ),
        ], styles, WIDE_CARD_COL_W)
        steam_block.append(steam_row)
        story.append(KeepTogether(steam_block))
        story.append(Spacer(1, 6 * mm))

    # --- Carbon balance waterfall ---
    # Each heading is kept together with its own first chart/paragraph (KeepTogether)
    # so a page break can never strand a heading alone at the bottom of a page with
    # its content pushed to the next one.
    balance_block = [Paragraph("Carbon Balance", styles["h2"])]
    wf = waterfall_chart(gross_captured, ctx.headline_operational, ctx.headline_embodied)
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
    subsystem_fig = single_week_subsystem_chart(row)
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

    pie = cn_emissions_breakdown_pie(row, ctx.headline_dict(), ctx.grid_ef)
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
    trend_fig = recent_weeks_trend_chart(df, row["start_date"])
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
