"""
account_pdf.py — Account Statement (كشف حساب) PDF generator.
Reuses the font registration + Arabic shaping from payslip_pdf.
"""

from pathlib import Path
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units    import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
)

from payslip_pdf import _register_fonts, _shape
import payslip_pdf as _pspdf

NAVY  = colors.HexColor('#1B2A47')
GOLD  = colors.HexColor('#C49A2A')
GREY  = colors.HexColor('#8A97A8')
LIGHT = colors.HexColor('#F8FAFC')
RED   = colors.HexColor('#C0392B')
GREEN = colors.HexColor('#27AE60')

PAYMENT_TYPES_AR = {"cash": "نقدي", "transfer": "تحويل بنكي"}


def _p(text, size=10, bold=False, color=NAVY, align='RIGHT'):
    _register_fonts()
    style = ParagraphStyle(
        name='p', fontName=_pspdf.FONT_BOLD if bold else _pspdf.FONT_REGULAR,
        fontSize=size, textColor=color, alignment={'RIGHT':2,'LEFT':0,'CENTER':1}[align],
        leading=size*1.4, wordWrap='RTL',
    )
    return Paragraph(_shape(str(text)), style)


def generate_account_statement_pdf(account: dict, ledger: list, balance: dict,
                                    date_from: str = None, date_to: str = None,
                                    output_dir: Path = None) -> Path:
    """Generate an A4 account statement PDF for one account."""
    _register_fonts()
    output_dir = output_dir or Path(__file__).parent / "pdfs" / "accounts"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(ch for ch in account["name"] if ch.isalnum() or ch in " _-").strip().replace(" ", "_")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"كشف_حساب_{safe_name}_{stamp}.pdf"

    doc = SimpleDocTemplate(
        str(filepath), pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=18*mm,
        title=f"كشف حساب {account['name']}",
    )

    story = []
    story.append(_p("شركة الخيار للسيارات وقطع غيارها", 16, bold=True, align='CENTER'))
    story.append(_p("كشف حساب", 13, bold=True, color=GOLD, align='CENTER'))
    story.append(Spacer(1, 6*mm))

    # Account info
    info_rows = [
        [_p(account["name"], 11, bold=True), _p("الحساب", 10, color=GREY)],
        [_p(account.get("phone","") or "—", 10), _p("الهاتف", 10, color=GREY)],
    ]
    period = "كل الحركات"
    if date_from or date_to:
        period = f"من {date_from or '...'} إلى {date_to or '...'}"
    info_rows.append([_p(period, 10), _p("الفترة", 10, color=GREY)])
    it = Table(info_rows, colWidths=[120*mm, 54*mm])
    it.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), LIGHT),
        ('BOX', (0,0), (-1,-1), 0.5, GREY),
        ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),8), ('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),5), ('BOTTOMPADDING',(0,0),(-1,-1),5),
    ]))
    story.append(it)
    story.append(Spacer(1, 6*mm))

    # Transactions table
    header = [
        _p("التاريخ", 9, bold=True, color=colors.white, align='CENTER'),
        _p("العملية", 9, bold=True, color=colors.white, align='CENTER'),
        _p("الوصف", 9, bold=True, color=colors.white, align='CENTER'),
        _p("مدين", 9, bold=True, color=colors.white, align='CENTER'),
        _p("دائن", 9, bold=True, color=colors.white, align='CENTER'),
        _p("الرصيد", 9, bold=True, color=colors.white, align='CENTER'),
    ]
    rows = [header]
    for l in ledger:
        if l["tx_type"] == "charge":
            op = "مستحق" + (f" ({l['ref']})" if l.get("ref") else "")
            debit = f"{l['debit']:,.0f}"
            credit = "—"
        else:
            extra = ""
            if l.get("paid_for_ref"): extra += f" · عن {l['paid_for_ref']}"
            if l.get("handled_by"):   extra += f" · بواسطة {l['handled_by']}"
            op = f"دفعة ({PAYMENT_TYPES_AR.get(l['ref'], l['ref'])}){extra}"
            debit = "—"
            credit = f"{l['credit']:,.0f}"
        rows.append([
            _p(l["tx_date"], 8, align='CENTER'),
            _p(op, 8),
            _p(l.get("description","") or "—", 8),
            _p(debit, 8, color=RED, align='CENTER'),
            _p(credit, 8, color=GREEN, align='CENTER'),
            _p(f"{l['running_balance']:,.0f}", 8, bold=True, align='CENTER'),
        ])

    col_widths = [22*mm, 48*mm, 46*mm, 20*mm, 20*mm, 22*mm]
    tt = Table(rows, colWidths=col_widths, repeatRows=1)
    tt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), NAVY),
        ('BOX', (0,0), (-1,-1), 0.5, GREY),
        ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),4), ('RIGHTPADDING',(0,0),(-1,-1),4),
        ('TOPPADDING',(0,0),(-1,-1),4), ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, LIGHT]),
    ]))
    story.append(tt)
    story.append(Spacer(1, 8*mm))

    # Balance summary
    if balance["balance"] > 0:
        state = "دين علينا"
    elif balance["balance"] < 0:
        state = "رصيد فائض لنا"
    else:
        state = "الحساب متوازن"
    summ = [
        [_p(f"{balance['total_charges']:,.2f} د.ل", 11, bold=True), _p("إجمالي المستحقات", 10, color=GREY)],
        [_p(f"{balance['total_paid']:,.2f} د.ل", 11, bold=True, color=GREEN), _p("إجمالي المدفوع", 10, color=GREY)],
        [_p(f"{abs(balance['balance']):,.2f} د.ل", 13, bold=True, color=GOLD), _p(state, 11, color=GREY)],
    ]
    stbl = Table(summ, colWidths=[90*mm, 84*mm])
    stbl.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.5, GREY),
        ('INNERGRID', (0,0), (-1,-1), 0.3, colors.HexColor('#E2E8F0')),
        ('BACKGROUND', (0,-1), (-1,-1), NAVY),
        ('BACKGROUND', (0,0), (-1,-2), LIGHT),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),10), ('RIGHTPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),7), ('BOTTOMPADDING',(0,0),(-1,-1),7),
    ]))
    story.append(stbl)
    story.append(Spacer(1, 14*mm))

    sigs = [
        [_p("المحاسب", 10, bold=True, color=GREY, align='CENTER'),
         _p("المدير المالي", 10, bold=True, color=GREY, align='CENTER')],
        [_p("__________________", 10, align='CENTER'),
         _p("__________________", 10, align='CENTER')],
    ]
    sg = Table(sigs, colWidths=[87*mm, 87*mm])
    sg.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'), ('TOPPADDING',(0,1),(-1,1),8)]))
    story.append(sg)
    story.append(Spacer(1, 6*mm))
    story.append(_p(f"تاريخ الطباعة: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    8, color=GREY, align='CENTER'))

    doc.build(story)
    return filepath
