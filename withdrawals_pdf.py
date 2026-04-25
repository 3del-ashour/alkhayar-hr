"""
withdrawals_pdf.py — PDF report for personal withdrawals (السحوبات الشخصية)
Matches the visual style of payslip_pdf.py (same fonts, colors, logo).
"""

from pathlib import Path
from datetime import datetime
from io import BytesIO

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.colors import HexColor
from reportlab.platypus import Image as RLImage

BASE_DIR   = Path(__file__).parent
LOGO_PATH  = BASE_DIR / "assets" / "sa_logo.png"

NAVY  = HexColor("#1B2A47")
BLUE  = HexColor("#2E4A7A")
RED   = HexColor("#c0392b")
LIGHT = HexColor("#f8fafc")
WHITE = colors.white
GREY  = HexColor("#8a97a8")

FONT_REGULAR = "HYSMyeongJo-Medium"
FONT_BOLD    = "HYSMyeongJo-Medium"
_FONTS_READY = False

_ARABIC_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
     "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def _register_fonts():
    global FONT_REGULAR, FONT_BOLD, _FONTS_READY
    if _FONTS_READY:
        return
    for reg, bold in _ARABIC_FONT_CANDIDATES:
        if Path(reg).exists():
            try:
                pdfmetrics.registerFont(TTFont("AR", reg))
                pdfmetrics.registerFont(TTFont("AR-Bold",
                    bold if Path(bold).exists() else reg))
                FONT_REGULAR = "AR"
                FONT_BOLD    = "AR-Bold"
                _FONTS_READY = True
                return
            except Exception:
                continue
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
        _FONTS_READY = True
    except Exception:
        pass


def _ar(text) -> str:
    raw = str(text) if text is not None else ""
    if not raw:
        return raw
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(raw))
    except ImportError:
        return raw


def _para(text, style) -> Paragraph:
    return Paragraph(_ar(str(text)), style)


def generate_withdrawals_pdf(
    records: list,
    title_ar: str = "تقرير السحوبات الشخصية",
    period_label: str = "",
    logged_by: str = "",
) -> bytes:
    """
    Generate a PDF report for personal withdrawals.

    Args:
        records: list of dicts with keys: w_date, partner_name, amount, description, logged_by
        title_ar: report title in Arabic
        period_label: e.g. "أبريل 2026" or "2026"
        logged_by: username who generated the report

    Returns:
        PDF bytes
    """
    _register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=1.8*cm, leftMargin=1.8*cm,
        topMargin=1.5*cm,   bottomMargin=1.5*cm,
    )

    # ── Styles ──────────────────────────────────────────────────
    S_title   = ParagraphStyle("title",   fontName=FONT_BOLD,    fontSize=16, textColor=WHITE,  alignment=1, spaceAfter=2)
    S_sub     = ParagraphStyle("sub",     fontName=FONT_REGULAR, fontSize=10, textColor=WHITE,  alignment=1)
    S_hdr     = ParagraphStyle("hdr",     fontName=FONT_BOLD,    fontSize=10, textColor=NAVY,   alignment=1)
    S_cell    = ParagraphStyle("cell",    fontName=FONT_REGULAR, fontSize=9,  textColor=colors.black, alignment=1)
    S_total   = ParagraphStyle("total",   fontName=FONT_BOLD,    fontSize=10, textColor=RED,    alignment=1)
    S_caption = ParagraphStyle("caption", fontName=FONT_REGULAR, fontSize=8,  textColor=GREY,   alignment=1)
    S_label   = ParagraphStyle("label",   fontName=FONT_BOLD,    fontSize=9,  textColor=NAVY,   alignment=1)
    S_value   = ParagraphStyle("value",   fontName=FONT_REGULAR, fontSize=9,  textColor=colors.black, alignment=1)

    story = []
    page_w = A4[0] - 3.6*cm  # usable width

    # ── Header banner ────────────────────────────────────────────
    logo_cell = ""
    if LOGO_PATH.exists():
        try:
            logo_cell = RLImage(str(LOGO_PATH), width=40, height=28)
        except Exception:
            logo_cell = _para("SA", S_sub)
    else:
        logo_cell = _para("SA", S_sub)

    hdr_table = Table(
        [[logo_cell,
          [_para("شركة الخيار للسيارات وقطع غيارها", S_title),
           _para(title_ar, S_sub)],
          _para(period_label, S_sub)]],
        colWidths=[2*cm, page_w - 4*cm, 2*cm],
    )
    hdr_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), NAVY),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING",  (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0),(-1,-1), 10),
        ("LEFTPADDING", (0,0), (-1,-1), 8),
        ("RIGHTPADDING",(0,0), (-1,-1), 8),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(hdr_table)
    story.append(Spacer(1, 0.4*cm))

    # ── Summary row ──────────────────────────────────────────────
    total_amount = sum(r.get("amount", 0) or 0 for r in records)
    partners_set = sorted(set(r.get("partner_name","") for r in records))

    sum_data = [
        [_para("إجمالي السحوبات", S_label), _para(f"{total_amount:,.0f} د.ل", S_total)],
        [_para("عدد العمليات",    S_label), _para(str(len(records)), S_value)],
        [_para("الأشخاص",        S_label), _para(" | ".join(partners_set), S_value)],
        [_para("تاريخ الطباعة",  S_label), _para(datetime.now().strftime("%Y-%m-%d %H:%M"), S_value)],
    ]
    sum_table = Table(sum_data, colWidths=[page_w*0.35, page_w*0.65])
    sum_table.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), LIGHT),
        ("GRID",         (0,0), (-1,-1), 0.5, HexColor("#d0d8e4")),
        ("TOPPADDING",   (0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 6),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LIGHT]),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 0.4*cm))

    # ── Main data table ──────────────────────────────────────────
    col_headers = [
        _para("التاريخ",       S_hdr),
        _para("الشخص",        S_hdr),
        _para("المبلغ (د.ل)", S_hdr),
        _para("الوصف",        S_hdr),
        _para("سُجِّل بواسطة", S_hdr),
    ]
    col_widths = [page_w*0.14, page_w*0.18, page_w*0.16, page_w*0.32, page_w*0.20]

    data_rows = [col_headers]
    for r in records:
        data_rows.append([
            _para(r.get("w_date",""),          S_cell),
            _para(r.get("partner_name",""),    S_cell),
            _para(f"{r.get('amount',0):,.0f}", S_cell),
            _para(r.get("description","") or "—", S_cell),
            _para(r.get("logged_by","") or "—",   S_cell),
        ])

    # Totals row
    data_rows.append([
        _para("الإجمالي", S_hdr),
        _para("",         S_cell),
        _para(f"{total_amount:,.0f}", ParagraphStyle("tot2", fontName=FONT_BOLD, fontSize=10, textColor=RED, alignment=1)),
        _para("", S_cell),
        _para("", S_cell),
    ])

    data_table = Table(data_rows, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",   (0,0),  (-1,0),  NAVY),
        ("TEXTCOLOR",    (0,0),  (-1,0),  WHITE),
        ("BACKGROUND",   (0,-1), (-1,-1), LIGHT),
        ("GRID",         (0,0),  (-1,-1), 0.4, HexColor("#d0d8e4")),
        ("VALIGN",       (0,0),  (-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),  (-1,-1), 6),
        ("BOTTOMPADDING",(0,0),  (-1,-1), 6),
        ("LEFTPADDING",  (0,0),  (-1,-1), 6),
        ("RIGHTPADDING", (0,0),  (-1,-1), 6),
        ("FONTNAME",     (0,-1), (-1,-1), FONT_BOLD),
    ]
    # Alternate row shading
    for i in range(1, len(data_rows)-1):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0,i), (-1,i), LIGHT))
    data_table.setStyle(TableStyle(style_cmds))

    story.append(data_table)
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Spacer(1, 0.2*cm))
    story.append(_para(
        f"تم إنشاء هذا التقرير بواسطة: {logged_by} | {datetime.now().strftime('%Y-%m-%d %H:%M')} | شركة الخيار — نظام الموارد البشرية v4",
        S_caption
    ))

    doc.build(story)
    return buf.getvalue()
