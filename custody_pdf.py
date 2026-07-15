"""
custody_pdf.py — Branch Custody PDF Generator
Simple, printable PDFs for:
  1. Individual expense receipt
  2. Monthly custody statement (all expenses + summary)

Reuses font registration from payslip_pdf for consistency.
"""

from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units    import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
)

from payslip_pdf import _register_fonts, _shape, FONT_REGULAR, FONT_BOLD
import payslip_pdf as _pspdf


NAVY   = colors.HexColor('#1B2A47')
GOLD   = colors.HexColor('#C49A2A')
GREY   = colors.HexColor('#8A97A8')
LIGHT  = colors.HexColor('#F8FAFC')
RED    = colors.HexColor('#C0392B')
GREEN  = colors.HexColor('#27AE60')

MONTH_AR = {
    1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل",
    5: "مايو", 6: "يونيو", 7: "يوليو", 8: "أغسطس",
    9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
}


def _p(text, size=10, bold=False, color=NAVY, align='RIGHT'):
    _register_fonts()
    style = ParagraphStyle(
        name='p', fontName=_pspdf.FONT_BOLD if bold else _pspdf.FONT_REGULAR,
        fontSize=size, textColor=color, alignment={'RIGHT':2,'LEFT':0,'CENTER':1}[align],
        leading=size*1.4, wordWrap='RTL',
    )
    return Paragraph(_shape(str(text)), style)


def generate_expense_receipt_pdf(expense: dict, branch_name: str, month_key: str,
                                  output_dir: Path = None) -> Path:
    """Generate a small A5 receipt for a single expense."""
    _register_fonts()
    output_dir = output_dir or Path(__file__).parent / "pdfs" / "custody"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"receipt_{expense.get('id','x')}_{expense.get('expense_date','')}.pdf"
    filepath = output_dir / filename

    doc = SimpleDocTemplate(
        str(filepath), pagesize=A5,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
        title="سند صرف من العهدة",
    )

    story = []

    # Header
    story.append(_p("شركة الخيار للسيارات وقطع غيارها", 14, bold=True, align='CENTER'))
    story.append(_p("سند صرف من عهدة الفرع", 11, color=GREY, align='CENTER'))
    story.append(Spacer(1, 8*mm))

    # Info box
    info = [
        [_p(str(expense.get('id', '—')), 10, bold=True), _p("رقم السند", 10, color=GREY)],
        [_p(branch_name, 10, bold=True), _p("الفرع", 10, color=GREY)],
        [_p(f"{MONTH_AR.get(int(month_key[5:7]),'')} {month_key[:4]}", 10, bold=True), _p("الشهر", 10, color=GREY)],
        [_p(expense.get('expense_date', ''), 10, bold=True), _p("تاريخ الصرف", 10, color=GREY)],
        [_p(expense.get('logged_by', '—'), 10), _p("سُجّل بواسطة", 10, color=GREY)],
    ]
    t = Table(info, colWidths=[85*mm, 35*mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('BOX',        (0,0), (-1,-1), 0.5, GREY),
        ('INNERGRID',  (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0), (-1,-1), 8),
        ('RIGHTPADDING',(0,0),(-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story.append(t)
    story.append(Spacer(1, 10*mm))

    # Description
    story.append(_p("السبب / التفاصيل:", 11, bold=True, color=GREY))
    story.append(Spacer(1, 2*mm))
    story.append(_p(expense.get('description', '—'), 12, bold=True))
    story.append(Spacer(1, 10*mm))

    # Amount banner
    amt = expense.get('amount', 0)
    amt_table = Table([[_p(f"{amt:,.2f} د.ل", 22, bold=True, color=GOLD, align='CENTER')]],
                     colWidths=[120*mm])
    amt_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), NAVY),
        ('BOX',        (0,0), (-1,-1), 1, GOLD),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 14),
        ('BOTTOMPADDING',(0,0),(-1,-1), 14),
    ]))
    story.append(amt_table)
    story.append(Spacer(1, 15*mm))

    # Signatures
    sigs = [
        [_p("توقيع المستلم", 9, color=GREY, align='CENTER'), _p("توقيع مدير الفرع", 9, color=GREY, align='CENTER')],
        [_p("_______________", 10, align='CENTER'), _p("_______________", 10, align='CENTER')],
    ]
    st = Table(sigs, colWidths=[60*mm, 60*mm])
    st.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,0), 3),
        ('BOTTOMPADDING', (0,1), (-1,1), 3),
    ]))
    story.append(st)
    story.append(Spacer(1, 8*mm))

    story.append(_p(f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    8, color=GREY, align='CENTER'))

    doc.build(story)
    return filepath


def generate_custody_monthly_pdf(cust: dict, expenses: list,
                                  branch_name: str, month_key: str,
                                  output_dir: Path = None) -> Path:
    """Generate the monthly custody statement PDF."""
    _register_fonts()
    output_dir = output_dir or Path(__file__).parent / "pdfs" / "custody"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"custody_{branch_name.replace(' ','_')}_{month_key}.pdf"
    filepath = output_dir / filename

    doc = SimpleDocTemplate(
        str(filepath), pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
        title=f"كشف عهدة {branch_name} — {month_key}",
    )

    story = []

    # Header
    story.append(_p("شركة الخيار للسيارات وقطع غيارها", 16, bold=True, align='CENTER'))
    story.append(_p(f"كشف عهدة الفرع — {branch_name}", 13, bold=True, color=GOLD, align='CENTER'))
    story.append(_p(f"شهر {MONTH_AR.get(int(month_key[5:7]),'')} {month_key[:4]}",
                    11, color=GREY, align='CENTER'))
    story.append(Spacer(1, 8*mm))

    # Summary box
    allocated = cust.get('allocated_amount', 0)
    carry     = cust.get('carry_from_previous', 0)
    total_av  = cust.get('total_available', allocated + carry)
    spent     = cust.get('spent', 0)
    remaining = cust.get('remaining', total_av - spent)

    summary_rows = [
        [_p(f"{allocated:,.2f} د.ل", 11, bold=True), _p("المُخصّص للشهر", 10, color=GREY)],
        [_p(f"{carry:,.2f} د.ل", 11, bold=True, color=colors.HexColor('#f39c12')),
         _p("مُرحّل من الشهر السابق", 10, color=GREY)],
        [_p(f"{total_av:,.2f} د.ل", 12, bold=True, color=NAVY),
         _p("إجمالي المتاح", 10, color=GREY)],
        [_p(f"{spent:,.2f} د.ل", 11, bold=True, color=RED),
         _p(f"إجمالي المصروف ({len(expenses)} عملية)", 10, color=GREY)],
        [_p(f"{remaining:,.2f} د.ل", 13, bold=True, color=GOLD),
         _p("المتبقي — يُرحّل للشهر التالي", 10, color=GREY)],
    ]
    st = Table(summary_rows, colWidths=[80*mm, 90*mm])
    st.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, GREY),
        ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,-1), (-1,-1), NAVY),
        ('BACKGROUND', (0,0), (-1,-2), LIGHT),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 7),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(st)
    story.append(Spacer(1, 8*mm))

    # Expenses table
    story.append(_p("تفصيل المصروفات", 12, bold=True, align='RIGHT'))
    story.append(Spacer(1, 3*mm))

    if expenses:
        header = [
            _p("م", 9, bold=True, color=colors.white, align='CENTER'),
            _p("التاريخ", 9, bold=True, color=colors.white, align='CENTER'),
            _p("السبب", 9, bold=True, color=colors.white, align='CENTER'),
            _p("المبلغ (د.ل)", 9, bold=True, color=colors.white, align='CENTER'),
            _p("بواسطة", 9, bold=True, color=colors.white, align='CENTER'),
        ]
        rows = [header]
        for i, e in enumerate(expenses, 1):
            rows.append([
                _p(str(i), 9, align='CENTER'),
                _p(e.get('expense_date',''), 9, align='CENTER'),
                _p(e.get('description','—'), 9),
                _p(f"{e.get('amount',0):,.2f}", 9, bold=True, color=RED, align='CENTER'),
                _p(e.get('logged_by','—'), 8, color=GREY, align='CENTER'),
            ])
        # Total row
        rows.append([
            _p("الإجمالي", 10, bold=True, color=GOLD, align='CENTER'),
            _p("", 9), _p("", 9),
            _p(f"{spent:,.2f}", 11, bold=True, color=GOLD, align='CENTER'),
            _p("", 9),
        ])

        col_widths = [12*mm, 24*mm, 75*mm, 30*mm, 30*mm]
        et = Table(rows, colWidths=col_widths, repeatRows=1)
        et.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), NAVY),
            ('BACKGROUND', (0,-1), (-1,-1), NAVY),
            ('BOX', (0,0), (-1,-1), 0.5, GREY),
            ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, LIGHT]),
        ]))
        story.append(et)
    else:
        story.append(_p("لا توجد مصروفات مسجلة.", 10, color=GREY, align='CENTER'))

    story.append(Spacer(1, 15*mm))

    # Signatures
    sigs = [
        [_p("أمين العهدة", 10, bold=True, color=GREY, align='CENTER'),
         _p("مدير الفرع", 10, bold=True, color=GREY, align='CENTER'),
         _p("المدير المالي", 10, bold=True, color=GREY, align='CENTER')],
        [_p("__________________", 10, align='CENTER'),
         _p("__________________", 10, align='CENTER'),
         _p("__________________", 10, align='CENTER')],
    ]
    st = Table(sigs, colWidths=[57*mm, 57*mm, 57*mm])
    st.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                            ('TOPPADDING',(0,1),(-1,1),8)]))
    story.append(st)
    story.append(Spacer(1, 6*mm))

    story.append(_p(f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    8, color=GREY, align='CENTER'))

    doc.build(story)
    return filepath
