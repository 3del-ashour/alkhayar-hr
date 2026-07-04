"""
payslip_pdf.py — Production-Grade Arabic Payslip Generator
شركة الخيار لسيارات وقطع غيارها — v5.0 Enterprise

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Architecture (4-layer separation):

  LAYER 1 — Font & Arabic Support
             Font registration, arabic_reshaper + bidi shaping
             Cross-platform font discovery

  LAYER 2 — Brand Colors & Style Engine
             All colors and ParagraphStyles in one place
             Zero style definitions scattered across builders

  LAYER 3 — Layout Builders (Flowable factories)
             build_header()          → company header + doc title
             build_employee_section()→ employee info grid
             build_salary_table()    → earnings / deductions table
             build_net_banner()      → highlighted net salary
             build_signatures()      → signature lines + stamp
             build_footer()          → legal notice + timestamp

  LAYER 4 — Public API
             generate_payslip_pdf()           → single employee payslip
             generate_branch_payroll_summary() → branch roll-up PDF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Usage:
    from payslip_pdf import generate_payslip_pdf
    path = generate_payslip_pdf(payslip_data, serial_number=1)

Data contract (employee_data keys):
    Mandatory:  year, month, base_salary, net_pay / net_salary
    Employee:   full_name / employee_name, employee_number,
                branch_name / branch_id, dept_name, job_title
    Earnings:   gross / gross_salary, allowances_sum / total_allowances,
                bonus, line_items (list of {type, desc, amount})
    Deductions: total_deductions, absence_deduction, advance_deduction,
                absent_days, daily_rate, working_days
    Optional:   payslip_number (auto-generated if absent)
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Standard library
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from pathlib  import Path
from datetime import date, datetime

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ReportLab — Platypus (layout engine)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Table,
    TableStyle,
    Spacer,
    HRFlowable,
    KeepTogether,
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles   import ParagraphStyle
from reportlab.lib.enums    import TA_RIGHT, TA_CENTER, TA_LEFT
from reportlab.lib.colors   import HexColor, white
from reportlab.lib.units    import mm
from reportlab.pdfbase      import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts  import TTFont


# ══════════════════════════════════════════════════════════════════════
# LAYER 1 — FONT REGISTRATION & ARABIC TEXT SUPPORT
# ══════════════════════════════════════════════════════════════════════

# Font name constants — set by _register_fonts() at first call
FONT_REGULAR: str = 'HYSMyeongJo-Medium'   # default CID fallback
FONT_BOLD:    str = 'HYSMyeongJo-Medium'   # same (CID fonts have no bold variant)
_FONTS_READY: bool = False

# Candidate paths for a system Arabic TTFont (checked in order)
_ARABIC_FONT_CANDIDATES = [
    # macOS
    ('/System/Library/Fonts/Supplemental/Arial.ttf',
     '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
    ('/Library/Fonts/Arial.ttf',
     '/Library/Fonts/Arial Bold.ttf'),
    # Windows
    ('C:/Windows/Fonts/arial.ttf',
     'C:/Windows/Fonts/arialbd.ttf'),
    # Linux (common distributions)
    ('/usr/share/fonts/truetype/msttcorefonts/Arial.ttf',
     '/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf'),
    ('/usr/share/fonts/truetype/freefont/FreeSans.ttf',
     '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf'),
    ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
     '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
]


def _register_fonts() -> None:
    """
    Register the best available Arabic-capable font.

    Priority:
      1. First system TTFont found in _ARABIC_FONT_CANDIDATES
         (proper Arabic glyph coverage + bold variant)
      2. UnicodeCIDFont('HYSMyeongJo-Medium') as fallback
         (as specified; requires arabic_reshaper for proper shaping)
    """
    global FONT_REGULAR, FONT_BOLD, _FONTS_READY
    if _FONTS_READY:
        return

    # ── Attempt 1: system TTFont with Arabic coverage ──
    for reg_path, bold_path in _ARABIC_FONT_CANDIDATES:
        if Path(reg_path).exists():
            try:
                pdfmetrics.registerFont(TTFont('AR',     reg_path))
                pdfmetrics.registerFont(TTFont('AR-Bold',
                    bold_path if Path(bold_path).exists() else reg_path))
                FONT_REGULAR = 'AR'
                FONT_BOLD    = 'AR-Bold'
                _FONTS_READY = True
                return
            except Exception:
                continue

    # ── Attempt 2: Unicode CID font (fallback) ──────────
    try:
        pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
        FONT_REGULAR = 'HYSMyeongJo-Medium'
        FONT_BOLD    = 'HYSMyeongJo-Medium'
        _FONTS_READY = True
    except Exception as exc:
        raise RuntimeError(
            f'payslip_pdf: No usable font found for PDF generation.\n'
            f'Install an Arabic font or run: pip install reportlab\n'
            f'Detail: {exc}'
        )


def _shape(text) -> str:
    """
    Reshape Arabic text for correct PDF rendering.

    Steps:
      1. arabic_reshaper — connects Arabic letters correctly
         (isolated ب → initial ﺑ / medial ﺒ / final ﺐ forms)
      2. python-bidi — reverses to visual RTL display order

    Falls back to raw string if libraries unavailable.
    This function is the ONLY place text is prepared for rendering.
    """
    raw = str(text) if text is not None else ''
    if not raw:
        return raw
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(raw))
    except ImportError:
        return raw   # graceful degradation — text visible but not shaped


# Alias: short name used throughout all builders
ar = _shape


# ══════════════════════════════════════════════════════════════════════
# LAYER 2 — BRAND COLORS & STYLE ENGINE
# ══════════════════════════════════════════════════════════════════════

# ── Company Brand Palette ─────────────────────────────────────────────
NAVY        = HexColor('#1B2A47')
NAVY_MID    = HexColor('#243560')
NAVY_DARK   = HexColor('#0F1A2E')
GOLD        = HexColor('#C49A2A')
GOLD_LIGHT  = HexColor('#F5E6C0')
GREEN       = HexColor('#27AE60')
GREEN_LIGHT = HexColor('#E8F8F0')
RED         = HexColor('#C0392B')
RED_LIGHT   = HexColor('#FDECEA')
GRAY_LIGHT  = HexColor('#F5F6F8')
GRAY_BORDER = HexColor('#D0D8E4')
GRAY_MID    = HexColor('#8A97A8')
WHITE       = white


class StyleEngine:
    """
    Central repository for all ParagraphStyles.

    Rules:
      • Every style is defined here — zero inline ParagraphStyle() calls in builders
      • Styles are lazily created and cached on first access
      • Font is injected at construction — no hardcoded font names inside styles
    """

    def __init__(self, font_regular: str, font_bold: str):
        self._fr = font_regular
        self._fb = font_bold
        self._cache: dict = {}

    def _s(self, name: str, font=None, size=10, color=None,
           align=TA_RIGHT, leading=None, space_before=0, space_after=0,
           **kw) -> ParagraphStyle:
        if name not in self._cache:
            self._cache[name] = ParagraphStyle(
                name,
                fontName    = font or self._fr,
                fontSize    = size,
                textColor   = color or NAVY,
                alignment   = align,
                leading     = leading or round(size * 1.35),
                spaceBefore = space_before,
                spaceAfter  = space_after,
                **kw,
            )
        return self._cache[name]

    # ── Header Styles ─────────────────────────────────────────────────
    @property
    def company_name(self):
        return self._s('co_name', font=self._fb, size=19, color=WHITE, align=TA_CENTER)

    @property
    def company_tagline(self):
        return self._s('co_tag', size=10, color=GOLD, align=TA_CENTER)

    @property
    def company_info(self):
        return self._s('co_info', size=8, color=GRAY_MID, align=TA_CENTER)

    @property
    def doc_title(self):
        return self._s('doc_title', font=self._fb, size=14, color=WHITE, align=TA_CENTER)

    @property
    def doc_meta_left(self):
        return self._s('doc_meta_l', size=8, color=WHITE, align=TA_LEFT)

    @property
    def doc_meta_right(self):
        return self._s('doc_meta_r', size=8, color=WHITE, align=TA_RIGHT)

    # ── Employee Info Styles ──────────────────────────────────────────
    @property
    def field_label(self):
        return self._s('fld_lbl', size=7, color=GRAY_MID, align=TA_RIGHT)

    @property
    def field_value(self):
        return self._s('fld_val', font=self._fb, size=9, color=NAVY, align=TA_RIGHT)

    # ── Salary Table Styles ───────────────────────────────────────────
    @property
    def section_hdr(self):
        return self._s('sec_hdr', font=self._fb, size=10, color=WHITE, align=TA_RIGHT)

    @property
    def row_label(self):
        return self._s('row_lbl', size=9, color=NAVY, align=TA_RIGHT)

    @property
    def row_label_bold(self):
        return self._s('row_lbl_b', font=self._fb, size=9, color=NAVY, align=TA_RIGHT)

    @property
    def row_amount(self):
        return self._s('row_amt', size=9, color=NAVY, align=TA_RIGHT)

    @property
    def row_amount_green(self):
        return self._s('row_amt_g', font=self._fb, size=10, color=GREEN, align=TA_RIGHT)

    @property
    def row_amount_red(self):
        return self._s('row_amt_r', font=self._fb, size=10, color=RED, align=TA_RIGHT)

    @property
    def row_label_green(self):
        return self._s('row_lbl_g', font=self._fb, size=10, color=GREEN, align=TA_RIGHT)

    @property
    def row_label_red(self):
        return self._s('row_lbl_r', font=self._fb, size=10, color=RED, align=TA_RIGHT)

    @property
    def no_items(self):
        return self._s('no_items', size=8, color=GRAY_MID, align=TA_CENTER)

    # ── Net Salary Banner Styles ──────────────────────────────────────
    @property
    def net_label(self):
        return self._s('net_lbl', font=self._fb, size=12, color=GOLD, align=TA_CENTER)

    @property
    def net_amount(self):
        return self._s('net_amt', font=self._fb, size=26, color=WHITE, align=TA_CENTER)

    @property
    def net_currency(self):
        return self._s('net_cur', size=10, color=GOLD, align=TA_CENTER)

    @property
    def net_attendance(self):
        return self._s('net_att', size=8, color=GRAY_MID, align=TA_CENTER)

    # ── Signature & Footer Styles ─────────────────────────────────────
    @property
    def sig_title(self):
        return self._s('sig_ttl', font=self._fb, size=8, color=NAVY, align=TA_CENTER)

    @property
    def sig_blank(self):
        return self._s('sig_blk', size=8, color=GRAY_MID, align=TA_CENTER)

    @property
    def footer_main(self):
        return self._s('ftr_main', size=7, color=GRAY_MID, align=TA_CENTER)

    @property
    def footer_sub(self):
        return self._s('ftr_sub', size=7, color=HexColor('#4A6080'), align=TA_CENTER)

    # ── Branch Summary Styles ─────────────────────────────────────────
    @property
    def summary_hdr(self):
        return self._s('sum_hdr', font=self._fb, size=9, color=WHITE, align=TA_RIGHT)

    @property
    def summary_cell(self):
        return self._s('sum_cell', size=8, color=NAVY, align=TA_RIGHT)

    @property
    def summary_total(self):
        return self._s('sum_tot', font=self._fb, size=9, color=GOLD, align=TA_RIGHT)


# ══════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════

MONTH_AR = {
    1: 'يناير',   2: 'فبراير',  3: 'مارس',    4: 'أبريل',
    5: 'مايو',    6: 'يونيو',   7: 'يوليو',   8: 'أغسطس',
    9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر',
}

BASE_DIR  = Path(__file__).parent
LOGO_PATH = BASE_DIR / 'assets' / 'sa_logo.png'

PAGE_W, PAGE_H = A4
MARGIN    = 16 * mm          # left & right margin
CONTENT_W = PAGE_W - 2 * MARGIN   # usable table width


# ══════════════════════════════════════════════════════════════════════
# LAYER 3 — LAYOUT BUILDERS
# Each builder is a pure function: (style, data) → list[Flowable]
# ══════════════════════════════════════════════════════════════════════

def _col(*fractions) -> list:
    """Convert fraction tuple to absolute column widths."""
    return [CONTENT_W * f for f in fractions]


def _para(text, style) -> Paragraph:
    """Shape Arabic text and wrap in a Paragraph."""
    return Paragraph(ar(text), style)


# ── Builder 1: Document Header ────────────────────────────────────────

def _build_header(S: StyleEngine, ps_num: str, year: int, month: int) -> list:
    """
    Produces:
      [Company name block — navy background, gold bottom stripe]
      [Document title bar — darker navy, with payslip# / title / month]
    """

    # ── Company identity block ─────────────────────────────
    logo_cell = ''
    if LOGO_PATH.exists():
        try:
            from reportlab.platypus import Image as RLImage
            logo_cell = RLImage(str(LOGO_PATH), width=40, height=28)
        except Exception:
            pass

    company_table = Table(
        [
            [logo_cell,
             Table(
                 [
                     [_para('شركة الخيار',                               S.company_name)],
                     [_para('لسيارات وقطع غيارها  —  طرابلس، ليبيا',   S.company_tagline)],
                     [_para('سجل تجاري: 60378  |  +218-91-2109096  |  عين زارة، منطقة السبعة', S.company_info)],
                 ],
                 colWidths=[CONTENT_W - 52],
             )],
        ],
        colWidths=[52, CONTENT_W - 52],
    )
    company_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1),  8),
        ('RIGHTPADDING',  (0, 0), (-1, -1),  8),
        ('LINEBELOW',     (0, -1), (-1, -1), 3, GOLD),   # gold stripe
    ]))

    # ── Document title bar ─────────────────────────────────
    title_bar = Table(
        [[
            _para(f'رقم الكشف: {ps_num}',         S.doc_meta_left),
            _para('إذن صرف راتب',                  S.doc_title),
            _para(f'{MONTH_AR[month]}  {year}',    S.doc_meta_right),
        ]],
        colWidths=_col(0.30, 0.40, 0.30),
    )
    title_bar.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY_MID),
        ('TOPPADDING',    (0, 0), (-1, -1),  8),
        ('BOTTOMPADDING', (0, 0), (-1, -1),  8),
        ('LEFTPADDING',   (0, 0), (-1, -1),  8),
        ('RIGHTPADDING',  (0, 0), (-1, -1),  8),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN',         (0, 0), (0, 0),  'LEFT'),
        ('ALIGN',         (1, 0), (1, 0),  'CENTER'),
        ('ALIGN',         (2, 0), (2, 0),  'RIGHT'),
    ]))

    return [company_table, Spacer(1, 2 * mm), title_bar, Spacer(1, 3 * mm)]


# ── Builder 2: Employee Information Section ───────────────────────────

def _build_employee_section(S: StyleEngine, data: dict) -> list:
    """
    Two-row grid with 3 cells each:
      Row 1: [تاريخ الإصدار] [الرقم الوظيفي] [اسم الموظف]
      Row 2: [القسم]         [الفرع]          [المنصب]
    """

    def field(label: str, value) -> Table:
        """A labeled field cell: small grey label above bold value."""
        return Table(
            [
                [_para(label,         S.field_label)],
                [_para(str(value or '—'), S.field_value)],
            ],
            colWidths=[CONTENT_W / 3 - 4],
        )

    name   = data.get('full_name',    data.get('employee_name',  '—'))
    emp_no = data.get('employee_number', '—')
    branch = data.get('branch_name',  data.get('branch_id',      '—'))
    dept   = data.get('dept_name',    '—')
    title  = data.get('job_title',    '—')
    issued = date.today().strftime('%d / %m / %Y')

    grid = Table(
        [
            # Row 1
            [field('تاريخ الإصدار',   issued),
             field('الرقم الوظيفي',   emp_no),
             field('اسم الموظف',      name)],
            # Row 2
            [field('القسم',            dept),
             field('الفرع',            branch),
             field('المنصب الوظيفي',   title)],
        ],
        colWidths=_col(0.333, 0.333, 0.334),
    )
    grid.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GRAY_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 0.5, GRAY_BORDER),
        ('LINEBELOW',     (0, 0), (-1,  0), 0.5, GRAY_BORDER),
        ('LINEBEFORE',    (1, 0), (1,  -1), 0.5, GRAY_BORDER),
        ('TOPPADDING',    (0, 0), (-1, -1),  6),
        ('BOTTOMPADDING', (0, 0), (-1, -1),  6),
        ('LEFTPADDING',   (0, 0), (-1, -1),  8),
        ('RIGHTPADDING',  (0, 0), (-1, -1),  8),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
    ]))

    return [grid, Spacer(1, 4 * mm)]


# ── Builder 3: Salary Breakdown Table ────────────────────────────────

def _build_salary_table(S: StyleEngine, data: dict) -> list:
    """
    Full earnings & deductions table.

    Visual RTL layout — columns in data array:
      col 0 (left  side) = القيمة / Amount
      col 1 (right side) = البند  / Description

    Column widths: [35% amount | 65% description]
    """

    CW = _col(0.35, 0.65)   # [amount col, label col]

    # ── Cell helper factories ──────────────────────────
    def amt(value, style) -> Paragraph:
        return _para(f'{value:,.2f}  د.ل', style)

    def lbl(text, style) -> Paragraph:
        return _para(text, style)

    def section_hdr(title_ar: str, subtitle_en: str) -> list:
        """Full-width navy section header row."""
        combined = f'{title_ar}   |   {subtitle_en}'
        return [[_para(combined, S.section_hdr), '']]

    # ── Row accumulator ────────────────────────────────
    rows: list  = []
    rstyles: list = []    # per-row TableStyle commands
    ri: int = 0           # current row index

    def add_hdr(title_ar, subtitle_en):
        nonlocal ri
        rows.append([_para(f'{title_ar}   |   {subtitle_en}', S.section_hdr), ''])
        rstyles.extend([
            ('BACKGROUND',    (0, ri), (-1, ri), NAVY),
            ('SPAN',          (0, ri), (-1, ri)),
            ('TOPPADDING',    (0, ri), (-1, ri), 8),
            ('BOTTOMPADDING', (0, ri), (-1, ri), 8),
        ])
        ri += 1

    def add_row(amount, label_text, label_sty, amount_sty, bg):
        nonlocal ri
        rows.append([amt(amount, amount_sty), lbl(label_text, label_sty)])
        rstyles.extend([
            ('BACKGROUND',    (0, ri), (-1, ri), bg),
            ('TOPPADDING',    (0, ri), (-1, ri), 6),
            ('BOTTOMPADDING', (0, ri), (-1, ri), 6),
        ])
        ri += 1

    def add_subtotal(amount, label_text, bg, line_color):
        nonlocal ri
        rows.append([amt(amount, S.row_amount_green
                         if line_color == GREEN else S.row_amount_red),
                     lbl(label_text, S.row_label_green
                         if line_color == GREEN else S.row_label_red)])
        rstyles.extend([
            ('BACKGROUND',    (0, ri), (-1, ri), bg),
            ('LINEABOVE',     (0, ri), (-1, ri), 1.0, line_color),
            ('TOPPADDING',    (0, ri), (-1, ri), 8),
            ('BOTTOMPADDING', (0, ri), (-1, ri), 8),
        ])
        ri += 1

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # EARNINGS SECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    add_hdr('المستحقات', 'EARNINGS')

    # Base salary — always shown
    add_row(data.get('base_salary', 0), 'الراتب الأساسي',
            S.row_label_bold, S.row_amount, WHITE)

    # Itemised allowances / bonuses from line_items
    earn_items = [i for i in data.get('line_items', [])
                  if i.get('type') in ('allowance', 'bonus')]

    if earn_items:
        for idx, item in enumerate(earn_items):
            add_row(
                item.get('amount', 0),
                item.get('desc', item.get('description_ar', 'بدل')),
                S.row_label,
                S.row_amount,
                GRAY_LIGHT if idx % 2 == 0 else WHITE,
            )
    else:
        # Fallback: aggregate allowances if no item detail available
        alw = data.get('allowances_sum', data.get('total_allowances', 0))
        bon = data.get('bonus', 0)
        if alw > 0:
            add_row(alw, 'البدلات الشهرية', S.row_label, S.row_amount, GRAY_LIGHT)
        if bon > 0:
            add_row(bon, 'مكافأة', S.row_label, S.row_amount, WHITE)

    gross = data.get('gross', data.get('gross_salary', 0))
    add_subtotal(gross, 'إجمالي الاستحقاقات', GREEN_LIGHT, GREEN)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # DEDUCTIONS SECTION
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    add_hdr('الاستقطاعات', 'DEDUCTIONS')

    ded_items = [i for i in data.get('line_items', [])
                 if i.get('type') in ('deduction', 'absence', 'advance')]

    if ded_items:
        for idx, item in enumerate(ded_items):
            add_row(
                item.get('amount', 0),
                item.get('desc', item.get('description_ar', 'خصم')),
                S.row_label,
                S.row_amount,
                RED_LIGHT if idx % 2 == 0 else WHITE,
            )
    else:
        # Fallback: show individual deduction fields
        abs_ded = data.get('absence_deduction', 0)
        adv_ded = data.get('advance_deduction', 0)
        oth_ded = data.get('other_deduction',   0)
        abs_d   = data.get('absent_days',       0)
        daily   = data.get('daily_rate',         0)

        if abs_ded > 0:
            add_row(abs_ded,
                    f'خصم الغياب  ({abs_d} يوم × {daily:,.2f} د.ل)',
                    S.row_label, S.row_amount, RED_LIGHT)
        if adv_ded > 0:
            add_row(adv_ded, 'خصم أقساط السلفة',
                    S.row_label, S.row_amount, WHITE)
        if oth_ded > 0:
            add_row(oth_ded, 'خصومات أخرى',
                    S.row_label, S.row_amount, RED_LIGHT)

    total_ded = data.get('total_deductions', 0)
    if total_ded == 0 and not ded_items:
        rows.append([_para('لا توجد استقطاعات هذا الشهر', S.no_items), ''])
        rstyles.extend([
            ('BACKGROUND',    (0, ri), (-1, ri), WHITE),
            ('SPAN',          (0, ri), (-1, ri)),
            ('TOPPADDING',    (0, ri), (-1, ri), 10),
            ('BOTTOMPADDING', (0, ri), (-1, ri), 10),
        ])
        ri += 1

    add_subtotal(total_ded, 'إجمالي الاستقطاعات', RED_LIGHT, RED)

    # ── Assemble table ─────────────────────────────────
    base_style = TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), FONT_REGULAR),
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('LINEBELOW',     (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('BOX',           (0, 0), (-1, -1), 0.8, GRAY_BORDER),
    ])

    table = Table(rows, colWidths=CW, repeatRows=0)
    table.setStyle(base_style)
    for cmd in rstyles:
        table.setStyle(TableStyle([cmd]))

    return [table, Spacer(1, 4 * mm)]


# ── Builder 4: Net Salary Banner ──────────────────────────────────────

def _build_net_banner(S: StyleEngine, data: dict) -> list:
    """
    Prominent navy banner with the net salary:
      [صافي الراتب المستحق]   ← gold label
      [1,234.56]               ← large white amount
      [دينار ليبي — LYD]      ← gold currency
      [أيام العمل: X | ...]   ← grey attendance summary
    """
    net        = data.get('net_pay',       data.get('net_salary', 0))
    wdays      = data.get('working_days',  0)
    absent     = data.get('absent_days',   0)
    daily      = data.get('daily_rate',    0)

    banner = Table(
        [
            [_para('صافي الراتب المستحق',              S.net_label)],
            [_para(f'{net:,.2f}',                       S.net_amount)],
            [_para('دينار ليبي  —  LYD',               S.net_currency)],
            [_para(
                f'أيام العمل: {wdays}  |  '
                f'أيام الغياب: {absent}  |  '
                f'معدل اليوم: {daily:,.2f} د.ل',
                S.net_attendance,
            )],
        ],
        colWidths=[CONTENT_W],
    )
    banner.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (0, 2), NAVY),
        ('BACKGROUND',    (0, 3), (0, 3), NAVY_MID),
        ('LINEABOVE',     (0, 0), (-1, 0), 3, GOLD),
        ('LINEBELOW',     (0, 3), (-1, 3), 1, GOLD),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1),  6),
        ('BOTTOMPADDING', (0, 0), (-1, -1),  6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))

    return [banner, Spacer(1, 5 * mm)]


# ── Builder 5: Signature Block ────────────────────────────────────────

def _build_signatures(S: StyleEngine) -> list:
    """
    Three equidistant signature fields:
      [الإدارة العليا] [مدير الفرع] [توقيع الموظف]
    Each has a line above the label and space for a stamp.
    """
    # Signature lines (drawn as top-border of cells)
    sig_row = Table(
        [[
            _para('الإدارة العليا',  S.sig_title),
            _para('مدير الفرع',      S.sig_title),
            _para('توقيع الموظف',    S.sig_title),
        ]],
        colWidths=_col(0.33, 0.34, 0.33),
    )
    sig_row.setStyle(TableStyle([
        ('LINEABOVE',     (0, 0), (0, 0), 1.2, NAVY),
        ('LINEABOVE',     (1, 0), (1, 0), 1.2, NAVY),
        ('LINEABOVE',     (2, 0), (2, 0), 1.2, NAVY),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 20),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 20),
    ]))

    # Stamp hint row
    stamp_row = Table(
        [[
            _para('ختم الشركة', S.sig_blank),
            _para('',           S.sig_blank),
            _para('',           S.sig_blank),
        ]],
        colWidths=_col(0.33, 0.34, 0.33),
    )
    stamp_row.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))

    return [sig_row, stamp_row, Spacer(1, 3 * mm)]


# ── Builder 6: Footer ─────────────────────────────────────────────────

def _build_footer(S: StyleEngine, ps_num: str) -> list:
    """Navy footer with legal disclaimer and generation timestamp."""
    footer = Table(
        [
            [_para(
                'هذه الوثيقة سجل رسمي ونهائي للراتب — '
                'شركة الخيار لسيارات وقطع غيارها',
                S.footer_main,
            )],
            [_para(
                f'تاريخ الإصدار: {datetime.now().strftime("%d/%m/%Y %H:%M")}  '
                f'|  {ps_num}  |  دفع نقدي  |  دينار ليبي',
                S.footer_sub,
            )],
        ],
        colWidths=[CONTENT_W],
    )
    footer.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('LINEABOVE',     (0, 0), (-1,  0), 3, GOLD),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    return [footer]


# ══════════════════════════════════════════════════════════════════════
# LAYER 4 — PUBLIC API
# ══════════════════════════════════════════════════════════════════════

def generate_payslip_pdf(employee_data: dict,
                          serial_number: int = 1,
                          output_dir=None) -> str:
    """
    Generate a single-employee Arabic payslip PDF.

    Args:
        employee_data:  Payroll compute dict (from payroll_compute_line).
                        Must be fully dynamic — no hardcoded values.
        serial_number:  Used for fallback payslip number and filename.
        output_dir:     Override default save directory.

    Returns:
        str: Absolute path to the saved PDF file.
    """
    _register_fonts()

    # ── Resolve output directory ───────────────────────
    out_dir = Path(output_dir) if output_dir else BASE_DIR / 'hr_data' / 'payslips'
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Extract period metadata ────────────────────────
    year    = int(employee_data.get('year',  date.today().year))
    month   = int(employee_data.get('month', date.today().month))
    emp_num = employee_data.get('employee_number', f'{serial_number:04d}')
    ps_num  = employee_data.get(
        'payslip_number',
        f'PSL-{year}-{month:02d}-{serial_number:04d}',
    )

    # ── Build filename (ASCII-safe, no Arabic chars) ───
    safe_num  = ''.join(c for c in emp_num if c.isalnum() or c in '-_')
    filename  = f'payslip_{safe_num}_{year}_{month:02d}.pdf'
    filepath  = str(out_dir / filename)

    # ── Configure document ─────────────────────────────
    full_name = employee_data.get('full_name', employee_data.get('employee_name', ''))
    doc = SimpleDocTemplate(
        filepath,
        pagesize      = A4,
        rightMargin   = MARGIN,
        leftMargin    = MARGIN,
        topMargin     = 10 * mm,
        bottomMargin  = 10 * mm,
        title         = f'كشف راتب — {full_name} — {MONTH_AR[month]} {year}',
        author        = 'شركة الخيار',
        subject       = 'إذن صرف راتب شهري',
        creator       = 'AlKhayar HR System v5',
    )

    # ── Build style engine ─────────────────────────────
    styles = StyleEngine(FONT_REGULAR, FONT_BOLD)

    # ── Compose flowable story ─────────────────────────
    story: list = []
    story += _build_header(styles, ps_num, year, month)
    story += _build_employee_section(styles, employee_data)
    story += _build_salary_table(styles, employee_data)
    story += _build_net_banner(styles, employee_data)
    story += _build_signatures(styles)
    story += _build_footer(styles, ps_num)

    # ── Render to PDF ──────────────────────────────────
    doc.build(story)
    return filepath


def generate_branch_payroll_summary(payslips: list,
                                     year: int,
                                     month: int,
                                     branch_name: str,
                                     output_dir=None) -> str:
    """
    Generate a branch-level payroll roll-up summary PDF.

    Args:
        payslips:    List of payslip dicts (same structure as generate_payslip_pdf).
        year:        Payroll year.
        month:       Payroll month (1–12).
        branch_name: Display name of the branch.
        output_dir:  Override default save directory.

    Returns:
        str: Absolute path to the saved PDF.
    """
    _register_fonts()

    out_dir = Path(output_dir) if output_dir else BASE_DIR / 'hr_data' / 'payslips'
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_branch = ''.join(c for c in branch_name
                          if c.isalnum() or c in '_- ').strip().replace(' ', '_')
    filename    = f'summary_{safe_branch}_{year}_{month:02d}.pdf'
    filepath    = str(out_dir / filename)

    styles = StyleEngine(FONT_REGULAR, FONT_BOLD)

    doc = SimpleDocTemplate(
        filepath,
        pagesize     = A4,
        rightMargin  = MARGIN,
        leftMargin   = MARGIN,
        topMargin    = 10 * mm,
        bottomMargin = 10 * mm,
        title        = f'مسير رواتب — {branch_name} — {MONTH_AR[month]} {year}',
        author       = 'شركة الخيار',
    )

    story: list = []

    # ── Summary header ─────────────────────────────────
    hdr = Table(
        [
            [_para('شركة الخيار  —  مسير رواتب الفرع',              styles.company_name)],
            [_para(f'فرع: {branch_name}',                             styles.company_tagline)],
            [_para(f'{MONTH_AR[month]} {year}  |  {date.today().strftime("%d/%m/%Y")}',
                   styles.company_info)],
        ],
        colWidths=[CONTENT_W],
    )
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), NAVY),
        ('LINEBELOW',     (0, -1), (-1, -1), 3, GOLD),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    story += [hdr, Spacer(1, 4 * mm)]

    # ── Summary table ──────────────────────────────────
    # RTL column order: [Salary Net | Deductions | Allowances | Base | Name | #]
    COL_W = _col(0.05, 0.28, 0.17, 0.17, 0.16, 0.17)

    headers = [
        _para('الصافي',       styles.summary_hdr),
        _para('الاستقطاعات', styles.summary_hdr),
        _para('البدلات',      styles.summary_hdr),
        _para('الأساسي',      styles.summary_hdr),
        _para('الموظف',       styles.summary_hdr),
        _para('#',            styles.summary_hdr),
    ]
    table_rows = [headers]
    total_net = total_base = total_alw = total_ded = 0.0

    for idx, ps in enumerate(payslips, 1):
        base = ps.get('base_salary', 0)
        alw  = ps.get('allowances_sum',
               ps.get('total_allowances', ps.get('bonus', 0)))
        ded  = ps.get('total_deductions', 0)
        net  = ps.get('net_pay', ps.get('net_salary', 0))
        name = ps.get('full_name', ps.get('employee_name', ''))

        bg = GRAY_LIGHT if idx % 2 == 0 else WHITE
        row = [
            _para(f'{net:,.0f}',  styles.summary_cell),
            _para(f'{ded:,.0f}',  styles.summary_cell),
            _para(f'{alw:,.0f}',  styles.summary_cell),
            _para(f'{base:,.0f}', styles.summary_cell),
            _para(name,            styles.summary_cell),
            _para(str(idx),        styles.summary_cell),
        ]
        table_rows.append(row)
        total_net  += net
        total_base += base
        total_alw  += alw
        total_ded  += ded

    # Totals row
    n = len(table_rows)
    table_rows.append([
        _para(f'{total_net:,.0f}  د.ل', styles.summary_total),
        _para(f'{total_ded:,.0f}',        styles.summary_total),
        _para(f'{total_alw:,.0f}',        styles.summary_total),
        _para(f'{total_base:,.0f}',       styles.summary_total),
        _para(f'الإجمالي — {len(payslips)} موظف', styles.summary_total),
        _para('',                          styles.summary_total),
    ])

    summary_table = Table(table_rows, colWidths=COL_W, repeatRows=1)
    summary_table.setStyle(TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), FONT_REGULAR),
        ('BACKGROUND',    (0, 0), (-1,  0), NAVY),
        ('BACKGROUND',    (0, n), (-1,  n), NAVY_MID),
        ('LINEBELOW',     (0, 0), (-1,  0), 1.0, GOLD),
        ('LINEABOVE',     (0, n), (-1,  n), 1.0, GOLD),
        ('BOX',           (0, 0), (-1, -1), 0.8, GRAY_BORDER),
        ('INNERGRID',     (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ('ALIGN',         (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    story += [summary_table, Spacer(1, 5 * mm)]

    # ── Summary footer ─────────────────────────────────
    ftr = Table(
        [[_para(
            f'شركة الخيار  |  مسير {MONTH_AR[month]} {year}  |  '
            f'فرع: {branch_name}  |  إجمالي الصافي: {total_net:,.2f} د.ل',
            styles.footer_main,
        )]],
        colWidths=[CONTENT_W],
    )
    ftr.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LINEABOVE',  (0, 0), (-1,  0), 3, GOLD),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(ftr)

    doc.build(story)
    return filepath
