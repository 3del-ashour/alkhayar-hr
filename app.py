"""
نظام إدارة الموارد البشرية والرواتب — الإصدار المؤسسي v4
شركة الخيار للسيارات وقطع غيارها

المستوى: مؤسسي (Enterprise-Grade)
اللغة: عربي كامل
الأمان: RBAC + SHA-256 + قفل تلقائي + سجل تدقيق
المالية: هيكل راتب حقيقي (أساسي + بدلات + خصومات ثابتة)
الرواتب: دورة شهرية مُقفلة غير قابلة للتعديل بعد الإقفال
"""

import streamlit as st
import pandas as pd
import json
import os
import sys
import base64
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import database as db

# Auto-backup once per day on app start (silent — never crashes the app)
db.auto_backup_if_needed()

LOGO_PATH = Path(__file__).parent / "assets" / "sa_logo.png"

MONTH_AR = {1:"يناير",2:"فبراير",3:"مارس",4:"أبريل",5:"مايو",6:"يونيو",
            7:"يوليو",8:"أغسطس",9:"سبتمبر",10:"أكتوبر",11:"نوفمبر",12:"ديسمبر"}

EMP_TYPE_AR = {"full_time":"دوام كامل","part_time":"دوام جزئي","contract":"عقد"}
STATUS_AR   = {"active":"✅ نشط","terminated":"🔴 منهي الخدمة",
               "on_leave":"🟡 إجازة","suspended":"⚠️ موقوف"}
ATT_AR      = {"present":"✅ حاضر","absent":"🔴 غائب","half_day":"🟡 نصف يوم",
               "holiday":"🔵 إجازة","sick_leave":"🟠 إجازة مرضية","annual_leave":"💚 إجازة سنوية"}
ROLE_AR     = {"admin":"مدير النظام","hr":"موارد بشرية","viewer":"مشاهد فقط"}

# ══════════════════════════════════════════════════════════════════
# إعداد الصفحة + CSS
# ══════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="شركة الخيار — نظام الرواتب",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;900&display=swap');

*, html, body, [class*="css"] {
    font-family: 'Cairo', sans-serif !important;
    direction: rtl;
}
section[data-testid="stSidebar"], section[data-testid="stSidebar"] > div { direction: rtl; }
h1,h2,h3,h4 { font-family: 'Cairo', sans-serif !important; }

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: linear-gradient(135deg,#f8fafc,#edf2f7);
    border:1px solid #d0d8e4; border-radius:12px; padding:16px;
    border-right:4px solid #1B2A47;
}
/* ── Buttons ── */
.stButton>button {
    font-family:'Cairo',sans-serif !important;
    font-weight:700; border-radius:8px;
}
.stButton>button[kind="primary"] {
    background:linear-gradient(135deg,#1B2A47,#2E4A7A);
    color:white; border:none;
}
.stButton>button[kind="primary"]:hover {
    background:linear-gradient(135deg,#2E4A7A,#1B2A47);
    box-shadow:0 4px 14px rgba(27,42,71,.35);
}
/* ── Alerts ── */
.ok  {background:#e8f8f0;border:1px solid #27ae60;border-right:4px solid #27ae60;
      border-radius:8px;padding:12px 16px;color:#1a7a46;font-weight:700;}
.err {background:#fdecea;border:1px solid #c0392b;border-right:4px solid #c0392b;
      border-radius:8px;padding:12px 16px;color:#922b21;font-weight:700;}
.inf {background:#e8f4fd;border:1px solid #2980b9;border-right:4px solid #1B2A47;
      border-radius:8px;padding:12px 16px;color:#1a5f8a;font-weight:700;}
.warn{background:#fef9e7;border:1px solid #f39c12;border-right:4px solid #f39c12;
      border-radius:8px;padding:12px 16px;color:#7d6608;font-weight:700;}
/* ── Section header ── */
.sh  {background:linear-gradient(135deg,#1B2A47,#2E4A7A);color:white;
      padding:10px 20px;border-radius:10px;font-size:18px;font-weight:700;
      margin-bottom:20px;text-align:right;}
/* ── Tables RTL ── */
.stDataFrame{direction:rtl;}
.stDataFrame td,.stDataFrame th{text-align:right !important;}
/* ── Inputs RTL ── */
.stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox select{
    direction:rtl;text-align:right;font-family:'Cairo',sans-serif !important;}
/* ── Hide branding ── */
#MainMenu,footer,header{visibility:hidden;}
/* ── Hide "Press Enter to submit form" hint (overlaps with RTL Arabic) ── */
[data-testid="InputInstructions"],
[data-testid="stTextInputInstructions"],
[data-testid="stNumberInputInstructions"] {display:none !important;}
/* ── Hide sidebar collapse button ── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarNavCollapseIcon"],
[data-testid="stSidebarHeader"] button,
button[kind="header"],
button[kind="headerNoPadding"] {display:none !important;}
/* ── Role badge ── */
.badge-admin{background:#1B2A47;color:#C49A2A;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;}
.badge-hr   {background:#27ae60;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;}
.badge-view {background:#8a97a8;color:white;padding:2px 10px;border-radius:12px;font-size:11px;font-weight:700;}
</style>
""", unsafe_allow_html=True)

db.init_db()

# Hide sidebar collapse button via JS (catches dynamic elements CSS misses)
st.markdown("""
<script>
(function hideSidebarBtn(){
    var sel = '[data-testid="stSidebarCollapseButton"],[data-testid="collapsedControl"]';
    function remove(){document.querySelectorAll(sel).forEach(function(el){el.style.display='none';});}
    remove();
    new MutationObserver(remove).observe(document.body,{childList:true,subtree:true});
})();
</script>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# الأدوار والصلاحيات
# ══════════════════════════════════════════════════════════════════

def can(action: str) -> bool:
    """فحص الصلاحية بناءً على دور المستخدم."""
    role = st.session_state.get("user_role", "viewer")
    permissions = {
        "admin":  {"all"},
        "hr":     {"view_employees","add_employee","edit_employee","view_salaries",
                   "set_salary","view_attendance","record_attendance",
                   "view_advances","add_advance","add_adjustment",
                   "view_payroll","generate_payslip","view_reports"},
        "viewer": {"view_employees","view_attendance","view_payroll","view_reports"},
    }
    p = permissions.get(role, set())
    return action in p or "all" in p

def require(action: str):
    if not can(action):
        st.markdown('<div class="err">⛔ ليس لديك صلاحية للوصول إلى هذه الصفحة.</div>',
                    unsafe_allow_html=True)
        st.stop()

# ── Toast + Undo stack ─────────────────────────────────────────────
UNDO_REGISTRY = {
    "advance":         ("سلفة",          lambda i: __import__('database').get_db().__enter__().execute("DELETE FROM advance_instalments WHERE advance_id=?; DELETE FROM advances WHERE id=?", (i,i))),
    "installment":     ("قسط راتب",       lambda i: __import__('database').salary_installment_delete(i)),
    "bonus":           ("مكافأة",         None),
    "penalty":         ("عقوبة",         lambda i: __import__('database').penalty_delete(i)),
    "expense":         ("مصروف شركة",     lambda i: __import__('database').expense_delete(i)),
    "custody_expense": ("مصروف عهدة",     lambda i: __import__('database').branch_custody_expense_delete(i)),
    "charge":          ("مستحق",         lambda i: __import__('database').charge_delete(i)),
    "acc_payment":     ("دفعة حساب",      lambda i: __import__('database').payment_delete(i)),
}

def track_action(msg: str, undo_type: str = None, undo_id: int = None):
    """Show toast + push to undo stack (kept per session, last 5)."""
    st.toast(f"✅ {msg}", icon="✅")
    if undo_type and undo_id and undo_type in UNDO_REGISTRY:
        stack = st.session_state.setdefault("_undo_stack", [])
        stack.append({
            "type": undo_type, "id": int(undo_id), "msg": msg,
            "at": today.strftime("%d/%m %H:%M"),
        })
        st.session_state["_undo_stack"] = stack[-5:]

def do_undo(entry: dict):
    """Perform the undo based on registry."""
    import database as _db
    t, i = entry["type"], entry["id"]
    try:
        if t == "advance":
            with _db.get_db() as c:
                c.execute("DELETE FROM advance_instalments WHERE advance_id=?", (i,))
                c.execute("DELETE FROM advances WHERE id=?", (i,))
            return True, "تم إلغاء السلفة"
        if t == "installment":
            return _db.salary_installment_delete(i)
        if t == "bonus":
            with _db.get_db() as c:
                c.execute("DELETE FROM employee_allowances WHERE id=?", (i,))
            return True, "تم إلغاء المكافأة"
        if t == "penalty":
            return _db.penalty_delete(i)
        if t == "expense":
            return _db.expense_delete(i)
        if t == "custody_expense":
            return _db.branch_custody_expense_delete(i)
        if t == "charge":
            return _db.charge_delete(i)
        if t == "acc_payment":
            return _db.payment_delete(i)
    except Exception as e:
        return False, str(e)
    return False, "نوع غير معروف"

def logo_b64() -> str:
    if LOGO_PATH.exists():
        return base64.b64encode(LOGO_PATH.read_bytes()).decode()
    return ""

# ══════════════════════════════════════════════════════════════════
# تسجيل الدخول
# ══════════════════════════════════════════════════════════════════

def show_login():
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        logo = logo_b64()
        logo_tag = f'<img src="data:image/png;base64,{logo}" style="height:60px;">' if logo else ""
        st.markdown(f"""
        <div style="text-align:center;margin-bottom:28px;">
            {logo_tag}
            <div style="font-size:28px;font-weight:900;color:#1B2A47;margin-top:8px;">شركة الخيار</div>
            <div style="font-size:13px;color:#8a97a8;margin-top:4px;">للسيارات وقطع غيارها —  ليبيا</div>
            <div style="margin-top:18px;background:#edf2f7;border-radius:10px;padding:10px;
                        font-size:14px;font-weight:700;color:#1B2A47;">
                🔒 نظام إدارة الموارد البشرية والرواتب
            </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login"):
            u = st.text_input("اسم المستخدم", placeholder="username")
            p = st.text_input("كلمة المرور", type="password", placeholder="••••••••")
            sub = st.form_submit_button("تسجيل الدخول ←", type="primary", use_container_width=True)

        # ── Enter on username → focus password field ──
        st.components.v1.html("""
        <script>
        (function attachEnterFlow(){
            const doc = window.parent.document;
            function wire(){
                const userInp = doc.querySelector('input[type="text"]:not([data-enter-wired])');
                const passInp = doc.querySelector('input[type="password"]');
                if (userInp && passInp){
                    userInp.setAttribute('data-enter-wired','1');
                    userInp.addEventListener('keydown', function(e){
                        if (e.key === 'Enter' || e.keyCode === 13){
                            e.preventDefault();
                            e.stopPropagation();
                            passInp.focus();
                        }
                    }, true);
                    return true;
                }
                return false;
            }
            let tries = 0;
            const iv = setInterval(function(){
                if (wire() || ++tries > 20) clearInterval(iv);
            }, 200);
        })();
        </script>
        """, height=0)

        if sub:
            if not u or not p:
                st.error("أدخل اسم المستخدم وكلمة المرور")
            else:
                with st.spinner("جارٍ التحقق..."):
                    ok, msg, user = db.verify_login(u.strip(), p)
                if ok:
                    st.session_state.update({
                        "logged_in": True,
                        "username": u.strip(),
                        "display_name": msg,
                        "user_role": user.get("role","viewer"),
                        "user_id": user.get("id"),
                        "branch_access": json.loads(user["branch_access"]) if user.get("branch_access") else None,
                    })
                    st.rerun()
                else:
                    st.error(f"⚠️ {msg}")
        st.markdown('<div style="text-align:center;margin-top:18px;color:#8a97a8;font-size:11px;">🔐 SHA-256 | RBAC | سجل تدقيق كامل</div>', unsafe_allow_html=True)

if not st.session_state.get("logged_in"):
    show_login()
    st.stop()

# ══════════════════════════════════════════════════════════════════
# الشريط الجانبي
# ══════════════════════════════════════════════════════════════════

today = date.today()
role  = st.session_state.get("user_role","viewer")
badge_cls = {"admin":"badge-admin","hr":"badge-hr","viewer":"badge-view"}.get(role,"badge-view")

with st.sidebar:
    logo = logo_b64()
    if logo:
        st.image(base64.b64decode(logo), width=55)
    st.markdown(f"""
    <div style="font-size:17px;font-weight:900;color:#1B2A47;">شركة الخيار</div>
    <div style="font-size:11px;color:#8a97a8;margin-bottom:4px;">للسيارات وقطع غيارها</div>
    <div style="font-size:12px;font-weight:600;color:#1B2A47;">
        {st.session_state['display_name']}
        <span class="{badge_cls}" style="margin-right:6px;">{ROLE_AR.get(role,role)}</span>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    pages = ["📊 لوحة المعلومات","👥 الموظفون","💰 هيكل الرواتب",
             "📅 الحضور والغياب","💵 السلف والقروض","💸 أقساط من الراتب","🎁 المكافآت",
             "⚖️ العقوبات",
             "💰 صرف الراتب الشهري","🧾 مسير الرواتب","📄 كشوف الرواتب","📈 التقارير"]
    if can("all"):
        pages += ["🧾 الحسابات","📦 عهدة الفروع","📒 مصروفات الشركة","👑 إدارة المستخدمين","💼 السحوبات الشخصية","🔒 الأمان"]

    page = st.radio("", pages, label_visibility="hidden")

    # ── Undo panel (admin only) ──
    stack = st.session_state.get("_undo_stack", [])
    if can("all") and stack:
        st.markdown("---")
        with st.expander(f"🔙 تراجع ({len(stack)})"):
            for i, act in enumerate(reversed(stack)):
                label_ar = UNDO_REGISTRY.get(act["type"], (act["type"],))[0]
                c1, c2 = st.columns([4,1])
                c1.markdown(f'<div style="font-size:12px;color:#1B2A47;font-weight:600;">{label_ar}</div><div style="font-size:11px;color:#8a97a8;">{act["at"]} — {act["msg"][:40]}</div>', unsafe_allow_html=True)
                if c2.button("↩️", key=f"undo_{i}_{act['type']}_{act['id']}", help="تراجع عن هذا الإجراء"):
                    ok, msg = do_undo(act)
                    if ok:
                        st.session_state["_undo_stack"].remove(act)
                        st.toast(f"↩️ {msg}", icon="↩️")
                        st.rerun()
                    else:
                        st.toast(f"⚠️ {msg}", icon="⚠️")

    st.markdown("---")
    st.markdown(f'<div style="font-size:11px;color:#8a97a8;">{today.strftime("%d/%m/%Y")} | v4.0</div>',
                unsafe_allow_html=True)
    if st.button("🚪 خروج", use_container_width=True):
        db.audit_log(st.session_state["username"],"LOGOUT")
        st.session_state.clear(); st.rerun()

# ══════════════════════════════════════════════════════════════════
# Dialog helpers (must be defined before the if/elif page chain)
# ══════════════════════════════════════════════════════════════════

@st.dialog("👤 تفاصيل الموظف", width="large")
def _emp_details(emp_id):
    e = db.get_employee(emp_id)
    if not e:
        st.error("الموظف غير موجود"); return
    sal  = db.get_current_salary(emp_id)
    base = sal.get("base_salary", 0) if sal else 0
    alws = db.emp_allowances_get(emp_id, __import__('datetime').date.today().strftime("%Y-%m"))
    status_color = {"active":"#27ae60","terminated":"#c0392b","on_leave":"#f39c12","suspended":"#8a97a8"}.get(e["status"],"#8a97a8")
    status_label = STATUS_AR.get(e["status"], e["status"])
    st.markdown(f"""
    <div style="background:#1B2A47;color:white;padding:16px 20px;border-radius:10px;margin-bottom:16px;direction:rtl;font-family:'Cairo',sans-serif;">
        <div style="font-size:20px;font-weight:900;">{e['full_name']}</div>
        <div style="color:#C49A2A;font-size:13px;margin-top:4px;">{e['employee_number']} · {e.get('job_title','') or 'بدون منصب'}</div>
        <span style="background:{status_color};color:white;padding:2px 12px;border-radius:10px;font-size:12px;font-weight:700;margin-top:6px;display:inline-block;">{status_label}</span>
    </div>
    """, unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📌 المعلومات الأساسية**")
        st.markdown(f"- **الفرع:** {db.BRANCH_NAMES.get(e['branch_id'], e['branch_id'])}")
        st.markdown(f"- **القسم:** {e.get('dept_name','') or '—'}")
        st.markdown(f"- **نوع التوظيف:** {EMP_TYPE_AR.get(e.get('employment_type',''),'—')}")
        st.markdown(f"- **تاريخ التعيين:** {e.get('hire_date','—')}")
        if e.get("termination_date"):
            st.markdown(f"- **تاريخ إنهاء الخدمة:** {e['termination_date']}")
    with c2:
        st.markdown("**📞 معلومات التواصل**")
        st.markdown(f"- **الهاتف:** {e.get('phone','') or '—'}")
        st.markdown(f"- **الرقم الوطني:** {e.get('national_id','') or '—'}")
        st.markdown("**💰 الراتب**")
        st.markdown(f"- **الراتب الأساسي:** {base:,.0f} د.ل")
        alw_sum = sum(a['amount'] for a in alws if a['category']=='allowance')
        ded_sum = sum(a['amount'] for a in alws if a['category']=='deduction')
        if alw_sum: st.markdown(f"- **البدلات:** {alw_sum:,.0f} د.ل")
        if ded_sum: st.markdown(f"- **الخصومات الثابتة:** {ded_sum:,.0f} د.ل")
        st.markdown(f"- **الإجمالي:** {base+alw_sum:,.0f} د.ل")
    if e.get("notes"):
        st.markdown("**📝 ملاحظات**")
        st.info(e["notes"])

@st.dialog("⚠️ تأكيد حذف الموظف")
def _confirm_del_emp(emp_id, emp_name, emp_num, username):
    st.warning(f"سيتم حذف **{emp_num} — {emp_name}** نهائياً مع كل سجلاته.")
    st.error("هذا الإجراء لا يمكن التراجع عنه.")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ نعم، احذف نهائياً", type="primary", use_container_width=True):
        ok, msg = db.delete_employee(emp_id, username)
        st.session_state["_emp_del_msg"] = (ok, msg)
        st.session_state["_emp_goto"] = "📋 قائمة الموظفين"
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ تأكيد حذف المستخدم")
def _confirm_del_user(uid, uname, current_uid, current_uname):
    st.warning(f"هل أنت متأكد من حذف المستخدم **'{uname}'**؟")
    st.error("هذا الإجراء لا يمكن التراجع عنه.")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ نعم، احذف", type="primary", use_container_width=True):
        ok, msg = db.user_delete(uid, current_uid, current_uname)
        st.session_state["_user_del_msg"] = (ok, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()

@st.dialog("🔓 تأكيد إعادة فتح المسير")
def _confirm_reopen(py, pm, username):
    period_label = f"{['','يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'][pm]} {py}"
    st.warning(f"أنت على وشك **إعادة فتح مسير {period_label}** للتعديل.")
    st.info("بعد إعادة الفتح يمكنك إجراء التصحيحات اللازمة ثم إعادة الإقفال.")
    c1, c2 = st.columns(2)
    if c1.button("🔓 نعم، أعد الفتح", type="primary", use_container_width=True):
        ok, msg = db.reopen_payroll(py, pm, username)
        st.session_state["_payroll_fin_msg"] = (ok, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()

@st.dialog("🔒 تأكيد إقفال المسير")
def _confirm_finalize(py, pm, username):
    period_label = f"{['','يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'][pm]} {py}"
    st.error("⚠️ تحذير: هذا الإجراء لا يمكن التراجع عنه!")
    st.warning(f"أنت على وشك **إقفال مسير {period_label}** نهائياً.\n\nبعد الإقفال:\n- لا يمكن تعديل أي أرقام في هذا المسير\n- ستُحدَّث أقساط السلف تلقائياً\n- ستُولَّد كشوف الرواتب PDF")
    st.markdown("هل أنت متأكد تماماً من صحة جميع الأرقام؟")
    c1, c2 = st.columns(2)
    if c1.button("🔒 نعم، أقفل المسير", type="primary", use_container_width=True):
        ok, msg = db.finalize_payroll(py, pm, username)
        if ok:
            try:
                from payslip_pdf import generate_payslip_pdf
                emps_a = db.get_employees(status="active")
                for emp in emps_a:
                    try: generate_payslip_pdf(emp["id"], py, pm)
                    except Exception: pass
            except ImportError:
                pass
            st.session_state["_payroll_fin_msg"] = (True, msg)
        else:
            st.session_state["_payroll_fin_msg"] = (False, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()

@st.dialog("✅ تأكيد تسجيل السحب")
def _confirm_withdrawal(partner_name, amount, w_date, desc, partner_id, username):
    st.success("أنت على وشك تسجيل السحب التالي:")
    st.markdown(f"""
    | | |
    |---|---|
    | **الشخص** | {partner_name} |
    | **المبلغ** | **{amount:,.0f} د.ل** |
    | **التاريخ** | {w_date} |
    | **الوصف** | {desc or '—'} |
    """)
    c1, c2 = st.columns(2)
    if c1.button("✅ نعم، سجّل السحب", type="primary", use_container_width=True):
        ok, msg = db.withdrawal_add(partner_id, amount, w_date, desc, username)
        st.session_state["_wd_msg"] = (ok, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()


@st.dialog("✏️ تعديل السحب")
def _edit_withdrawal(rec, username):
    st.info(f"تعديل سجل بتاريخ {rec['w_date']} — {rec['partner_name']}")
    new_amount = st.number_input("المبلغ الجديد (د.ل)", min_value=1.0, step=50.0,
                                  value=float(rec["amount"]))
    new_date   = st.date_input("التاريخ", value=date.fromisoformat(rec["w_date"]))
    new_desc   = st.text_input("الوصف", value=rec.get("description","") or "")
    c1, c2 = st.columns(2)
    if c1.button("💾 حفظ التعديل", type="primary", use_container_width=True):
        ok, msg = db.withdrawal_edit(rec["id"], new_amount,
                                     new_date.isoformat(), new_desc, username)
        st.session_state["_wd_msg"] = (ok, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()


@st.dialog("⚠️ تأكيد حذف السحب")
def _delete_withdrawal(rec):
    st.error("هل أنت متأكد من حذف هذا السجل؟")
    st.markdown(f"""
    | | |
    |---|---|
    | **الشخص** | {rec['partner_name']} |
    | **المبلغ** | **{rec['amount']:,.0f} د.ل** |
    | **التاريخ** | {rec['w_date']} |
    """)
    st.warning("هذا الإجراء لا يمكن التراجع عنه.")
    c1, c2 = st.columns(2)
    if c1.button("🗑️ نعم، احذف", type="primary", use_container_width=True):
        ok, msg = db.withdrawal_delete(rec["id"])
        st.session_state["_wd_msg"] = (ok, msg)
        st.rerun()
    if c2.button("❌ إلغاء", use_container_width=True):
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# لوحة المعلومات
# ══════════════════════════════════════════════════════════════════
if page == "📊 لوحة المعلومات":
    st.markdown('<div class="sh">📊 لوحة المعلومات الرئيسية</div>', unsafe_allow_html=True)
    kpis = db.get_dashboard_kpis()
    yr,mo = today.year,today.month
    pp = f"{yr:04d}-{mo:02d}"
    run = db.get_payroll_run(pp)

    c1,c2,c3,c4 = st.columns(4)
    c1.metric("الموظفون النشطون", kpis["active_employees"])
    c2.metric("إجمالي مسير الرواتب", f"{kpis['total_payroll']:,.0f} د.ل")
    c3.metric("السلف القائمة", f"{kpis['outstanding_advances']:,.0f} د.ل")
    c4.metric(f"مسير {MONTH_AR[mo]}",
              "✅ مُقفل" if run and run.get("status")=="finalized" else "⏳ مفتوح")

    st.markdown("---")
    cl, cr = st.columns(2)

    with cl:
        st.markdown("#### 📌 توزيع الموظفين حسب الفرع")
        bd = kpis["branch_data"]
        if bd:
            rows_html = ""
            for r in bd:
                rows_html += f"""
                <tr>
                    <td style="font-weight:700;color:#1B2A47;">{db.BRANCH_NAMES.get(r['branch_id'], r['branch_id'])}</td>
                    <td style="text-align:center;font-weight:600;">{r['emp_count']}</td>
                    <td style="font-weight:600;color:#1B2A47;">{r['total_base']:,.0f} د.ل</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">الفرع</th>
                        <th style="padding:10px 14px;text-align:center;font-weight:700;">الموظفون</th>
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">إجمالي الرواتب</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            #dash-branch tbody tr:nth-child(even){{background:#f8fafc;}}
            </style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات.")

    with cr:
        st.markdown("#### 📜 آخر دورات الرواتب")
        history = db.get_payroll_history()[:6]
        if history:
            rows_html = ""
            for h in history:
                status_label = "✅ مُقفل" if h["status"] == "finalized" else "⏳ مسودة"
                status_color = "#27ae60" if h["status"] == "finalized" else "#f39c12"
                rows_html += f"""
                <tr>
                    <td style="font-weight:700;color:#1B2A47;">{h['pay_period']}</td>
                    <td style="font-weight:600;">{h['total_net']:,.0f} د.ل</td>
                    <td style="text-align:center;">{h['employee_count']}</td>
                    <td style="text-align:center;"><span style="background:{status_color};color:white;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">{status_label}</span></td>
                    <td style="color:#555;font-size:13px;">{h.get('finalized_by','—') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">الفترة</th>
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">الصافي</th>
                        <th style="padding:10px 14px;text-align:center;font-weight:700;">موظفون</th>
                        <th style="padding:10px 14px;text-align:center;font-weight:700;">الحالة</th>
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">أُقفل بواسطة</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            </style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا توجد دورات رواتب بعد.")

    st.markdown("---")
    st.markdown("#### ⚠️ السلف القائمة")
    advs = db.get_advances(status="active")
    if advs:
        rows_html = ""
        for a in advs:
            rows_html += f"""
            <tr>
                <td style="font-weight:700;color:#1B2A47;">{a['full_name']}</td>
                <td style="font-weight:600;">{a['amount']:,.0f} د.ل</td>
                <td style="color:#c0392b;font-weight:600;">{a['remaining']:,.0f} د.ل</td>
                <td style="color:#555;">{a['issue_date']}</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
            <thead>
                <tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;font-weight:700;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;font-weight:700;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;font-weight:700;">المتبقي</th>
                    <th style="padding:10px 14px;text-align:right;font-weight:700;">التاريخ</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        <style>
        table tbody tr:nth-child(even){{background:#f8fafc;}}
        table tbody tr:hover{{background:#edf2f7;}}
        table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
        </style>
        """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="ok">✅ لا توجد سلف قائمة</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# الموظفون
# ══════════════════════════════════════════════════════════════════

elif page == "👥 الموظفون":
    require("view_employees")
    st.markdown('<div class="sh">👥 إدارة الموظفين</div>', unsafe_allow_html=True)

    # Navigation — use index-based state to avoid radio key overwriting programmatic switches
    nav_options = ["📋 قائمة الموظفين"]
    if can("add_employee"): nav_options.append("➕ موظف جديد")
    if can("edit_employee"): nav_options.append("✏️ تعديل الملف الوظيفي")

    # Handle deferred navigation (set before rerun, applied before widget instantiation)
    if st.session_state.get("_emp_goto"):
        st.session_state["_emp_view"] = st.session_state.pop("_emp_goto")
    if "_emp_view" not in st.session_state or st.session_state["_emp_view"] not in nav_options:
        st.session_state["_emp_view"] = nav_options[0]

    chosen = st.radio("", nav_options, horizontal=True,
                      label_visibility="hidden", key="_emp_view")
    st.markdown("---")

    if chosen == "📋 قائمة الموظفين":
        # Show persistent success/error message after adding or deleting an employee
        if st.session_state.get("_emp_add_msg"):
            ok_flag, add_msg = st.session_state.pop("_emp_add_msg")
            if ok_flag: st.success(f"✅ {add_msg}")
            else:       st.error(f"⚠️ {add_msg}")
        if st.session_state.get("_emp_del_msg"):
            ok_flag, del_msg = st.session_state.pop("_emp_del_msg")
            if ok_flag: st.success(f"✅ {del_msg}")
            else:       st.error(f"⚠️ {del_msg}")

        emp_filter = st.radio("عرض:", ["✅ النشطون", "🔴 غير النشطون", "📋 الجميع"],
                              horizontal=True, label_visibility="collapsed")
        # Branch filter
        emp_branch_filter = st.selectbox("تصفية بالفرع",
            ["all"] + list(db.BRANCH_NAMES.keys()),
            format_func=lambda x: "🏢 كل الفروع" if x == "all" else db.BRANCH_NAMES[x],
            key="emp_branch_filter")

        if emp_filter == "✅ النشطون":
            emps = db.get_employees(status="active")
        elif emp_filter == "🔴 غير النشطون":
            emps = [e for e in db.get_employees(status="all") if e["status"] != "active"]
        else:
            emps = db.get_employees(status="all")

        # Apply branch filter
        if emp_branch_filter != "all":
            emps = [e for e in emps if str(e.get("branch_id","")) == emp_branch_filter]
        if emps:
            rows_html = ""
            for e in emps:
                sal = db.get_current_salary(e["id"])
                base = sal.get("base_salary", 0) if sal else 0
                alw  = sal.get("total_allowances", 0) if sal else 0
                status_label = STATUS_AR.get(e["status"], e["status"])
                status_color = {"active":"#27ae60","terminated":"#c0392b","on_leave":"#f39c12","suspended":"#8a97a8"}.get(e["status"],"#8a97a8")
                rows_html += f"""
                <tr>
                    <td><code style="background:#e8f0fe;color:#1B2A47;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:700;">{e['employee_number']}</code></td>
                    <td style="font-weight:700;font-size:14px;color:#1B2A47;">{e['full_name']}</td>
                    <td>{db.BRANCH_NAMES.get(e['branch_id'], e['branch_id'])}</td>
                    <td style="color:#555;">{e.get('job_title','') or '—'}</td>
                    <td style="color:#555;">{EMP_TYPE_AR.get(e.get('employment_type',''),'')}</td>
                    <td style="font-weight:600;color:#1B2A47;text-align:left;">{base:,.0f} د.ل</td>
                    <td style="color:#27ae60;font-weight:600;text-align:left;">{alw:,.0f} د.ل</td>
                    <td style="text-align:center;"><span style="background:{status_color};color:white;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700;">{status_label}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:11px 14px;text-align:right;font-weight:700;">الرقم</th>
                        <th style="padding:11px 14px;text-align:right;font-weight:700;">الاسم</th>
                        <th style="padding:11px 14px;text-align:right;font-weight:700;">الفرع</th>
                        <th style="padding:11px 14px;text-align:right;font-weight:700;">المنصب</th>
                        <th style="padding:11px 14px;text-align:right;font-weight:700;">نوع التوظيف</th>
                        <th style="padding:11px 14px;text-align:left;font-weight:700;">الراتب الأساسي</th>
                        <th style="padding:11px 14px;text-align:left;font-weight:700;">البدلات</th>
                        <th style="padding:11px 14px;text-align:center;font-weight:700;">الحالة</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;transition:background 0.15s;}}
            table tbody td{{padding:11px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            </style>
            <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:10px;font-family:'Cairo',sans-serif;">
                إجمالي: {len(emps)} موظف
            </div>
            """, unsafe_allow_html=True)

            # Details viewer below table
            st.markdown("---")
            dc1, dc2 = st.columns([4, 1])
            sel_detail = dc1.selectbox("👁️ عرض تفاصيل موظف:",
                [e["id"] for e in emps],
                format_func=lambda x: next((f"{e['employee_number']} — {e['full_name']}" for e in emps if e["id"]==x), ""),
                label_visibility="visible", key="emp_detail_sel")
            if dc2.button("عرض التفاصيل", type="primary", use_container_width=True):
                _emp_details(sel_detail)
        else:
            st.info("لا يوجد موظفون.")

    elif chosen == "➕ موظف جديد" and can("add_employee"):
        st.subheader("إضافة موظف جديد")
        depts = db.get_departments()
        with st.form("add_emp"):
            c1,c2 = st.columns(2)
            with c1:
                fname    = st.text_input("الاسم الكامل *")
                branch   = st.selectbox("الفرع *",list(db.BRANCH_NAMES.keys()),
                                        format_func=lambda x:db.BRANCH_NAMES[x])
                job      = st.text_input("المنصب / الوظيفة")
                emp_type = st.selectbox("نوع التوظيف",
                                        ["full_time","part_time","contract"],
                                        format_func=lambda x:EMP_TYPE_AR[x])
            with c2:
                dept_id  = st.selectbox("القسم",
                                        [None]+[d["id"] for d in depts],
                                        format_func=lambda x:"— بدون قسم —" if x is None else next((d["name_ar"] for d in depts if d["id"]==x),""))
                hire     = st.date_input("تاريخ التعيين *", value=today)
                phone    = st.text_input("الهاتف")
                nat_id   = st.text_input("الرقم الوطني")
            notes = st.text_area("ملاحظات")
            ok_btn = st.form_submit_button("✅ إضافة الموظف", type="primary")
        if ok_btn:
            if not fname.strip():
                st.error("الاسم مطلوب")
            else:
                res = db.add_employee({
                    "full_name":fname.strip(),"branch_id":branch,
                    "department_id":dept_id,"job_title":job.strip(),
                    "employment_type":emp_type,"hire_date":hire.isoformat(),
                    "phone":phone.strip(),"national_id":nat_id.strip(),"notes":notes.strip()
                }, st.session_state["username"])
                if res[0]:
                    st.session_state["_emp_add_msg"] = (True, res[1])
                    st.session_state["_emp_goto"] = "📋 قائمة الموظفين"
                    st.rerun()
                else:
                    st.error(f"⚠️ {res[1]}")

    elif chosen == "✏️ تعديل الملف الوظيفي" and can("edit_employee"):
        st.subheader("تعديل الملف الوظيفي")
        emps_a = db.get_employees(status="active")
        if emps_a:
            sel = st.selectbox("اختر الموظف",
                               [e["id"] for e in emps_a],
                               format_func=lambda x:f"{db.get_employee(x)['employee_number']} — {db.get_employee(x)['full_name']}")
            emp = db.get_employee(sel)
            depts = db.get_departments()
            with st.form("edit_emp"):
                c1,c2=st.columns(2)
                with c1:
                    nname  = st.text_input("الاسم الكامل",value=emp.get("full_name","") or "")
                    nbranch= st.selectbox("الفرع",list(db.BRANCH_NAMES.keys()),
                                          index=list(db.BRANCH_NAMES.keys()).index(emp["branch_id"]) if emp["branch_id"] in db.BRANCH_NAMES else 0,
                                          format_func=lambda x:db.BRANCH_NAMES[x])
                    njob   = st.text_input("المنصب",value=emp.get("job_title","") or "")
                    ntype  = st.selectbox("نوع التوظيف",
                                          ["full_time","part_time","contract"],
                                          index=["full_time","part_time","contract"].index(emp.get("employment_type","full_time")),
                                          format_func=lambda x:EMP_TYPE_AR[x])
                with c2:
                    nphone = st.text_input("الهاتف",value=emp.get("phone","") or "")
                    nnat   = st.text_input("الرقم الوطني",value=emp.get("national_id","") or "")
                    nstatus= st.selectbox("الحالة",
                                          list(STATUS_AR.keys()),
                                          index=list(STATUS_AR.keys()).index(emp.get("status","active")),
                                          format_func=lambda x:STATUS_AR[x])
                    tdate  = None
                    if nstatus=="terminated":
                        tdate = st.date_input("تاريخ إنهاء الخدمة",value=today)
                    nnotes = st.text_area("ملاحظات",value=emp.get("notes","") or "")
                sv = st.form_submit_button("💾 حفظ التغييرات", type="primary")
            if sv:
                res = db.update_employee(sel,{
                    "full_name":nname.strip(),"branch_id":nbranch,
                    "job_title":njob.strip(),"employment_type":ntype,
                    "status":nstatus,"phone":nphone.strip(),
                    "national_id":nnat.strip(),"notes":nnotes.strip(),
                    "termination_date":tdate.isoformat() if tdate else None
                }, st.session_state["username"])
                if res[0]: st.success(f"✅ {res[1]}")
                else: st.error(f"⚠️ {res[1]}")

            # ── حذف نهائي ──────────────────────────────────────
            if can("admin"):
                st.markdown("---")
                st.markdown("#### 🗑️ حذف الموظف نهائياً")
                if st.button("🗑️ حذف نهائي", type="primary", key="del_btn"):
                    _confirm_del_emp(sel, emp["full_name"], emp["employee_number"], st.session_state["username"])

# ══════════════════════════════════════════════════════════════════
# هيكل الرواتب
# ══════════════════════════════════════════════════════════════════
elif page == "💰 هيكل الرواتب":
    require("view_salaries")
    st.markdown('<div class="sh">💰 هيكل الرواتب والبدلات</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">كل تغيير في الراتب يُحفظ بتاريخه ولا يُحذف أبداً — سجل تاريخي كامل للتدقيق المالي.</div>', unsafe_allow_html=True)
    st.markdown("")

    tab_cur, tab_set, tab_hist = st.tabs(["📋 الرواتب الحالية","✏️ تحديد/تعديل الراتب","📜 السجل التاريخي"])

    with tab_cur:
        report = db.get_salary_report()
        if report:
            total_base = sum(r["base_salary"] or 0 for r in report)
            total_allow = sum(r["allowances"] or 0 for r in report)
            c1,c2,c3 = st.columns(3)
            c1.metric("إجمالي الرواتب الأساسية", f"{total_base:,.0f} د.ل")
            c2.metric("إجمالي البدلات", f"{total_allow:,.0f} د.ل")
            c3.metric("إجمالي الاستحقاق", f"{total_base+total_allow:,.0f} د.ل")
            st.markdown("---")
            rows_html = ""
            for r in report:
                base  = r["base_salary"]  or 0
                allow = r["allowances"]   or 0
                rows_html += f"""<tr>
                    <td><code style="background:#e8f0fe;color:#1B2A47;padding:2px 8px;border-radius:5px;font-size:12px;font-weight:700;">{r['employee_number']}</code></td>
                    <td style="font-weight:700;color:#1B2A47;">{r['full_name']}</td>
                    <td style="color:#555;">{db.BRANCH_NAMES.get(r['branch_id'],'')}</td>
                    <td style="font-weight:600;">{base:,.0f} د.ل</td>
                    <td style="color:#27ae60;font-weight:600;">{allow:,.0f} د.ل</td>
                    <td style="font-weight:700;color:#1B2A47;">{base+allow:,.0f} د.ل</td>
                    <td style="color:#555;font-size:13px;">{r.get('effective_date','') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الرقم</th>
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">الفرع</th>
                    <th style="padding:10px 14px;text-align:right;">الأساسي</th>
                    <th style="padding:10px 14px;text-align:right;">البدلات</th>
                    <th style="padding:10px 14px;text-align:right;">الإجمالي</th>
                    <th style="padding:10px 14px;text-align:right;">ساري من</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا توجد بيانات رواتب.")

    if can("set_salary"):
        with tab_set:
            st.subheader("تحديد أو تعديل هيكل الراتب")
            st.markdown('<div class="warn">⚠️ أي تغيير هنا سيُسجَّل في سجل التدقيق مع اسم المستخدم والوقت.</div>',unsafe_allow_html=True)
            st.markdown("")
            emps_a = db.get_employees(status="active")
            sel = st.selectbox("اختر الموظف",
                               [e["id"] for e in emps_a],
                               format_func=lambda x: next((f"{e['employee_number']} — {e['full_name']}  (أساسي حالي: {db.get_current_salary(e['id']).get('base_salary',0):,.0f} د.ل)" for e in emps_a if e['id']==x),""))

            cur_struct = db.get_current_salary(sel)
            cur_items  = cur_struct.get("items",[]) if cur_struct else []

            # ── Row counter OUTSIDE the form so + / − reflects immediately ──
            st.markdown("---")
            st.markdown("**البدلات الثابتة** (اختياري)")
            st.caption("أضف بدلات ثابتة شهرية مثل: بدل سكن، بدل نقل، بدل اتصالات")
            num_items = st.number_input("عدد البنود الإضافية", 0, 10,
                                        value=len(cur_items), step=1, key=f"nitems_{sel}")

            with st.form("set_sal"):
                c1,c2 = st.columns(2)
                with c1:
                    new_base = st.number_input("الراتب الأساسي (د.ل) *",
                                               min_value=0.0, step=50.0,
                                               value=float(cur_struct.get("base_salary",0)) if cur_struct else 0.0)
                    eff_date = st.date_input("ساري اعتباراً من",value=today)
                with c2:
                    reason   = st.text_input("السبب *", placeholder="زيادة سنوية، ترقية...")
                    approved = st.text_input("معتمد من", value="الإدارة العليا")

                items_data = []
                for i in range(int(num_items)):
                    existing = cur_items[i] if i < len(cur_items) else {}
                    ci1,ci2,ci3 = st.columns([3,2,2])
                    itype = ci1.selectbox(f"نوع {i+1}", ["allowance","deduction"],
                                          index=0 if existing.get("item_type","allowance")=="allowance" else 1,
                                          format_func=lambda x:"✅ بدل" if x=="allowance" else "🔴 خصم ثابت",
                                          key=f"it_{i}")
                    iname = ci2.text_input(f"الاسم {i+1}", value=existing.get("item_name",""), key=f"in_{i}")
                    iamt  = ci3.number_input(f"المبلغ {i+1}", 0.0, step=10.0,
                                             value=float(existing.get("amount",0)), key=f"ia_{i}")
                    if iname.strip():
                        items_data.append({"type":itype,"name":iname.strip(),"amount":iamt,"is_percentage":0})

                save_sal = st.form_submit_button("💾 حفظ هيكل الراتب", type="primary")

            if save_sal:
                if new_base < 0: st.error("الراتب لا يمكن أن يكون سالباً")
                elif not reason.strip(): st.error("السبب مطلوب")
                else:
                    ok,msg = db.set_salary(sel,new_base,items_data,eff_date.isoformat(),
                                           reason,approved,st.session_state["username"])
                    if ok: st.success(f"✅ {msg}"); st.rerun()
                    else: st.error(f"⚠️ {msg}")

    with tab_hist:
        emps_a = db.get_employees(status="active")
        sel2 = st.selectbox("اختر الموظف",
                            [e["id"] for e in emps_a],
                            format_func=lambda x:next((f"{e['employee_number']} — {e['full_name']}" for e in emps_a if e["id"]==x),""),
                            key="sh2")
        hist = db.get_salary_history(sel2)
        if hist:
            rows_html = ""
            for h in hist:
                is_cur = h["is_current"]
                status_label = "✅ ساري" if is_cur else "📦 سابق"
                status_color = "#27ae60" if is_cur else "#8a97a8"
                row_bg = "background:#f0fff4;" if is_cur else ""
                rows_html += f"""<tr style="{row_bg}">
                    <td style="color:#555;">{h['effective_date']}</td>
                    <td style="font-weight:700;color:#1B2A47;">{h['base_salary']:,.0f} د.ل</td>
                    <td style="color:#27ae60;font-weight:600;">{h.get('allowances',0) or 0:,.0f} د.ل</td>
                    <td style="color:#555;">{h.get('reason','') or '—'}</td>
                    <td style="color:#555;">{h.get('approved_by','') or '—'}</td>
                    <td style="color:#555;font-size:12px;">{(h.get('created_at','') or '')[:16]}</td>
                    <td style="text-align:center;"><span style="background:{status_color};color:white;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">{status_label}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">تاريخ السريان</th>
                    <th style="padding:10px 14px;text-align:right;">الراتب الأساسي</th>
                    <th style="padding:10px 14px;text-align:right;">البدلات</th>
                    <th style="padding:10px 14px;text-align:right;">السبب</th>
                    <th style="padding:10px 14px;text-align:right;">معتمد من</th>
                    <th style="padding:10px 14px;text-align:right;">تم الإدخال</th>
                    <th style="padding:10px 14px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا يوجد سجل رواتب لهذا الموظف.")

# ══════════════════════════════════════════════════════════════════
# الحضور والغياب
# ══════════════════════════════════════════════════════════════════
elif page == "📅 الحضور والغياب":
    require("view_attendance")
    st.markdown('<div class="sh">📅 الحضور والغياب</div>', unsafe_allow_html=True)

    tab_rec, tab_view, tab_sum = st.tabs(["✍️ تسجيل الحضور","📋 عرض السجلات","📊 ملخص الشهر"])

    with tab_rec:
        if not can("record_attendance"):
            st.markdown('<div class="err">ليس لديك صلاحية لتسجيل الحضور.</div>',unsafe_allow_html=True)
        else:
            c1,c2 = st.columns(2)
            att_date = c1.date_input("التاريخ",value=today)
            bf = c2.selectbox("تصفية بالفرع",["الكل"]+list(db.BRANCH_NAMES.keys()),
                              format_func=lambda x:"جميع الفروع" if x=="الكل" else db.BRANCH_NAMES[x])
            emps = db.get_employees(status="active")
            filtered = emps if bf=="الكل" else [e for e in emps if e["branch_id"]==bf]
            if filtered:
                existing_att = {a["employee_id"]:a["status"]
                                for a in db.get_attendance_month(att_date.year,att_date.month)
                                if a["att_date"]==att_date.isoformat()}
                if existing_att:
                    st.markdown(f'<div class="inf">✅ تم تسجيل الحضور ليوم {att_date} مسبقاً — يمكنك التعديل والحفظ مجدداً إذا أردت تغيير شيء</div>', unsafe_allow_html=True)
                with st.form("att_form"):
                    statuses={}
                    for emp in filtered:
                        cur=existing_att.get(emp["id"],"present")
                        statuses[emp["id"]] = st.selectbox(
                            f"{emp['full_name']}  ({db.BRANCH_NAMES.get(emp['branch_id'],'')})",
                            list(ATT_AR.keys()),
                            index=list(ATT_AR.keys()).index(cur) if cur in ATT_AR else 0,
                            format_func=lambda x:ATT_AR[x],
                            key=f"a_{emp['id']}")
                    sv_att = st.form_submit_button("💾 حفظ الحضور",type="primary",use_container_width=True)
                if sv_att:
                    for eid,status in statuses.items():
                        db.record_attendance(eid,att_date.isoformat(),status,st.session_state["username"])
                    st.session_state["_att_saved_date"] = att_date.isoformat()
                    st.rerun()

                if st.session_state.get("_att_saved_date"):
                    saved_d = st.session_state.pop("_att_saved_date")
                    st.toast(f"✅ تم حفظ حضور {saved_d} بنجاح", icon="✅")

    with tab_view:
        c1,c2,c3=st.columns(3)
        vy=c1.selectbox("السنة",list(range(2022,today.year+2)),index=today.year-2022,key="avy")
        vm=c2.selectbox("الشهر",list(range(1,13)),format_func=lambda m:MONTH_AR[m],index=today.month-1,key="avm")
        emps_a=db.get_employees(status="active")
        ve=c3.selectbox("الموظف",["الكل"]+[e["id"] for e in emps_a],
                        format_func=lambda x:"الجميع" if x=="الكل" else next((f"{e['employee_number']} — {e['full_name']}" for e in emps_a if e["id"]==x),""),key="ave")
        recs=db.get_attendance_month(vy,vm,ve if ve!="الكل" else None)
        if recs:
            ATT_COLOR = {"present":"#27ae60","absent":"#c0392b","half_day":"#f39c12",
                         "holiday":"#2980b9","sick_leave":"#e67e22","annual_leave":"#27ae60"}
            rows_html = ""
            for r in recs:
                lbl   = ATT_AR.get(r["status"], r["status"])
                color = ATT_COLOR.get(r["status"], "#8a97a8")
                rows_html += f"""<tr>
                    <td style="color:#555;">{r['att_date']}</td>
                    <td style="font-weight:700;color:#1B2A47;">{r['full_name']}</td>
                    <td style="text-align:center;"><span style="background:{color};color:white;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">{lbl}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:6px;font-family:'Cairo',sans-serif;">إجمالي السجلات: {len(recs)}</div>
            """, unsafe_allow_html=True)
        else: st.info("لا توجد سجلات.")

    with tab_sum:
        c1,c2=st.columns(2)
        sy=c1.selectbox("السنة",list(range(2022,today.year+2)),index=today.year-2022,key="asy")
        sm=c2.selectbox("الشهر",list(range(1,13)),format_func=lambda m:MONTH_AR[m],index=today.month-1,key="asm")
        wdays=db._working_days(sy,sm)
        emps=db.get_employees(status="active")
        rows=[]
        for e in emps:
            abs_n=db._count_att_status(e["id"],sy,sm,"absent")
            hday=db._count_att_status(e["id"],sy,sm,"half_day")
            sal=db.get_current_salary(e["id"])
            base=sal.get("base_salary",0) if sal else 0
            daily=base/wdays if wdays else 0
            ded=round(daily*abs_n+daily*0.5*hday,2)
            rows.append((e["full_name"], db.BRANCH_NAMES.get(e["branch_id"],""), wdays, abs_n, hday, ded))
    if rows:
        rows_html = ""
        for name, branch, wd, ab, hd, ded in rows:
            ded_color = "#c0392b" if ded > 0 else "#27ae60"
            rows_html += f"""<tr>
                <td style="font-weight:700;color:#1B2A47;">{name}</td>
                <td style="color:#555;">{branch}</td>
                <td style="text-align:center;">{wd}</td>
                <td style="text-align:center;color:#c0392b;font-weight:600;">{ab}</td>
                <td style="text-align:center;color:#f39c12;font-weight:600;">{hd}</td>
                <td style="font-weight:700;color:{ded_color};">{ded:,.2f} د.ل</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
            <thead><tr style="background:#1B2A47;color:white;">
                <th style="padding:10px 14px;text-align:right;">الموظف</th>
                <th style="padding:10px 14px;text-align:right;">الفرع</th>
                <th style="padding:10px 14px;text-align:center;">أيام العمل</th>
                <th style="padding:10px 14px;text-align:center;">غياب</th>
                <th style="padding:10px 14px;text-align:center;">نصف يوم</th>
                <th style="padding:10px 14px;text-align:right;">خصم الغياب</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
        table tbody tr:hover{{background:#edf2f7;}}
        table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# السلف
# ══════════════════════════════════════════════════════════════════
elif page == "💵 السلف والقروض":
    require("view_advances")
    st.markdown('<div class="sh">💵 السلف والقروض</div>', unsafe_allow_html=True)
    st.markdown("")
    tab_new,tab_act,tab_all = st.tabs(["➕ سلفة جديدة","📋 القائمة","📜 السجل الكامل"])

    with tab_new:
        if not can("add_advance"):
            st.markdown('<div class="err">ليس لديك صلاحية لإضافة سلف.</div>',unsafe_allow_html=True)
        else:
            emps_a=db.get_employees(status="active")
            with st.form("adv_form"):
                c1,c2=st.columns(2)
                with c1:
                    esp=c1.selectbox("الموظف *",[e["id"] for e in emps_a],
                                     format_func=lambda x:next((f"{e['employee_number']} — {e['full_name']}" for e in emps_a if e["id"]==x),""))
                    amt=st.number_input("المبلغ (د.ل) *",min_value=1.0,step=50.0)
                    adv_date=st.date_input("تاريخ الصرف",value=today)
                with c2:
                    n_inst=st.number_input("عدد الأقساط",1,24,1,1)
                    approved=st.text_input("معتمد من",value="الإدارة العليا")
                    reason=st.text_input("السبب")
                sv_adv=st.form_submit_button("✅ تسجيل السلفة",type="primary")
            if sv_adv:
                ok,msg,new_id = db.add_advance(esp,amt,adv_date.isoformat(),reason,approved,int(n_inst),st.session_state["username"])
                if ok:
                    track_action(f"سلفة {amt:,.0f} د.ل — {int(n_inst)} أقساط", "advance", new_id)
                    st.success(f"✅ {msg}"); st.rerun()
                else: st.error(f"⚠️ {msg}")

    with tab_act:
        advs=db.get_advances(status="active")
        if advs:
            rows_html = ""
            for a in advs:
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{a['full_name']}</td>
                    <td style="font-weight:600;">{a['amount']:,.0f} د.ل</td>
                    <td style="color:#c0392b;font-weight:700;">{a['remaining']:,.0f} د.ل</td>
                    <td style="color:#555;">{a['issue_date']}</td>
                    <td style="color:#555;">{a.get('approved_by','') or '—'}</td>
                    <td style="color:#555;">{a.get('reason','') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">المتبقي</th>
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">معتمد من</th>
                    <th style="padding:10px 14px;text-align:right;">السبب</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            st.metric("إجمالي السلف القائمة", f"{sum(a['remaining'] for a in advs):,.0f} د.ل")
        else:
            st.markdown('<div class="ok">✅ لا توجد سلف قائمة</div>', unsafe_allow_html=True)

    with tab_all:
        advs_all=db.get_advances()
        if advs_all:
            rows_html = ""
            for a in advs_all:
                status_label = "✅ مسدد" if a["status"] == "settled" else "⏳ قائم"
                status_color = "#27ae60" if a["status"] == "settled" else "#f39c12"
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{a['full_name']}</td>
                    <td style="font-weight:600;">{a['amount']:,.0f} د.ل</td>
                    <td style="color:#c0392b;font-weight:600;">{a['remaining']:,.0f} د.ل</td>
                    <td style="color:#555;">{a['issue_date']}</td>
                    <td style="text-align:center;"><span style="background:{status_color};color:white;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:700;">{status_label}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">المتبقي</th>
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
        else: st.info("لا توجد سجلات.")

# ══════════════════════════════════════════════════════════════════
# دفعات الراتب (Salary Installments — partial salary during the month)
# ══════════════════════════════════════════════════════════════════
elif page == "💸 أقساط من الراتب":
    require("view_employees")
    st.markdown('<div class="sh">💸 أقساط من الراتب</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 لصرف قسط من راتب الموظف قبل نهاية الشهر. يُخصم تلقائياً من صافي الراتب عند صرف الراتب الشهري.<br>ليست سلفة أو قرض — هي أقساط من راتبه هو. لا يُسمح بصرف أقساط أكثر من الراتب الأساسي.</div>', unsafe_allow_html=True)
    st.markdown("")

    tab_new_si, tab_list_si, tab_bal_si = st.tabs(["➕ قسط جديد", "📋 سجل الشهر", "📊 الرصيد المتبقي"])

    with tab_new_si:
        if not can("add_employee"):
            st.markdown('<div class="err">ليس لديك صلاحية.</div>', unsafe_allow_html=True)
        else:
            emps_si = db.get_employees(status="active")
            # Employee + date OUTSIDE form so balance updates live
            c1, c2 = st.columns(2)
            si_emp = c1.selectbox("الموظف *", [e["id"] for e in emps_si],
                format_func=lambda x: next((f"{e['employee_number']} — {e['full_name']}" for e in emps_si if e["id"]==x), ""),
                key="si_emp_new")
            si_date = c2.date_input("تاريخ الصرف", value=today, key="si_date_new")
            mk_new = si_date.strftime("%Y-%m")

            # Live balance card
            base_new = 0.0
            paid_new = 0.0
            with db.get_db() as _c:
                r = _c.execute("SELECT base_salary FROM salary_structures WHERE employee_id=? ORDER BY effective_date DESC LIMIT 1",(si_emp,)).fetchone()
                if r: base_new = r["base_salary"]
                r2 = _c.execute("SELECT COALESCE(SUM(amount),0) as t FROM salary_installments WHERE employee_id=? AND month_key=? AND settled=0",(si_emp, mk_new)).fetchone()
                if r2: paid_new = r2["t"]
            available = max(0.0, base_new - paid_new)

            st.markdown(f"""
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;font-family:'Cairo',sans-serif;direction:rtl;margin:12px 0;">
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #1B2A47;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">💰 الراتب الأساسي</div>
                    <div style="font-size:20px;font-weight:900;color:#1B2A47;">{base_new:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #c0392b;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">💸 مسحوب هذا الشهر</div>
                    <div style="font-size:20px;font-weight:900;color:#c0392b;">{paid_new:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #27ae60;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">✅ المتاح للسحب</div>
                    <div style="font-size:20px;font-weight:900;color:#27ae60;">{available:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if available <= 0:
                st.markdown(f'<div class="warn">⚠️ الموظف سحب كامل راتبه لهذا الشهر ({paid_new:,.0f} د.ل من {base_new:,.0f} د.ل). أي قسط إضافي سيُرحّل للشهر التالي.</div>', unsafe_allow_html=True)

            with st.form("si_form"):
                c1, c2 = st.columns(2)
                with c1:
                    si_amt = st.number_input("المبلغ (د.ل) *", min_value=1.0, step=50.0)
                with c2:
                    si_approved = st.text_input("معتمد من", value="الإدارة")
                si_desc = st.text_input("ملاحظات", placeholder="سبب / تفاصيل القسط...")
                sv_si = st.form_submit_button("💸 صرف قسط", type="primary")
            if sv_si:
                ok, msg = db.salary_installment_add(si_emp, si_amt, si_date.isoformat(),
                    si_desc.strip(), si_approved.strip(), st.session_state["username"])
                if ok:
                    with db.get_db() as _c:
                        _row = _c.execute("SELECT id FROM salary_installments WHERE employee_id=? ORDER BY id DESC LIMIT 1", (si_emp,)).fetchone()
                        _lid = _row["id"] if _row else None
                    track_action(f"قسط {si_amt:,.0f} د.ل", "installment", _lid)
                    if "⚠️" in msg:
                        st.warning(msg)
                    else:
                        st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"⚠️ {msg}")

    with tab_list_si:
        c1, c2, c3 = st.columns(3)
        si_yr = c1.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="si_yr")
        si_mo = c2.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="si_mo")
        si_emps = db.get_employees(status="all")
        si_emp_filter = c3.selectbox("الموظف", [0]+[e["id"] for e in si_emps],
            format_func=lambda x: "الكل" if x==0 else next((f"{e['full_name']}" for e in si_emps if e["id"]==x), ""), key="si_emp_f")
        mk_si = f"{si_yr:04d}-{si_mo:02d}"
        insts = db.salary_installment_list(
            emp_id=si_emp_filter if si_emp_filter else None,
            month_key=mk_si,
            include_settled=True)
        if insts:
            rows_html = ""
            total_si = 0
            for p in insts:
                total_si += p["amount"]
                settled_badge = '<span style="background:#27ae60;color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">✅ مُسوَّاة</span>' if p.get("settled") else '<span style="background:#f39c12;color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">⏳ معلَّقة</span>'
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{p['full_name']}</td>
                    <td style="font-weight:600;color:#c0392b;">{p['amount']:,.0f} د.ل</td>
                    <td style="color:#555;">{p['pay_date']}</td>
                    <td style="color:#555;">{p.get('description','') or '—'}</td>
                    <td style="color:#555;font-size:12px;">{p.get('approved_by','') or '—'}</td>
                    <td style="text-align:center;">{settled_badge}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">ملاحظات</th>
                    <th style="padding:10px 14px;text-align:right;">معتمد من</th>
                    <th style="padding:10px 14px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            st.metric(f"إجمالي دفعات {MONTH_AR[si_mo]} {si_yr}", f"{total_si:,.0f} د.ل")

            # Delete unsettled
            if can("all"):
                unsettled = [p for p in insts if not p.get("settled")]
                if unsettled:
                    st.markdown("---")
                    st.markdown("#### 🗑️ حذف دفعة معلَّقة")
                    c1, c2 = st.columns([3,1])
                    to_del = c1.selectbox("اختر",
                        [p["id"] for p in unsettled],
                        format_func=lambda x: next((f"{p['full_name']} — {p['amount']:,.0f} د.ل — {p['pay_date']}" for p in unsettled if p["id"]==x),""))
                    if c2.button("🗑️ حذف", type="primary"):
                        ok, msg = db.salary_installment_delete(to_del)
                        if ok:
                            st.success(f"✅ {msg}"); st.rerun()
                        else:
                            st.error(f"⚠️ {msg}")
        else:
            st.info(f"لا توجد دفعات في {MONTH_AR[si_mo]} {si_yr}.")

    with tab_bal_si:
        c1, c2 = st.columns(2)
        bal_yr = c1.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="bal_yr")
        bal_mo = c2.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="bal_mo")
        summary = db.salary_installment_summary(bal_yr, bal_mo)
        if summary:
            rows_html = ""
            total_paid = 0
            total_rem = 0
            for s in summary:
                total_paid += s["paid"]
                total_rem  += s["remaining"]
                pct = round(s["paid"] / s["base_salary"] * 100, 1) if s["base_salary"] > 0 else 0
                bar_color = "#c0392b" if pct >= 90 else "#f39c12" if pct >= 50 else "#27ae60"
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{s['full_name']}</td>
                    <td style="text-align:right;font-weight:600;color:#1B2A47;">{s['base_salary']:,.0f} د.ل</td>
                    <td style="text-align:center;color:#555;">{s['tx_count']}</td>
                    <td style="text-align:right;font-weight:700;color:#c0392b;">{s['paid']:,.0f} د.ل</td>
                    <td style="text-align:right;font-weight:700;color:#27ae60;">{s['remaining']:,.0f} د.ل</td>
                    <td style="text-align:center;"><span style="background:{bar_color};color:white;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700;">{pct}%</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">الراتب الأساسي</th>
                    <th style="padding:10px 14px;text-align:center;">عدد الدفعات</th>
                    <th style="padding:10px 14px;text-align:right;">المسحوب</th>
                    <th style="padding:10px 14px;text-align:right;">المتبقي</th>
                    <th style="padding:10px 14px;text-align:center;">نسبة المسحوب</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            c1, c2 = st.columns(2)
            c1.metric("إجمالي المسحوب", f"{total_paid:,.0f} د.ل")
            c2.metric("إجمالي المتبقي", f"{total_rem:,.0f} د.ل")
        else:
            st.info(f"لا توجد دفعات لـ {MONTH_AR[bal_mo]} {bal_yr}.")

# ══════════════════════════════════════════════════════════════════
# المكافآت (Bonuses only — deductions go through العقوبات)
# ══════════════════════════════════════════════════════════════════
elif page == "🎁 المكافآت":
    st.markdown('<div class="sh">🎁 المكافآت الشهرية</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 لإضافة خصومات أو عقوبات، استخدم صفحة <b>⚖️ العقوبات</b></div>', unsafe_allow_html=True)
    st.markdown("")
    emps_a=db.get_employees(status="active")
    c1,c2=st.columns(2)
    adj_yr=c1.selectbox("السنة",list(range(2022,today.year+2)),index=today.year-2022)
    adj_mo=c2.selectbox("الشهر",list(range(1,13)),format_func=lambda m:MONTH_AR[m],index=today.month-1)
    pp=f"{adj_yr:04d}-{adj_mo:02d}"

    tab_add,tab_view=st.tabs(["➕ إضافة مكافأة","📋 عرض"])
    with tab_add:
        with st.form("adj_form"):
            c1,c2=st.columns(2)
            adj_emp=c1.selectbox("الموظف *",[e["id"] for e in emps_a],
                                  format_func=lambda x:next((f"{e['employee_number']} — {e['full_name']}" for e in emps_a if e["id"]==x),""))
            adj_amt=c2.number_input("المبلغ (د.ل) *",min_value=0.01,step=10.0)
            adj_desc=c2.text_input("الوصف *",placeholder="مثال: مكافأة أداء، مكافأة عمل إضافي")
            sv_adj=st.form_submit_button("🎁 تسجيل المكافأة",type="primary")
        if sv_adj:
            if not adj_desc.strip(): st.error("الوصف مطلوب")
            else:
                db.add_adjustment(adj_emp,pp,"bonus",adj_desc.strip(),adj_amt,st.session_state["username"])
                with db.get_db() as _c:
                    _row = _c.execute("SELECT id FROM employee_allowances WHERE employee_id=? ORDER BY id DESC LIMIT 1", (adj_emp,)).fetchone()
                    _lid = _row["id"] if _row else None
                track_action(f"مكافأة {adj_amt:,.0f} د.ل — {adj_desc.strip()[:30]}", "bonus", _lid)
                st.success("✅ تم تسجيل المكافأة"); st.rerun()

    with tab_view:
        rows=db.get_adjustments_month(pp)
        # Filter to show only bonuses
        rows = [r for r in rows if r.get("adj_type") == "bonus"] if rows else []
        if rows:
            rows_html = ""
            for r in rows:
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{r['full_name']}</td>
                    <td style="font-weight:700;color:#27ae60;">{r['amount']:,.0f} د.ل</td>
                    <td style="color:#555;">{r.get('description','') or '—'}</td>
                    <td style="color:#555;font-size:12px;">{(r.get('created_at','') or '')[:16]}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">الوصف</th>
                    <th style="padding:10px 14px;text-align:right;">التوقيت</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            st.metric("إجمالي المكافآت", f"{sum(r['amount'] for r in rows):,.0f} د.ل")
        else: st.info(f"لا توجد مكافآت لشهر {MONTH_AR[adj_mo]} {adj_yr}.")

# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
# العقوبات (Penalties)
# ══════════════════════════════════════════════════════════════════
elif page == "⚖️ العقوبات":
    require("view_employees")
    st.markdown('<div class="sh">⚖️ العقوبات والجزاءات</div>', unsafe_allow_html=True)

    PENALTY_TYPES = {"خصم مالي": "💰 خصم مالي", "إنذار": "⚠️ إنذار",
                     "إنذار مع خصم": "⚠️💰 إنذار مع خصم", "إيقاف": "🚫 إيقاف"}

    tab_add, tab_list = st.tabs(["➕ عقوبة جديدة", "📋 السجل"])

    with tab_add:
        if not can("add_employee"):
            st.markdown('<div class="err">ليس لديك صلاحية.</div>', unsafe_allow_html=True)
        else:
            emps_pen = db.get_employees(status="active")
            with st.form("pen_form"):
                c1, c2 = st.columns(2)
                with c1:
                    pen_emp = st.selectbox("الموظف *", [e["id"] for e in emps_pen],
                        format_func=lambda x: next((f"{e['employee_number']} — {e['full_name']}" for e in emps_pen if e["id"]==x), ""))
                    pen_type = st.selectbox("نوع العقوبة", list(PENALTY_TYPES.keys()),
                        format_func=lambda x: PENALTY_TYPES[x])
                    pen_amt = st.number_input("مبلغ الخصم (د.ل)", min_value=0.0, step=10.0,
                        help="0 إذا كان إنذار بدون خصم")
                with c2:
                    pen_date = st.date_input("تاريخ العقوبة", value=today)
                    pen_mk_yr = st.selectbox("سنة الخصم", list(range(2022, today.year+2)), index=today.year-2022, key="pen_mk_yr")
                    pen_mk_mo = st.selectbox("شهر الخصم", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="pen_mk_mo")
                    pen_reason = st.text_input("السبب *", placeholder="تأخير، مخالفة، إهمال...")
                sv_pen = st.form_submit_button("⚖️ تسجيل العقوبة", type="primary")
            if sv_pen:
                if not pen_reason.strip():
                    st.error("السبب مطلوب")
                else:
                    mk = f"{pen_mk_yr:04d}-{pen_mk_mo:02d}"
                    ok, msg = db.penalty_add(pen_emp, pen_type, pen_amt, pen_date.isoformat(),
                        pen_reason.strip(), mk, st.session_state["username"])
                    if ok:
                        with db.get_db() as _c:
                            _row = _c.execute("SELECT id FROM penalties WHERE employee_id=? ORDER BY id DESC LIMIT 1", (pen_emp,)).fetchone()
                            _lid = _row["id"] if _row else None
                        track_action(f"عقوبة {pen_amt:,.0f} د.ل — {pen_reason.strip()[:30]}", "penalty", _lid)
                        st.success(f"✅ {msg}")
                        st.rerun()
                    else:
                        st.error(f"⚠️ {msg}")

    with tab_list:
        pen_yr = st.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="pen_list_yr")
        penalties = db.penalty_list(year=pen_yr)
        if penalties:
            rows_html = ""
            for p in penalties:
                ded_label = "✅ مخصوم" if p["deducted"] else "⏳ لم يُخصم"
                ded_color = "#27ae60" if p["deducted"] else "#f39c12"
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{p['full_name']}</td>
                    <td style="text-align:center;"><span style="background:#8e44ad;color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{p['penalty_type']}</span></td>
                    <td style="font-weight:700;color:#c0392b;">{p['amount']:,.0f} د.ل</td>
                    <td style="color:#555;">{p['penalty_date']}</td>
                    <td style="color:#555;">{p.get('reason','') or '—'}</td>
                    <td style="color:#555;font-size:12px;">{p.get('month_key','') or '—'}</td>
                    <td style="text-align:center;"><span style="background:{ded_color};color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{ded_label}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">الموظف</th>
                    <th style="padding:10px 14px;text-align:center;">النوع</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">السبب</th>
                    <th style="padding:10px 14px;text-align:right;">شهر الخصم</th>
                    <th style="padding:10px 14px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            total_pen = sum(p["amount"] for p in penalties)
            not_ded = sum(p["amount"] for p in penalties if not p["deducted"])
            c1, c2 = st.columns(2)
            c1.metric("إجمالي العقوبات", f"{total_pen:,.0f} د.ل")
            c2.metric("لم تُخصم بعد", f"{not_ded:,.0f} د.ل")
        else:
            st.info(f"لا توجد عقوبات في {pen_yr}.")

# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════
# صرف الراتب الشهري — راتب فردي لموظف واحد
# ══════════════════════════════════════════════════════════════════
elif page == "💰 صرف الراتب الشهري":
    require("view_payroll")
    st.markdown('<div class="sh">💰 صرف الراتب الشهري — موظف واحد</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 لصرف راتب موظف واحد في أي وقت خلال الشهر. للمسير الشهري الكامل استخدم <b>🧾 مسير الرواتب</b>.</div>', unsafe_allow_html=True)
    st.markdown("")

    if not can("add_employee"):
        st.markdown('<div class="err">ليس لديك صلاحية لصرف الرواتب.</div>', unsafe_allow_html=True)
    else:
        emps_sal = db.get_employees(status="active")
        c1, c2, c3 = st.columns(3)
        sal_emp = c1.selectbox("الموظف *", [e["id"] for e in emps_sal],
            format_func=lambda x: next((f"{e['employee_number']} — {e['full_name']}" for e in emps_sal if e["id"]==x), ""),
            key="sal_emp")
        sal_yr = c2.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="sal_yr")
        sal_mo = c3.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="sal_mo")
        mk_sal = f"{sal_yr:04d}-{sal_mo:02d}"

        # Check if already issued
        already_issued = None
        with db.get_db() as _conn:
            row = _conn.execute("""
                SELECT pl.payslip_number, pl.net_pay, pp.status
                FROM payroll_lines pl JOIN payroll_periods pp ON pl.period_id=pp.id
                WHERE pp.month_key=? AND pl.employee_id=?
            """, (mk_sal, sal_emp)).fetchone()
            if row:
                already_issued = dict(row)

        st.markdown("")

        if already_issued:
            st.markdown(f'<div class="warn">⚠️ تم صرف راتب هذا الموظف لشهر {MONTH_AR[sal_mo]} {sal_yr} مسبقاً.<br>رقم الكشف: <b>{already_issued["payslip_number"]}</b> — الصافي: <b>{already_issued["net_pay"]:,.2f} د.ل</b></div>', unsafe_allow_html=True)
        else:
            # Compute preview
            try:
                line = db.payroll_compute_line(sal_emp, sal_yr, sal_mo)
            except Exception as e:
                st.error(f"⚠️ {e}")
                line = None

            if line:
                # ── Detail breakdown table (matches app style) ──
                def _row(label, detail, amount, positive=None, sub=False):
                    color = "#1B2A47"
                    if positive is True:  color = "#27ae60"
                    if positive is False: color = "#c0392b"
                    pad = "padding-right:28px;" if sub else ""
                    fw = "600" if sub else "700"
                    fs = "13px" if sub else "14px"
                    return f"""<tr>
                        <td style="font-weight:{fw};color:{color};font-size:{fs};text-align:right;{pad}">{label}</td>
                        <td style="text-align:center;color:#777;font-size:13px;">{detail}</td>
                        <td style="font-weight:{fw};color:{color};font-size:{fs};text-align:right;white-space:nowrap;">{amount}</td>
                    </tr>"""

                rows_html = _row("💰 الراتب الأساسي", f"{line['working_days']} يوم عمل", f"{line['base_salary']:,.0f} د.ل")
                for a in line["allowances"]:
                    if a["category"] == "allowance":
                        rows_html += _row(f"➕ {a['name_ar']}", "—", f"{a['amount']:,.0f} د.ل", positive=True, sub=True)
                if line["absence_deduction"] > 0:
                    rows_html += _row("➖ خصم الغياب", f"{line['absent_days']} يوم", f"({line['absence_deduction']:,.0f}) د.ل", positive=False, sub=True)
                for a in line["allowances"]:
                    if a["category"] == "deduction":
                        rows_html += _row(f"➖ {a['name_ar']}", "—", f"({a['amount']:,.0f}) د.ل", positive=False, sub=True)
                for inst in line["adv_instalments"]:
                    rows_html += _row("➖ قسط سلفة", "—", f"({inst['amount']:,.0f}) د.ل", positive=False, sub=True)
                for pen in line.get("pen_instalments", []):
                    rows_html += _row(f"➖ عقوبة: {pen['reason']}", "—", f"({pen['amount']:,.0f}) د.ل", positive=False, sub=True)
                if line.get("installment_paid", 0) > 0:
                    rows_html += _row("➖ دفعات راتب مسحوبة خلال الشهر", "—", f"({line['installment_paid']:,.0f}) د.ل", positive=False, sub=True)

                # Final total row
                rows_html += f"""<tr style="background:#1B2A47;">
                    <td style="font-weight:900;color:white;font-size:15px;padding:14px 16px;text-align:right;">✅ صافي الراتب المستحق</td>
                    <td></td>
                    <td style="font-weight:900;color:#C49A2A;font-size:15px;text-align:right;padding:14px 16px;white-space:nowrap;">{line['net_pay']:,.0f} د.ل</td>
                </tr>"""

                st.markdown(f"""
                <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
                    <thead><tr style="background:#1B2A47;color:white;">
                        <th style="padding:12px 16px;text-align:right;font-weight:700;">البند</th>
                        <th style="padding:12px 16px;text-align:center;font-weight:700;">التفاصيل</th>
                        <th style="padding:12px 16px;text-align:right;font-weight:700;">المبلغ</th>
                    </tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <style>
                table tbody tr:nth-child(even){{background:#f8fafc;}}
                table tbody tr:hover:not(:last-child){{background:#edf2f7;transition:background 0.15s;}}
                table tbody td{{padding:11px 16px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
                </style>
                """, unsafe_allow_html=True)

                st.markdown("")
                st.markdown("")

                # ── Carry-over notice ──
                carry = line.get("installment_carry", 0)
                if carry > 0:
                    st.markdown(
                        f'<div class="warn">⚠️ الموظف <b>{line["full_name"]}</b> سحب أقساط تتجاوز راتب هذا الشهر.<br>'
                        f'سيتم خصم <b>{line["installment_paid"]:,.2f} د.ل</b> هذا الشهر (الراتب الكامل).<br>'
                        f'المبلغ المتبقي <b>{carry:,.2f} د.ل</b> سيُرحّل تلقائياً ويُخصم من راتب الشهر التالي (كأقساط، ليس سلفة).</div>',
                        unsafe_allow_html=True)
                # Issue button
                confirm = st.checkbox(f"أؤكد صرف راتب **{line['full_name']}** لشهر **{MONTH_AR[sal_mo]} {sal_yr}** بمبلغ **{line['net_pay']:,.2f} د.ل**", key="confirm_sal")
                if st.button("💰 صرف الراتب الآن", type="primary", disabled=not confirm, use_container_width=True):
                    try:
                        with db.get_db() as _c:
                            uid = _c.execute("SELECT id FROM users WHERE username=?", (st.session_state["username"],)).fetchone()
                            finalized_by = uid["id"] if uid else 1
                        ps_num, net = db.payroll_issue_individual(sal_emp, sal_yr, sal_mo, finalized_by)
                        st.success(f"✅ تم صرف الراتب بنجاح — رقم الكشف: **{ps_num}** — الصافي: **{net:,.2f} د.ل**")
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ {e}")

# ══════════════════════════════════════════════════════════════════
# مسير الرواتب الشهري
# ══════════════════════════════════════════════════════════════════
elif page == "🧾 مسير الرواتب":
    require("view_payroll")
    st.markdown('<div class="sh">🧾 مسير الرواتب الشهري</div>', unsafe_allow_html=True)

    c1,c2=st.columns(2)
    py=c1.selectbox("السنة",list(range(2022,today.year+2)),index=today.year-2022)
    pm=c2.selectbox("الشهر",list(range(1,13)),format_func=lambda m:MONTH_AR[m],index=today.month-1)
    pp=f"{py:04d}-{pm:02d}"

    run=db.get_payroll_run(pp)
    finalized = run and run.get("status")=="finalized"

    if finalized:
        st.markdown(f'<div class="ok">✅ مسير {MONTH_AR[pm]} {py} مُقفل بواسطة: {run.get("finalized_by","—")} في {run.get("finalized_at","")[:16]}</div>', unsafe_allow_html=True)
        if can("admin"):
            if st.session_state.get("_payroll_fin_msg"):
                ok_f, fin_msg = st.session_state.pop("_payroll_fin_msg")
                if ok_f: st.success(f"✅ {fin_msg}")
                else:    st.error(f"⚠️ {fin_msg}")
            if st.button("🔓 إعادة فتح المسير للتعديل", use_container_width=False):
                _confirm_reopen(py, pm, st.session_state["username"])
            st.markdown("---")
        entries=db.get_payroll_entries(pp)
    else:
        emps=db.get_employees(status="active")
        entries=[db.calculate_payslip(e["id"],py,pm) for e in emps]
        entries=[e for e in entries if e]

    if entries:
        rows=[]
        for e in entries:
            rows.append({
                "الموظف":e.get("employee_name","") or e.get("full_name",""),
                "الفرع":db.BRANCH_NAMES.get(e.get("branch_id",""),""),
                "الأساسي":e.get("base_salary",0),
                "البدلات":e.get("total_allowances",0),
                "المكافآت":e.get("bonus",0),
                "خصم الغياب":e.get("absence_deduction",0),
                "خصم السلفة":e.get("advance_deduction",0),
                "إجمالي الخصومات":e.get("total_deductions",0),
                "صافي الراتب":e.get("net_salary",0),
            })
        rows_html = ""
        for r in rows:
            net = r["صافي الراتب"]
            rows_html += f"""<tr>
                <td style="font-weight:700;color:#1B2A47;">{r['الموظف']}</td>
                <td style="color:#555;">{r['الفرع']}</td>
                <td style="font-weight:600;">{r['الأساسي']:,.0f} د.ل</td>
                <td style="color:#27ae60;font-weight:600;">{r['البدلات']:,.0f} د.ل</td>
                <td style="color:#2980b9;font-weight:600;">{r['المكافآت']:,.0f} د.ل</td>
                <td style="color:#e67e22;">{r['خصم الغياب']:,.0f} د.ل</td>
                <td style="color:#c0392b;">{r['خصم السلفة']:,.0f} د.ل</td>
                <td style="color:#c0392b;font-weight:600;">{r['إجمالي الخصومات']:,.0f} د.ل</td>
                <td style="font-weight:700;color:#1B2A47;font-size:15px;">{net:,.0f} د.ل</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:13px;margin-top:8px;">
            <thead><tr style="background:#1B2A47;color:white;">
                <th style="padding:10px 12px;text-align:right;">الموظف</th>
                <th style="padding:10px 12px;text-align:right;">الفرع</th>
                <th style="padding:10px 12px;text-align:right;">الأساسي</th>
                <th style="padding:10px 12px;text-align:right;">البدلات</th>
                <th style="padding:10px 12px;text-align:right;">المكافآت</th>
                <th style="padding:10px 12px;text-align:right;">خصم الغياب</th>
                <th style="padding:10px 12px;text-align:right;">خصم السلفة</th>
                <th style="padding:10px 12px;text-align:right;">إجمالي الخصومات</th>
                <th style="padding:10px 12px;text-align:right;background:#2E4A7A;">صافي الراتب</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
        table tbody tr:hover{{background:#edf2f7;}}
        table tbody td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
        """, unsafe_allow_html=True)

        c1,c2,c3=st.columns(3)
        c1.metric("إجمالي الأساسي",f"{sum(r['الأساسي'] for r in rows):,.0f} د.ل")
        c2.metric("إجمالي الصافي للصرف",f"{sum(r['صافي الراتب'] for r in rows):,.0f} د.ل")
        c3.metric("إجمالي الخصومات",f"{sum(r['إجمالي الخصومات'] for r in rows):,.0f} د.ل")

        if not finalized and can("view_payroll"):
            st.markdown("---")
            if st.session_state.get("_payroll_fin_msg"):
                ok_f, fin_msg = st.session_state.pop("_payroll_fin_msg")
                if ok_f: st.success(f"✅ {fin_msg}")
                else:    st.error(f"⚠️ {fin_msg}")
            col_btn, col_info = st.columns([1, 2])
            with col_btn:
                if st.button("🔒 إقفال المسير الشهري", type="primary", use_container_width=True):
                    _confirm_finalize(py, pm, st.session_state["username"])
            with col_info:
                st.markdown('<div class="warn">⚠️ بعد الإقفال: لا يمكن تعديل هذا المسير أبداً. تأكد من صحة جميع الأرقام أولاً.</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# كشوف الرواتب
# ══════════════════════════════════════════════════════════════════
elif page == "📄 كشوف الرواتب":
    require("view_payroll")
    st.markdown('<div class="sh">📄 كشوف الرواتب</div>', unsafe_allow_html=True)

    c1,c2,c3=st.columns(3)
    psy=c1.selectbox("السنة",list(range(2022,today.year+2)),index=today.year-2022)
    psm=c2.selectbox("الشهر",list(range(1,13)),format_func=lambda m:MONTH_AR[m],index=today.month-1)
    emps_a=db.get_employees(status="active")
    pse=c3.selectbox("الموظف",[e["id"] for e in emps_a],
                     format_func=lambda x:next((f"{e['employee_number']} — {e['full_name']}" for e in emps_a if e["id"]==x),""))

    ps=db.calculate_payslip(pse,psy,psm)
    finalized=db.get_payroll_run(f"{psy:04d}-{psm:02d}")
    is_fin = finalized and finalized.get("status")=="finalized"
    month_ar=MONTH_AR[psm]

    logo=logo_b64()
    logo_tag=f'<img src="data:image/png;base64,{logo}" style="height:48px;">' if logo else ""
    status_badge='<span style="background:#27ae60;color:white;padding:3px 10px;border-radius:8px;font-size:11px;font-weight:700;">✅ مُقفل</span>' if is_fin else '<span style="background:#f39c12;color:white;padding:3px 10px;border-radius:8px;font-size:11px;">⏳ مسودة</span>'

    if ps:
        allow_lines = "".join(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f4f9;"><span style="color:#555;">{li["desc"]}</span><span style="color:#27ae60;font-weight:600;">+ {li["amount"]:,.2f} د.ل</span></div>' for li in ps["line_items"] if li["type"]=="allowance")
        ded_lines = "".join(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f4f9;"><span style="color:#555;">{li["desc"]}</span><span style="color:#c0392b;font-weight:600;">- {li["amount"]:,.2f} د.ل</span></div>' for li in ps["line_items"] if li["type"] in ("deduction","absence","advance"))
        bonus_lines= "".join(f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f4f9;"><span style="color:#27ae60;">{li["desc"]}</span><span style="color:#27ae60;font-weight:600;">+ {li["amount"]:,.2f} د.ل</span></div>' for li in ps["line_items"] if li["type"]=="bonus")

        st.markdown(f"""
        <div style="border:2px solid #1B2A47;border-radius:14px;overflow:hidden;max-width:640px;margin:0 auto;font-family:'Cairo',sans-serif;direction:rtl;box-shadow:0 4px 20px rgba(27,42,71,.15);">
            <div style="background:#1B2A47;color:white;padding:20px 24px;">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <div>
                        <div style="font-size:22px;font-weight:900;">شركة الخيار</div>
                        <div style="font-size:11px;color:#C49A2A;margin-top:2px;">لسيارات وقطع غيارها | طرابلس — ليبيا</div>
                        <div style="font-size:10px;color:#8AB0CC;">سجل تجاري: 60378 | +218-91-2109096</div>
                    </div>
                    <div style="text-align:center;">{logo_tag}<br>{status_badge}</div>
                </div>
                <div style="background:rgba(196,154,42,.2);border:1px solid #C49A2A;border-radius:8px;padding:8px 16px;margin-top:14px;display:flex;justify-content:space-between;align-items:center;">
                    <div style="font-size:16px;font-weight:700;">كشف راتب شهري</div>
                    <div style="font-size:14px;color:#C49A2A;font-weight:700;">{month_ar} {psy}</div>
                </div>
            </div>
            <div style="background:#f0f4f9;padding:12px 24px;border-bottom:1px solid #d0d8e4;">
                <div style="display:flex;justify-content:space-between;">
                    <div><div style="font-size:10px;color:#8a97a8;">رقم الموظف</div><div style="font-weight:700;color:#1B2A47;">{ps['employee_number']}</div></div>
                    <div><div style="font-size:10px;color:#8a97a8;">الموظف</div><div style="font-size:16px;font-weight:700;color:#1B2A47;">{ps['employee_name']}</div></div>
                    <div style="text-align:left;"><div style="font-size:10px;color:#8a97a8;">الفرع</div><div style="font-weight:600;color:#1B2A47;">{ps['branch_name']}</div></div>
                </div>
            </div>
            <div style="background:white;padding:14px 24px;">
                <div style="font-size:12px;font-weight:700;color:#27ae60;border-bottom:2px solid #27ae60;padding-bottom:4px;margin-bottom:8px;">▼ المستحقات</div>
                <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f0f4f9;"><span>الراتب الأساسي</span><span style="font-weight:600;">{ps['base_salary']:,.2f} د.ل</span></div>
                {allow_lines}{bonus_lines}
                <div style="display:flex;justify-content:space-between;padding:7px 0;background:#f0fbf4;border-radius:6px;padding:8px 10px;margin-top:6px;"><span style="font-weight:700;">الإجمالي</span><span style="font-weight:700;color:#27ae60;font-size:14px;">{ps['gross_salary']:,.2f} د.ل</span></div>
            </div>
            <div style="background:white;padding:14px 24px;border-top:1px solid #f0f4f9;">
                <div style="font-size:12px;font-weight:700;color:#c0392b;border-bottom:2px solid #c0392b;padding-bottom:4px;margin-bottom:8px;">▼ الاستقطاعات</div>
                {ded_lines if ded_lines else '<div style="color:#8a97a8;font-size:12px;padding:6px 0;">لا توجد استقطاعات هذا الشهر</div>'}
            </div>
            <div style="background:#1B2A47;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;">
                <div><div style="color:#C49A2A;font-size:13px;font-weight:700;">صافي الراتب المستحق</div><div style="color:#8AB0CC;font-size:10px;">أيام العمل: {ps['working_days']} | دفع نقدي</div></div>
                <div style="font-size:28px;font-weight:900;color:white;">{ps['net_salary']:,.2f}<span style="font-size:13px;color:#C49A2A;"> د.ل</span></div>
            </div>
            <div style="background:#f8fafc;padding:14px 24px;display:flex;justify-content:space-around;text-align:center;">
                <div><div style="width:90px;border-top:1px solid #1B2A47;margin:0 auto 5px;"></div><div style="font-size:10px;color:#8a97a8;">توقيع الموظف</div></div>
                <div><div style="width:90px;border-top:1px solid #1B2A47;margin:0 auto 5px;"></div><div style="font-size:10px;color:#8a97a8;">مدير الفرع</div></div>
                <div><div style="width:90px;border-top:1px solid #1B2A47;margin:0 auto 5px;"></div><div style="font-size:10px;color:#8a97a8;">الإدارة العليا</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")
        col_pdf,col_csv=st.columns(2)
        with col_pdf:
            if st.button("📄 تنزيل PDF",type="primary",use_container_width=True):
                try:
                    from payslip_pdf import generate_payslip_pdf
                    path=generate_payslip_pdf(ps,serial_number=pse+psm*100)
                    with open(path,"rb") as f:
                        st.download_button("⬇️ تحميل",data=f.read(),
                                           file_name=os.path.basename(path),
                                           mime="application/pdf",key="pdf_dl")
                except Exception as ex: st.error(f"خطأ: {ex}")
        with col_csv:
            csv=pd.DataFrame([{"الموظف":ps["employee_name"],"الشهر":f"{month_ar} {psy}",
                                "الأساسي":ps["base_salary"],"البدلات":ps["total_allowances"],
                                "المكافآت":ps["bonus"],"الإجمالي":ps["gross_salary"],
                                "خصم الغياب":ps["absence_deduction"],"خصم السلفة":ps["advance_deduction"],
                                "إجمالي الخصومات":ps["total_deductions"],"الصافي":ps["net_salary"]}]).to_csv(index=False).encode("utf-8-sig")
            st.download_button("⬇️ تنزيل CSV",data=csv,file_name=f"كشف_راتب_{ps['employee_name']}_{psy}_{psm:02d}.csv",mime="text/csv",use_container_width=True)

# ══════════════════════════════════════════════════════════════════
# التقارير
# ══════════════════════════════════════════════════════════════════
elif page == "📈 التقارير":
    require("view_reports")
    st.markdown('<div class="sh">📈 التقارير المالية والإدارية</div>', unsafe_allow_html=True)
    tab_sal,tab_pay,tab_att,tab_master=st.tabs(["💰 تقرير الرواتب","🧾 تاريخ المسير","📅 تقرير الحضور","💸 التكلفة الشهرية"])

    with tab_sal:
        report = db.get_salary_report()
        if report:
            total_base  = sum(r["base_salary"]  or 0 for r in report)
            total_allow = sum(r["allowances"]    or 0 for r in report)
            c1, c2 = st.columns(2)
            c1.metric("إجمالي مسير الرواتب", f"{total_base:,.0f} د.ل")
            c2.metric("إجمالي مع البدلات",   f"{total_base + total_allow:,.0f} د.ل")
            rows_html = ""
            for r in report:
                base  = r["base_salary"]  or 0
                allow = r["allowances"]   or 0
                total = base + allow
                rows_html += f"""
                <tr>
                    <td><code style="background:#e8f0fe;color:#1B2A47;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:700;">{r['employee_number']}</code></td>
                    <td style="font-weight:700;color:#1B2A47;">{r['full_name']}</td>
                    <td style="color:#555;">{db.BRANCH_NAMES.get(r['branch_id'],'')}</td>
                    <td style="color:#555;">{r.get('job_title','') or '—'}</td>
                    <td style="font-weight:600;color:#1B2A47;">{base:,.0f} د.ل</td>
                    <td style="color:#27ae60;font-weight:600;">{allow:,.0f} د.ل</td>
                    <td style="font-weight:700;color:#1B2A47;">{total:,.0f} د.ل</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:12px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:11px 14px;text-align:right;">الرقم</th>
                        <th style="padding:11px 14px;text-align:right;">الاسم</th>
                        <th style="padding:11px 14px;text-align:right;">الفرع</th>
                        <th style="padding:11px 14px;text-align:right;">المنصب</th>
                        <th style="padding:11px 14px;text-align:right;">الأساسي (د.ل)</th>
                        <th style="padding:11px 14px;text-align:right;">البدلات (د.ل)</th>
                        <th style="padding:11px 14px;text-align:right;">الإجمالي (د.ل)</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;transition:background 0.15s;}}
            table tbody td{{padding:11px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            </style>
            <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:8px;font-family:'Cairo',sans-serif;">
                إجمالي: {len(report)} موظف
            </div>
            """, unsafe_allow_html=True)
            st.markdown("")
            csv_data = "الرقم,الاسم,الفرع,المنصب,الأساسي,البدلات,الإجمالي\n"
            csv_data += "\n".join(f"{r['employee_number']},{r['full_name']},{db.BRANCH_NAMES.get(r['branch_id'],'')},{r.get('job_title','') or ''},{r['base_salary'] or 0},{r['allowances'] or 0},{(r['base_salary'] or 0)+(r['allowances'] or 0)}" for r in report)
            st.download_button("⬇️ تصدير CSV", data=csv_data.encode("utf-8-sig"),
                               file_name="تقرير_الرواتب.csv", mime="text/csv")
        else:
            st.info("لا توجد بيانات رواتب.")

    with tab_pay:
        history = db.get_payroll_history()
        if history:
            rows_html = ""
            for h in history:
                status_label = "✅ مُقفل" if h["status"] == "finalized" else "⏳ مسودة"
                status_color = "#27ae60" if h["status"] == "finalized" else "#f39c12"
                fin_at = (h.get("finalized_at") or "")[:10] or "—"
                rows_html += f"""
                <tr>
                    <td style="font-weight:700;color:#1B2A47;">{h['pay_period']}</td>
                    <td style="font-weight:600;">{h['total_gross']:,.0f} د.ل</td>
                    <td style="color:#c0392b;font-weight:600;">{h['total_deductions']:,.0f} د.ل</td>
                    <td style="font-weight:700;color:#1B2A47;">{h['total_net']:,.0f} د.ل</td>
                    <td style="text-align:center;">{h['employee_count']}</td>
                    <td style="text-align:center;"><span style="background:{status_color};color:white;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700;">{status_label}</span></td>
                    <td style="color:#555;">{h.get('finalized_by','—') or '—'}</td>
                    <td style="color:#555;">{fin_at}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:12px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:11px 14px;text-align:right;">الفترة</th>
                        <th style="padding:11px 14px;text-align:right;">الإجمالي الخام</th>
                        <th style="padding:11px 14px;text-align:right;">الخصومات</th>
                        <th style="padding:11px 14px;text-align:right;">الصافي</th>
                        <th style="padding:11px 14px;text-align:center;">موظفون</th>
                        <th style="padding:11px 14px;text-align:center;">الحالة</th>
                        <th style="padding:11px 14px;text-align:right;">أُقفل بواسطة</th>
                        <th style="padding:11px 14px;text-align:right;">تاريخ الإقفال</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;transition:background 0.15s;}}
            table tbody td{{padding:11px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            </style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا توجد دورات رواتب.")

    with tab_att:
        c1, c2 = st.columns(2)
        ry = c1.selectbox("السنة", list(range(2022, today.year + 2)), index=today.year - 2022, key="ry")
        rm = c2.selectbox("الشهر", list(range(1, 13)), format_func=lambda m: MONTH_AR[m], index=today.month - 1, key="rm")
        wdays = db._working_days(ry, rm)
        emps  = db.get_employees(status="active")
        att_rows = []
        for e in emps:
            pres  = db._count_att_status(e["id"], ry, rm, "present")
            abs_n = db._count_att_status(e["id"], ry, rm, "absent")
            h_n   = db._count_att_status(e["id"], ry, rm, "half_day")
            pct   = round(pres / wdays * 100 if wdays else 0, 1)
            att_rows.append((e["employee_number"], e["full_name"],
                             db.BRANCH_NAMES.get(e["branch_id"], ""),
                             pres, abs_n, h_n, pct))
        if att_rows:
            rows_html = ""
            for emp_num, name, branch, pres, abs_n, h_n, pct in att_rows:
                pct_color = "#27ae60" if pct >= 90 else "#f39c12" if pct >= 75 else "#c0392b"
                rows_html += f"""
                <tr>
                    <td><code style="background:#e8f0fe;color:#1B2A47;padding:3px 10px;border-radius:6px;font-size:13px;font-weight:700;">{emp_num}</code></td>
                    <td style="font-weight:700;color:#1B2A47;">{name}</td>
                    <td style="color:#555;">{branch}</td>
                    <td style="text-align:center;font-weight:600;color:#27ae60;">{pres}</td>
                    <td style="text-align:center;font-weight:600;color:#c0392b;">{abs_n}</td>
                    <td style="text-align:center;font-weight:600;color:#f39c12;">{h_n}</td>
                    <td style="text-align:center;"><span style="background:{pct_color};color:white;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700;">{pct}%</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:12px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:11px 14px;text-align:right;">الرقم</th>
                        <th style="padding:11px 14px;text-align:right;">الاسم</th>
                        <th style="padding:11px 14px;text-align:right;">الفرع</th>
                        <th style="padding:11px 14px;text-align:center;">حاضر</th>
                        <th style="padding:11px 14px;text-align:center;">غائب</th>
                        <th style="padding:11px 14px;text-align:center;">نصف يوم</th>
                        <th style="padding:11px 14px;text-align:center;">نسبة الحضور</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>
            table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;transition:background 0.15s;}}
            table tbody td{{padding:11px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            </style>
            <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:8px;font-family:'Cairo',sans-serif;">
                أيام العمل في الشهر: {wdays} يوم
            </div>
            """, unsafe_allow_html=True)
            st.markdown("")
            csv_att = "الرقم,الاسم,الفرع,حاضر,غائب,نصف يوم,نسبة الحضور\n"
            csv_att += "\n".join(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]}%" for r in att_rows)
            st.download_button("⬇️ تصدير CSV", data=csv_att.encode("utf-8-sig"),
                               file_name=f"تقرير_حضور_{ry}_{rm:02d}.csv", mime="text/csv")
        else:
            st.info("لا يوجد موظفون نشطون.")

    with tab_master:
        mc1, mc2 = st.columns(2)
        mst_yr = mc1.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="mst_yr")
        mst_mo = mc2.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="mst_mo")
        mk_mst = f"{mst_yr:04d}-{mst_mo:02d}"

        # ── 1. الرواتب (مسير مُقفل) ───────────────────────────────
        payroll_rows = db.get_payroll_history()
        finalized = [p for p in payroll_rows if p["pay_period"] == mk_mst and p["status"] == "finalized"]
        sal_net   = sum(p["total_net"] for p in finalized)
        sal_gross = sum(p["total_gross"] for p in finalized)
        sal_ded   = sum(p["total_deductions"] for p in finalized)

        # ── 2. السلف ──────────────────────────────────────────────
        with db.get_db() as _conn:
            adv_rows = _conn.execute("""
                SELECT COALESCE(SUM(amount),0) as total, COUNT(*) as cnt
                FROM advances WHERE strftime('%Y-%m', issue_date) = ?
            """, (mk_mst,)).fetchone()
        adv_total = adv_rows["total"] if adv_rows else 0
        adv_cnt   = adv_rows["cnt"]   if adv_rows else 0

        # ── 3. المكافآت ───────────────────────────────────────────
        bonuses = db.get_adjustments_month(mk_mst)
        bonus_total = sum(b["amount"] for b in bonuses if b.get("adj_type") == "bonus")
        bonus_cnt   = len([b for b in bonuses if b.get("adj_type") == "bonus"])

        # ── 4. مصروفات الشركة ─────────────────────────────────────
        exp_rows  = db.expense_list(month_key=mk_mst)
        exp_total = sum(e["amount"] for e in exp_rows)
        exp_cnt   = len(exp_rows)

        # ── الإجمالي ──────────────────────────────────────────────
        grand_total = sal_net + adv_total + bonus_total + exp_total

        st.markdown("")

        # ── البطاقات العلوية ──────────────────────────────────────
        st.markdown(f"""
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;font-family:'Cairo',sans-serif;direction:rtl;margin-bottom:20px;">
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #1B2A47;">
                <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">💰 صافي الرواتب</div>
                <div style="font-size:22px;font-weight:900;color:#1B2A47;">{sal_net:,.0f}</div>
                <div style="font-size:11px;color:#aaa;">د.ل</div>
            </div>
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #2980b9;">
                <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">💵 السلف</div>
                <div style="font-size:22px;font-weight:900;color:#2980b9;">{adv_total:,.0f}</div>
                <div style="font-size:11px;color:#aaa;">{adv_cnt} سلفة</div>
            </div>
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #27ae60;">
                <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">🎁 المكافآت</div>
                <div style="font-size:22px;font-weight:900;color:#27ae60;">{bonus_total:,.0f}</div>
                <div style="font-size:11px;color:#aaa;">{bonus_cnt} مكافأة</div>
            </div>
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #8e44ad;">
                <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">📒 مصروفات الشركة</div>
                <div style="font-size:22px;font-weight:900;color:#8e44ad;">{exp_total:,.0f}</div>
                <div style="font-size:11px;color:#aaa;">{exp_cnt} عملية</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── بطاقة الإجمالي ────────────────────────────────────────
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1B2A47 0%,#2c3e6b 100%);border-radius:14px;padding:24px 32px;display:flex;align-items:center;justify-content:space-between;font-family:'Cairo',sans-serif;direction:rtl;margin-bottom:24px;">
            <div>
                <div style="color:#8AB0CC;font-size:13px;font-weight:600;">إجمالي ما أنفقته الشركة</div>
                <div style="color:#C49A2A;font-size:15px;font-weight:700;margin-top:2px;">{MONTH_AR[mst_mo]} {mst_yr}</div>
            </div>
            <div style="text-align:left;">
                <span style="color:white;font-size:38px;font-weight:900;">{grand_total:,.0f}</span>
                <span style="color:#8AB0CC;font-size:18px;"> د.ل</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── جدول التفصيل ──────────────────────────────────────────
        def _row(label, count, amount, bold=True, sub=False, amt_color="#1B2A47"):
            lbl_color = "#1B2A47"
            bg = ""
            pad = "padding-right:32px;" if sub else ""
            fw = "600" if sub else "700"
            fs = "13px" if sub else "14px"
            cnt_color = "#999" if sub else "#555"
            return f"""<tr style="{bg}">
                <td style="font-weight:{fw};color:{lbl_color};font-size:{fs};text-align:right;{pad}">{label}</td>
                <td style="text-align:center;color:{cnt_color};font-size:13px;">{count}</td>
                <td style="font-weight:{fw};color:{amt_color};font-size:{fs};text-align:right;white-space:nowrap;">{amount}</td>
            </tr>"""

        rows_html  = _row("💰 صافي الرواتب المدفوعة", f"{len(finalized)} مسير", f"{sal_net:,.0f} د.ل")
        rows_html += _row("الراتب قبل أي خصومات", "—", f"{sal_gross:,.0f} د.ل", sub=True, amt_color="#555")
        rows_html += _row("الخصومات", "—", f"({sal_ded:,.0f}) د.ل", sub=True, amt_color="#c0392b")
        rows_html += _row("💵 السلف المصروفة", adv_cnt, f"{adv_total:,.0f} د.ل")
        rows_html += _row("🎁 المكافآت", bonus_cnt, f"{bonus_total:,.0f} د.ل")
        rows_html += _row("📒 مصروفات الشركة", exp_cnt, f"{exp_total:,.0f} د.ل")

        if exp_rows:
            by_cat = {}
            for e in exp_rows:
                by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
            for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
                rows_html += _row(cat, "—", f"{amt:,.0f} د.ل", sub=True, amt_color="#555")

        rows_html += f"""<tr style="background:#1B2A47;">
            <td style="font-weight:900;color:white;font-size:15px;padding:14px 16px;text-align:right;">🏁 الإجمالي الكلي</td>
            <td></td>
            <td style="font-weight:900;color:#C49A2A;font-size:15px;text-align:right;padding:14px 16px;white-space:nowrap;">{grand_total:,.0f} د.ل</td>
        </tr>"""

        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.07);">
            <thead><tr style="background:#2c3e6b;color:white;">
                <th style="padding:12px 16px;text-align:right;font-weight:700;">البند</th>
                <th style="padding:12px 16px;text-align:center;font-weight:700;">العدد</th>
                <th style="padding:12px 16px;text-align:right;font-weight:700;">المبلغ</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <style>
        table tbody tr:nth-child(even){{background:#f8fafc;}}
        table tbody tr:hover:not(:last-child){{background:#edf2f7;transition:background 0.15s;}}
        table tbody td{{padding:11px 16px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
        </style>
        """, unsafe_allow_html=True)

        st.markdown("")
        csv_master  = f"التكلفة الشهرية — {MONTH_AR[mst_mo]} {mst_yr}\n\n"
        csv_master += "البند,المبلغ\n"
        csv_master += f"صافي الرواتب,{sal_net}\n"
        csv_master += f"السلف,{adv_total}\n"
        csv_master += f"المكافآت,{bonus_total}\n"
        csv_master += f"مصروفات الشركة,{exp_total}\n"
        csv_master += f"الإجمالي الكلي,{grand_total}\n"
        st.download_button("⬇️ تصدير CSV", data=csv_master.encode("utf-8-sig"),
                           file_name=f"تكلفة_{mst_yr}_{mst_mo:02d}.csv", mime="text/csv")

# ══════════════════════════════════════════════════════════════════
# الحسابات (Accounts Ledger — generic party ledger)
# ══════════════════════════════════════════════════════════════════
elif page == "🧾 الحسابات":
    require("all")
    st.markdown('<div class="sh">🧾 الحسابات وكشوف الحساب</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 لكل جهة (مورد، وكيل...) حساب مستقل. نسجّل المستحقات (ما علينا) والمدفوعات — والرصيد يتراكم تلقائياً: <b>موجب = دين علينا</b>، <b>سالب = رصيد فائض لنا</b>.</div>', unsafe_allow_html=True)
    st.markdown("")

    accts = db.account_list()
    if not accts:
        st.warning("لا يوجد حساب مُسجَّل. أضف حساباً أولاً.")
        with st.form("new_acct_form"):
            nc_name = st.text_input("اسم الحساب *")
            nc_phone = st.text_input("رقم الهاتف")
            nc_notes = st.text_input("ملاحظات")
            if st.form_submit_button("➕ إضافة حساب", type="primary"):
                ok, msg = db.account_add(nc_name, nc_phone, nc_notes)
                if ok: st.success(f"✅ {msg}"); st.rerun()
                else: st.error(f"⚠️ {msg}")
        st.stop()

    def _acct_label(x):
        a = next((a for a in accts if a["id"]==x), None)
        if not a: return ""
        return f"{a['name']}" + (f" — 📞 {a['phone']}" if a.get('phone') else "")
    acct_sel = st.selectbox("اختر الحساب", [a["id"] for a in accts], format_func=_acct_label)

    bal = db.account_balance(acct_sel)
    if bal["balance"] > 0:
        state_label, state_val_color = "علينا دين له", "#e74c3c"
    elif bal["balance"] < 0:
        state_label, state_val_color = "رصيد فائض لنا", "#C49A2A"
    else:
        state_label, state_val_color = "الحساب متوازن", "#C49A2A"

    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;font-family:'Cairo',sans-serif;direction:rtl;margin:12px 0 20px 0;">
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #1B2A47;">
            <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">📥 إجمالي المستحقات</div>
            <div style="font-size:22px;font-weight:900;color:#1B2A47;">{bal['total_charges']:,.0f}</div>
            <div style="font-size:11px;color:#aaa;">د.ل</div>
        </div>
        <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:18px 16px;border-top:4px solid #27ae60;">
            <div style="font-size:12px;color:#8a97a8;font-weight:600;margin-bottom:6px;">💰 إجمالي المدفوع</div>
            <div style="font-size:22px;font-weight:900;color:#27ae60;">{bal['total_paid']:,.0f}</div>
            <div style="font-size:11px;color:#aaa;">د.ل</div>
        </div>
        <div style="background:linear-gradient(135deg,#1B2A47,#2c3e6b);border-radius:12px;padding:18px 16px;">
            <div style="font-size:12px;color:#8AB0CC;font-weight:600;margin-bottom:6px;">⚖️ {state_label}</div>
            <div style="font-size:24px;font-weight:900;color:{state_val_color};">{abs(bal['balance']):,.0f}</div>
            <div style="font-size:11px;color:#8AB0CC;">د.ل</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab_charge, tab_pay, tab_ledger, tab_list, tab_accts = st.tabs(
        ["➕ تسجيل مستحق", "💰 تسجيل دفعة", "📊 كشف الحساب", "📋 المستحقات", "👤 الحسابات"])

    with tab_charge:
        with st.form("charge_form"):
            c1, c2 = st.columns(2)
            with c1:
                ch_amount = st.number_input("المبلغ المستحق (د.ل) *", min_value=0.0, step=100.0)
                ch_ref = st.text_input("رقم مرجعي", placeholder="فاتورة / طلبية / بوليصة... (اختياري)")
            with c2:
                ch_date = st.date_input("التاريخ", value=today)
            ch_desc = st.text_input("الوصف *", placeholder="سبب المستحق / تفاصيله...")
            sv_charge = st.form_submit_button("📥 تسجيل المستحق", type="primary")
        if sv_charge:
            if not ch_desc.strip():
                st.error("الوصف مطلوب")
            else:
                ok, msg = db.charge_add(acct_sel, ch_amount, ch_date.isoformat(),
                    ch_ref.strip(), ch_desc.strip(), st.session_state["username"])
                if ok:
                    with db.get_db() as _c:
                        _row = _c.execute("SELECT id FROM account_charges ORDER BY id DESC LIMIT 1").fetchone()
                        _lid = _row["id"] if _row else None
                    track_action(f"مستحق {ch_amount:,.0f} د.ل — {ch_desc.strip()[:30]}", "charge", _lid)
                    st.success(f"✅ {msg}"); st.rerun()
                else:
                    st.error(f"⚠️ {msg}")

    with tab_pay:
        acct_charges = db.charges_with_status(acct_sel)
        charge_opts = [0] + [c["id"] for c in acct_charges]
        def _charge_label(x):
            if x == 0:
                return "— دفعة عامة (غير مرتبطة بمستحق) —"
            c = next((c for c in acct_charges if c["id"]==x), None)
            if not c: return ""
            refp = f"{c['reference']} · " if c.get('reference') else ""
            return f"{refp}{c['description'][:35]} — متبقي {c['remaining_amount']:,.0f} د.ل"

        with st.form("acc_pay_form"):
            pay_charge = st.selectbox("المستحق المرتبط", charge_opts, format_func=_charge_label)
            c1, c2 = st.columns(2)
            with c1:
                pay_amt = st.number_input("المبلغ (د.ل) *", min_value=1.0, step=100.0)
                pay_type = st.selectbox("طريقة الدفع *", list(db.PAYMENT_TYPES_AR.keys()),
                    format_func=lambda x: db.PAYMENT_TYPES_AR[x])
            with c2:
                pay_date = st.date_input("تاريخ الدفع", value=today)
                pay_handler = st.text_input("مَن سلّم المبلغ / نفّذ العملية", placeholder="اسم الشخص الذي دفع أو حوّل")
            pay_desc = st.text_input("الوصف", placeholder="دفعة عن كذا...")
            pay_notes = st.text_input("ملاحظات", placeholder="أي تفاصيل إضافية...")
            sv_pay = st.form_submit_button("💰 تسجيل الدفعة", type="primary")
        if sv_pay:
            ok, msg = db.payment_add(acct_sel, pay_amt, pay_date.isoformat(), pay_type,
                pay_desc.strip(), pay_notes.strip(), st.session_state["username"],
                charge_id=pay_charge if pay_charge else None,
                handled_by=pay_handler.strip())
            if ok:
                with db.get_db() as _c:
                    _row = _c.execute("SELECT id FROM account_payments ORDER BY id DESC LIMIT 1").fetchone()
                    _lid = _row["id"] if _row else None
                track_action(f"دفعة {pay_amt:,.0f} د.ل — {db.PAYMENT_TYPES_AR[pay_type]}", "acc_payment", _lid)
                st.success(f"✅ {msg}"); st.rerun()
            else:
                st.error(f"⚠️ {msg}")

    with tab_ledger:
        # Date filter + print
        fc1, fc2, fc3 = st.columns([2,2,2])
        use_filter = fc1.checkbox("تصفية بالتاريخ", key="led_use_filter")
        df_from = df_to = None
        if use_filter:
            df_from = fc2.date_input("من تاريخ", value=today.replace(day=1), key="led_from").isoformat()
            df_to   = fc3.date_input("إلى تاريخ", value=today, key="led_to").isoformat()

        ledger = db.account_ledger(acct_sel, date_from=df_from, date_to=df_to)

        # Print PDF button
        cur_acct_obj = next((a for a in accts if a["id"]==acct_sel), None)
        if st.button("🖨️ طباعة كشف الحساب (PDF)", key="print_stmt", use_container_width=False):
            try:
                from account_pdf import generate_account_statement_pdf
                pdf_path = generate_account_statement_pdf(cur_acct_obj, ledger, bal, df_from, df_to)
                with open(pdf_path, "rb") as f:
                    st.download_button("⬇️ تحميل كشف الحساب PDF", data=f.read(),
                        file_name=pdf_path.name, mime="application/pdf",
                        key="dl_stmt_pdf", use_container_width=True)
            except Exception as e:
                st.error(f"⚠️ فشل توليد PDF: {e}")

        st.markdown("")
        if ledger:
            rows_html = ""
            for l in ledger:
                if l["tx_type"] == "charge":
                    ref_str = f" ({l['ref']})" if l.get('ref') else ""
                    icon, label, color = "📥", f"مستحق{ref_str}", "#c0392b"
                    amt_str = f"+{l['debit']:,.0f}"
                else:
                    pay_for = f" · عن {l['paid_for_ref']}" if l.get('paid_for_ref') else ""
                    handler = f" · بواسطة {l['handled_by']}" if l.get('handled_by') else ""
                    icon, label, color = "💰", f"دفعة ({db.PAYMENT_TYPES_AR.get(l['ref'], l['ref'])}){pay_for}{handler}", "#27ae60"
                    amt_str = f"-{l['credit']:,.0f}"
                bal_color = "#c0392b" if l["running_balance"] > 0 else "#C49A2A"
                rows_html += f"""<tr>
                    <td style="color:#555;">{l['tx_date']}</td>
                    <td style="font-weight:700;color:#1B2A47;">{icon} {label}</td>
                    <td style="color:#777;">{l.get('description','') or '—'}</td>
                    <td style="font-weight:700;color:{color};text-align:right;">{amt_str} د.ل</td>
                    <td style="font-weight:900;color:{bal_color};text-align:right;">{l['running_balance']:,.0f} د.ل</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">العملية</th>
                    <th style="padding:10px 14px;text-align:right;">الوصف</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">الرصيد بعد العملية</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
        else:
            st.info("لا توجد حركات مسجلة بعد.")

    with tab_list:
        charges = db.charges_with_status(acct_sel)
        if charges:
            STATUS_AR = {"paid": "✅ مدفوع بالكامل", "partial": "🟡 مدفوع جزئياً", "unpaid": "🔴 غير مدفوع"}
            STATUS_COLOR = {"paid": "#27ae60", "partial": "#f39c12", "unpaid": "#c0392b"}
            rows_html = ""
            for c in charges:
                st_label = STATUS_AR.get(c["status"], c["status"])
                st_color = STATUS_COLOR.get(c["status"], "#8a97a8")
                rows_html += f"""<tr>
                    <td style="color:#555;">{c.get('reference','') or '—'}</td>
                    <td style="font-weight:700;color:#1B2A47;">{c['description']}</td>
                    <td style="color:#555;">{c['charge_date']}</td>
                    <td style="font-weight:700;color:#1B2A47;">{c['amount']:,.0f} د.ل</td>
                    <td style="color:#27ae60;">{c['paid_amount']:,.0f} د.ل</td>
                    <td style="color:#c0392b;">{c['remaining_amount']:,.0f} د.ل</td>
                    <td style="text-align:center;"><span style="background:{st_color};color:white;padding:3px 10px;border-radius:10px;font-size:11px;font-weight:700;">{st_label}</span></td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:13px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 12px;text-align:right;">مرجع</th>
                    <th style="padding:10px 12px;text-align:right;">الوصف</th>
                    <th style="padding:10px 12px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 12px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 12px;text-align:right;">المدفوع</th>
                    <th style="padding:10px 12px;text-align:right;">المتبقي</th>
                    <th style="padding:10px 12px;text-align:center;">الحالة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)

            if can("all"):
                st.markdown("---")
                st.markdown("#### 🗑️ حذف مستحق")
                c1, c2 = st.columns([3,1])
                to_del = c1.selectbox("اختر المستحق",
                    [c["id"] for c in charges],
                    format_func=lambda x: next((f"{c['description'][:40]} — {c['amount']:,.0f} د.ل" for c in charges if c["id"]==x),""))
                if c2.button("🗑️ حذف", type="primary"):
                    ok, msg = db.charge_delete(to_del)
                    if ok: st.success(f"✅ {msg}"); st.rerun()
                    else: st.error(f"⚠️ {msg}")
        else:
            st.info("لا توجد مستحقات مسجلة بعد.")

    with tab_accts:
        st.markdown("#### ➕ إضافة حساب جديد")
        with st.form("add_acct_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ac_name = st.text_input("اسم الحساب *", placeholder="الاسم الكامل")
            with c2:
                ac_phone = st.text_input("رقم الهاتف", placeholder="09xxxxxxxx")
            ac_notes = st.text_input("ملاحظات", placeholder="نوع الحساب / أي تفاصيل...")
            if st.form_submit_button("➕ إضافة الحساب", type="primary"):
                ok, msg = db.account_add(ac_name, ac_phone, ac_notes)
                if ok: st.success(f"✅ {msg}"); st.rerun()
                else: st.error(f"⚠️ {msg}")

        st.markdown("---")
        st.markdown("#### 📋 قائمة الحسابات")
        all_accts = db.account_list()
        rows_html = ""
        for a in all_accts:
            ab = db.account_balance(a["id"])
            bal_color = "#c0392b" if ab["balance"] > 0 else "#C49A2A"
            rows_html += f"""<tr>
                <td style="font-weight:700;color:#1B2A47;">{a['name']}</td>
                <td style="color:#555;">{a.get('phone','') or '—'}</td>
                <td style="color:#777;">{a.get('notes','') or '—'}</td>
                <td style="font-weight:700;color:{bal_color};text-align:right;">{ab['balance']:,.0f} د.ل</td>
            </tr>"""
        st.markdown(f"""
        <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
            <thead><tr style="background:#1B2A47;color:white;">
                <th style="padding:10px 14px;text-align:right;">الاسم</th>
                <th style="padding:10px 14px;text-align:right;">الهاتف</th>
                <th style="padding:10px 14px;text-align:right;">ملاحظات</th>
                <th style="padding:10px 14px;text-align:right;">الرصيد</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
        table tbody tr:hover{{background:#edf2f7;}}
        table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
        """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("#### ✏️ تعديل حساب")
        edit_id = st.selectbox("اختر الحساب للتعديل", [a["id"] for a in all_accts],
            format_func=lambda x: next((a["name"] for a in all_accts if a["id"]==x), ""),
            key="edit_acct_pick")
        cur_acct = next((a for a in all_accts if a["id"]==edit_id), None)
        if cur_acct:
            with st.form("edit_acct_form"):
                c1, c2 = st.columns(2)
                with c1:
                    ed_name = st.text_input("الاسم *", value=cur_acct["name"])
                with c2:
                    ed_phone = st.text_input("الهاتف", value=cur_acct.get("phone","") or "")
                ed_notes = st.text_input("ملاحظات", value=cur_acct.get("notes","") or "")
                c3, c4 = st.columns(2)
                save_ed = c3.form_submit_button("💾 حفظ التعديل", type="primary", use_container_width=True)
                deact = c4.form_submit_button("🚫 إخفاء الحساب", use_container_width=True)
            if save_ed:
                ok, msg = db.account_edit(edit_id, ed_name, ed_phone, ed_notes)
                if ok: st.success(f"✅ {msg}"); st.rerun()
                else: st.error(f"⚠️ {msg}")
            if deact:
                if len(all_accts) <= 1:
                    st.error("⚠️ لا يمكن إخفاء الحساب الوحيد — أضف حساباً آخر أولاً.")
                else:
                    ok, msg = db.account_deactivate(edit_id)
                    if ok: st.success(f"✅ {msg}"); st.rerun()
                    else: st.error(f"⚠️ {msg}")

# ══════════════════════════════════════════════════════════════════
# عهدة الفروع (Branch Custody / Petty Cash)
# ══════════════════════════════════════════════════════════════════
elif page == "📦 عهدة الفروع":
    require("all")
    st.markdown('<div class="sh">📦 عهدة الفروع الشهرية</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 مبلغ نقدي مُخصص لكل فرع شهرياً لتغطية المصروفات اليومية (نظافة، قرطاسية، وقود...). المتبقي في نهاية الشهر يُرحّل تلقائياً للشهر التالي.</div>', unsafe_allow_html=True)
    st.markdown("")

    tab_view, tab_assign, tab_summary = st.tabs(["📋 عرض العهدة والمصروفات", "➕ تخصيص / إضافة مبلغ", "📊 ملخص كل الفروع"])

    with tab_view:
        c1, c2, c3 = st.columns(3)
        bc_branch = c1.selectbox("الفرع", list(db.BRANCH_NAMES.keys()),
            format_func=lambda x: db.BRANCH_NAMES[x], key="bc_branch")
        bc_yr = c2.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="bc_yr")
        bc_mo = c3.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="bc_mo")
        mk_bc = f"{bc_yr:04d}-{bc_mo:02d}"

        cust = db.branch_custody_get(bc_branch, mk_bc)

        if not cust:
            st.markdown(f'<div class="warn">⚠️ لا توجد عهدة مُخصصة لـ <b>{db.BRANCH_NAMES[bc_branch]}</b> في {MONTH_AR[bc_mo]} {bc_yr}. أضف تخصيص من تبويب "➕ تخصيص / إضافة مبلغ".</div>', unsafe_allow_html=True)
        else:
            # Balance cards
            st.markdown(f"""
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;font-family:'Cairo',sans-serif;direction:rtl;margin:12px 0;">
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #1B2A47;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">💰 التخصيص الشهري</div>
                    <div style="font-size:20px;font-weight:900;color:#1B2A47;">{cust['allocated_amount']:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #f39c12;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">🔄 مُرحّل من الشهر السابق</div>
                    <div style="font-size:20px;font-weight:900;color:#f39c12;">{cust['carry_from_previous']:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
                <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:14px;border-top:4px solid #c0392b;">
                    <div style="font-size:12px;color:#8a97a8;font-weight:600;">💸 المصروف ({cust['expense_count']} عملية)</div>
                    <div style="font-size:20px;font-weight:900;color:#c0392b;">{cust['spent']:,.0f}<span style="font-size:12px;color:#aaa;"> د.ل</span></div>
                </div>
                <div style="background:linear-gradient(135deg,#1B2A47,#2c3e6b);border-radius:12px;padding:14px;">
                    <div style="font-size:12px;color:#8AB0CC;font-weight:600;">✅ المتبقي</div>
                    <div style="font-size:22px;font-weight:900;color:#C49A2A;">{cust['remaining']:,.0f}<span style="font-size:12px;color:#8AB0CC;"> د.ل</span></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Status badge + close/reopen buttons + monthly print
            is_closed = (cust.get("status") == "closed")
            status_html = ('<span style="background:#c0392b;color:white;padding:4px 12px;border-radius:10px;font-weight:700;">🔒 مُقفل</span>'
                           if is_closed else
                           '<span style="background:#27ae60;color:white;padding:4px 12px;border-radius:10px;font-weight:700;">✅ مفتوح</span>')
            st.markdown(f'<div style="margin:8px 0 12px 0;">حالة العهدة: {status_html}</div>', unsafe_allow_html=True)

            action_c1, action_c2, action_c3 = st.columns([1,1,2])
            if not is_closed:
                if action_c1.button("🔒 إقفال الشهر", type="primary", use_container_width=True, key="btn_close_cust"):
                    if st.session_state.get("_confirm_close") == mk_bc:
                        ok, msg = db.branch_custody_close_month(bc_branch, mk_bc, st.session_state["username"])
                        if ok:
                            st.session_state.pop("_confirm_close", None)
                            st.toast(f"✅ {msg}", icon="✅")
                            st.rerun()
                        else:
                            st.error(f"⚠️ {msg}")
                    else:
                        st.session_state["_confirm_close"] = mk_bc
                        st.warning("⚠️ اضغط مرة أخرى للتأكيد. سيتم إقفال هذا الشهر وترحيل المتبقي تلقائياً للشهر التالي.")
            else:
                if can("all") and action_c1.button("🔓 إعادة فتح الشهر", use_container_width=True, key="btn_reopen_cust"):
                    ok, msg = db.branch_custody_reopen_month(bc_branch, mk_bc, st.session_state["username"])
                    if ok: st.toast(f"✅ {msg}", icon="✅"); st.rerun()
                    else: st.error(f"⚠️ {msg}")

            # Monthly PDF print
            if action_c2.button("🖨️ طباعة كشف الشهر (PDF)", use_container_width=True, key="btn_print_month"):
                try:
                    from custody_pdf import generate_custody_monthly_pdf
                    exps_pdf = db.branch_custody_expense_list(bc_branch, mk_bc)
                    pdf_path = generate_custody_monthly_pdf(cust, exps_pdf, db.BRANCH_NAMES[bc_branch], mk_bc)
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            "⬇️ تحميل ملف PDF",
                            data=f.read(),
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            key="dl_month_pdf",
                            use_container_width=True,
                        )
                except Exception as e:
                    st.error(f"⚠️ فشل توليد PDF: {e}")

            st.markdown("---")

            # Add expense form (disabled if closed)
            if is_closed:
                st.markdown('<div class="warn">🔒 العهدة مُقفلة — لا يمكن تسجيل مصروفات جديدة. لإعادة الفتح استخدم الزر أعلاه (أدمن فقط).</div>', unsafe_allow_html=True)
            else:
                st.markdown("#### ➕ تسجيل مصروف")
                saved_reasons = db.branch_custody_reason_list()
                OTHER_OPT = "➕ أخرى — أضف سبباً جديداً"
                reason_options = saved_reasons + [OTHER_OPT] if saved_reasons else [OTHER_OPT]

                picked_reason = st.selectbox("السبب *",
                    reason_options, key="bc_reason_pick",
                    help="اختر من الأسباب السابقة، أو ✚ أخرى لإضافة سبب جديد")
                new_reason = ""
                if picked_reason == OTHER_OPT:
                    new_reason = st.text_input("السبب الجديد *",
                        placeholder="اكتب السبب — سيُحفظ للمرات القادمة",
                        key="bc_new_reason")

                with st.form("bc_exp_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        exp_amt = st.number_input("المبلغ (د.ل) *", min_value=1.0, step=10.0)
                    with c2:
                        exp_date = st.date_input("تاريخ المصروف", value=today)
                    st.markdown(f'<div style="padding:8px 12px;background:#f8fafc;border-radius:8px;border:1px solid #e2e8f0;color:#1B2A47;font-weight:600;">📝 {new_reason or (picked_reason if picked_reason != OTHER_OPT else "—")}</div>', unsafe_allow_html=True)
                    sv_exp = st.form_submit_button("💸 تسجيل المصروف", type="primary")
                if sv_exp:
                    final_reason = new_reason.strip() if picked_reason == OTHER_OPT else picked_reason
                    if not final_reason:
                        st.error("⚠️ اكتب السبب الجديد قبل التسجيل")
                    elif exp_amt > cust["remaining"]:
                        st.error(f"⚠️ المبلغ ({exp_amt:,.0f} د.ل) أكبر من الرصيد المتبقي ({cust['remaining']:,.0f} د.ل)")
                    else:
                        ok, msg = db.branch_custody_expense_add(bc_branch, mk_bc, exp_amt,
                            final_reason, "", exp_date.isoformat(), st.session_state["username"])
                        if ok:
                            with db.get_db() as _c:
                                _row = _c.execute("SELECT id FROM branch_custody_expenses ORDER BY id DESC LIMIT 1").fetchone()
                                _lid = _row["id"] if _row else None
                            track_action(f"مصروف عهدة {exp_amt:,.0f} د.ل — {final_reason}", "custody_expense", _lid)
                            st.success(f"✅ {msg}"); st.rerun()
                        else:
                            st.error(f"⚠️ {msg}")

            # Expenses table
            st.markdown("")
            st.markdown("#### 📋 سجل المصروفات")
            exps = db.branch_custody_expense_list(bc_branch, mk_bc)
            if exps:
                rows_html = ""
                for e in exps:
                    rows_html += f"""<tr>
                        <td style="color:#555;">{e['expense_date']}</td>
                        <td style="font-weight:700;color:#1B2A47;">{e['description']}</td>
                        <td style="font-weight:700;color:#c0392b;text-align:right;">{e['amount']:,.0f} د.ل</td>
                        <td style="color:#555;font-size:12px;">{e.get('logged_by','—')}</td>
                    </tr>"""
                st.markdown(f"""
                <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
                    <thead><tr style="background:#1B2A47;color:white;">
                        <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                        <th style="padding:10px 14px;text-align:right;">السبب</th>
                        <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                        <th style="padding:10px 14px;text-align:right;">بواسطة</th>
                    </tr></thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
                table tbody tr:hover{{background:#edf2f7;}}
                table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
                """, unsafe_allow_html=True)

                # Per-expense PDF receipt
                st.markdown("---")
                st.markdown("#### 🖨️ طباعة سند صرف")
                pc1, pc2 = st.columns([3,1])
                to_print = pc1.selectbox("اختر مصروف لطباعة سند صرف",
                    [e["id"] for e in exps],
                    format_func=lambda x: next((f"{e['expense_date']} — {e['description'][:40]} ({e['amount']:,.0f} د.ل)" for e in exps if e["id"]==x),""),
                    key="bc_print_pick")
                if pc2.button("🖨️ توليد سند", use_container_width=True, key="btn_print_receipt"):
                    try:
                        from custody_pdf import generate_expense_receipt_pdf
                        picked = next((e for e in exps if e["id"] == to_print), None)
                        pdf_path = generate_expense_receipt_pdf(picked, db.BRANCH_NAMES[bc_branch], mk_bc)
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "⬇️ تحميل سند الصرف",
                                data=f.read(),
                                file_name=pdf_path.name,
                                mime="application/pdf",
                                key="dl_receipt_pdf",
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(f"⚠️ فشل توليد PDF: {e}")

                # Delete button
                st.markdown("---")
                st.markdown("#### 🗑️ حذف مصروف")
                c1, c2 = st.columns([3,1])
                to_del = c1.selectbox("اختر المصروف",
                    [e["id"] for e in exps],
                    format_func=lambda x: next((f"{e['expense_date']} — {e['description']} ({e['amount']:,.0f} د.ل)" for e in exps if e["id"]==x),""),
                    key="bc_del_pick")
                if c2.button("🗑️ حذف", type="primary"):
                    ok, msg = db.branch_custody_expense_delete(to_del)
                    if ok: st.success(f"✅ {msg}"); st.rerun()
                    else: st.error(f"⚠️ {msg}")
            else:
                st.info("لا توجد مصروفات مسجلة بعد.")

    with tab_assign:
        st.markdown("#### ➕ تخصيص أو إضافة عهدة للفرع")
        st.caption("عند التخصيص الأول للشهر، تُضاف تلقائياً المُرحّلات من الشهر السابق.")

        with st.form("bc_assign_form"):
            c1, c2, c3 = st.columns(3)
            asg_branch = c1.selectbox("الفرع *", list(db.BRANCH_NAMES.keys()),
                format_func=lambda x: db.BRANCH_NAMES[x], key="asg_branch")
            asg_yr = c2.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="asg_yr")
            asg_mo = c3.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="asg_mo")
            asg_amt = st.number_input("مبلغ العهدة (د.ل) *", min_value=1.0, step=100.0)
            asg_notes = st.text_input("ملاحظات", placeholder="سبب / تفاصيل التخصيص...")
            sv_asg = st.form_submit_button("📦 تخصيص العهدة", type="primary")
        if sv_asg:
            mk_asg = f"{asg_yr:04d}-{asg_mo:02d}"
            ok, msg = db.branch_custody_assign(asg_branch, mk_asg, asg_amt,
                asg_notes.strip(), st.session_state["username"])
            if ok:
                st.success(f"✅ {msg}"); st.rerun()
            else:
                st.error(f"⚠️ {msg}")

    with tab_summary:
        c1, c2 = st.columns(2)
        sum_yr = c1.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="bcsum_yr")
        sum_mo = c2.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="bcsum_mo")
        mk_sum = f"{sum_yr:04d}-{sum_mo:02d}"
        summary = db.branch_custody_summary(mk_sum)
        if summary:
            rows_html = ""
            total_alloc = 0; total_carry = 0; total_spent = 0; total_rem = 0
            for s in summary:
                total_alloc += s["allocated"]; total_carry += s["carry_from_previous"]
                total_spent += s["spent"];    total_rem += s["remaining"]
                pct = round(s["spent"] / s["total_available"] * 100, 1) if s["total_available"] > 0 else 0
                bar_color = "#c0392b" if pct >= 90 else "#f39c12" if pct >= 50 else "#27ae60"
                rows_html += f"""<tr>
                    <td style="font-weight:700;color:#1B2A47;">{s['branch_name']}</td>
                    <td style="text-align:right;color:#1B2A47;">{s['allocated']:,.0f} د.ل</td>
                    <td style="text-align:right;color:#f39c12;">{s['carry_from_previous']:,.0f} د.ل</td>
                    <td style="text-align:right;font-weight:600;">{s['total_available']:,.0f} د.ل</td>
                    <td style="text-align:right;color:#c0392b;">{s['spent']:,.0f} د.ل ({s['expense_count']})</td>
                    <td style="text-align:right;font-weight:700;color:#27ae60;">{s['remaining']:,.0f} د.ل</td>
                    <td style="text-align:center;"><span style="background:{bar_color};color:white;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700;">{pct}%</span></td>
                </tr>"""
            rows_html += f"""<tr style="background:#1B2A47;">
                <td style="font-weight:900;color:white;padding:14px 16px;">🏁 الإجمالي</td>
                <td style="color:#C49A2A;text-align:right;font-weight:900;padding:14px 16px;">{total_alloc:,.0f} د.ل</td>
                <td style="color:#C49A2A;text-align:right;font-weight:900;padding:14px 16px;">{total_carry:,.0f} د.ل</td>
                <td style="color:#C49A2A;text-align:right;font-weight:900;padding:14px 16px;">{(total_alloc+total_carry):,.0f} د.ل</td>
                <td style="color:#C49A2A;text-align:right;font-weight:900;padding:14px 16px;">{total_spent:,.0f} د.ل</td>
                <td style="color:#C49A2A;text-align:right;font-weight:900;padding:14px 16px;">{total_rem:,.0f} د.ل</td>
                <td></td>
            </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:13px;margin-top:8px;">
                <thead><tr style="background:#2c3e6b;color:white;">
                    <th style="padding:10px 12px;text-align:right;">الفرع</th>
                    <th style="padding:10px 12px;text-align:right;">التخصيص</th>
                    <th style="padding:10px 12px;text-align:right;">مُرحّل</th>
                    <th style="padding:10px 12px;text-align:right;">المتاح</th>
                    <th style="padding:10px 12px;text-align:right;">المصروف</th>
                    <th style="padding:10px 12px;text-align:right;">المتبقي</th>
                    <th style="padding:10px 12px;text-align:center;">نسبة الصرف</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even):not(:last-child){{background:#f8fafc;}}
            table tbody tr:hover:not(:last-child){{background:#edf2f7;}}
            table tbody td{{padding:10px 12px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
        else:
            st.info(f"لا توجد عهدة مخصصة لأي فرع في {MONTH_AR[sum_mo]} {sum_yr}.")

# ══════════════════════════════════════════════════════════════════
# مصروفات الشركة (Company Expenses)
# ══════════════════════════════════════════════════════════════════
elif page == "📒 مصروفات الشركة":
    require("all")
    st.markdown('<div class="sh">📒 مصروفات الشركة الشهرية</div>', unsafe_allow_html=True)
    st.markdown('<div class="inf">💡 لتسجيل المصروفات التشغيلية للشركة: وجبات، إيجار، كهرباء، صيانة...</div>', unsafe_allow_html=True)
    st.markdown("")

    tab_add, tab_list, tab_summary = st.tabs(["➕ مصروف جديد", "📋 السجل الشهري", "📊 ملخص سنوي"])

    with tab_add:
        with st.form("exp_form"):
            c1, c2 = st.columns(2)
            with c1:
                exp_cat = st.selectbox("التصنيف *", db.EXPENSE_CATEGORIES)
                exp_amt = st.number_input("المبلغ (د.ل) *", min_value=1.0, step=50.0)
                exp_branch = st.selectbox("الفرع",
                    [""] + list(db.BRANCH_NAMES.keys()),
                    format_func=lambda x: "🏢 عام (كل الشركة)" if x == "" else db.BRANCH_NAMES[x])
            with c2:
                exp_date = st.date_input("التاريخ", value=today)
                exp_desc = st.text_input("ملاحظات", placeholder="تفاصيل إضافية...")
            sv_exp = st.form_submit_button("📒 تسجيل المصروف", type="primary")
        if sv_exp:
            mk = exp_date.strftime("%Y-%m")
            ok, msg = db.expense_add(exp_cat, exp_amt, exp_date.isoformat(), mk,
                exp_desc.strip(), st.session_state["username"],
                branch_id=exp_branch if exp_branch else None)
            if ok:
                with db.get_db() as _c:
                    _row = _c.execute("SELECT id FROM company_expenses ORDER BY id DESC LIMIT 1").fetchone()
                    _lid = _row["id"] if _row else None
                b_label = f" — {db.BRANCH_NAMES.get(exp_branch, exp_branch)}" if exp_branch else " — عام"
                track_action(f"مصروف شركة {exp_amt:,.0f} د.ل — {exp_cat}{b_label}", "expense", _lid)
                st.success(f"✅ {msg}")
                st.rerun()
            else:
                st.error(f"⚠️ {msg}")

    with tab_list:
        c1, c2, c3 = st.columns(3)
        exp_yr = c1.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="exp_yr")
        exp_mo = c2.selectbox("الشهر", list(range(1,13)), format_func=lambda m: MONTH_AR[m], index=today.month-1, key="exp_mo")
        exp_bfilter = c3.selectbox("الفرع",
            ["all", ""] + list(db.BRANCH_NAMES.keys()),
            format_func=lambda x: "الكل" if x=="all" else ("🏢 عام" if x=="" else db.BRANCH_NAMES[x]),
            key="exp_bfilter")
        mk = f"{exp_yr:04d}-{exp_mo:02d}"
        if exp_bfilter == "all":
            expenses = db.expense_list(month_key=mk)
        elif exp_bfilter == "":
            expenses = [e for e in db.expense_list(month_key=mk) if not e.get("branch_id")]
        else:
            expenses = db.expense_list(month_key=mk, branch_id=exp_bfilter)

        if expenses:
            rows_html = ""
            total_exp = 0
            for e in expenses:
                total_exp += e["amount"]
                bid = e.get("branch_id")
                b_label = db.BRANCH_NAMES.get(bid, "🏢 عام") if bid else "🏢 عام"
                b_color = "#2980b9" if bid else "#8a97a8"
                rows_html += f"""<tr>
                    <td style="font-weight:600;color:#1B2A47;"><span style="background:#8e44ad;color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{e['category']}</span></td>
                    <td><span style="background:{b_color};color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{b_label}</span></td>
                    <td style="font-weight:700;color:#c0392b;">{e['amount']:,.0f} د.ل</td>
                    <td style="color:#555;">{e['expense_date']}</td>
                    <td style="color:#555;">{e.get('description','') or '—'}</td>
                    <td style="color:#555;font-size:12px;">{e.get('logged_by','') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">التصنيف</th>
                    <th style="padding:10px 14px;text-align:right;">الفرع</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">ملاحظات</th>
                    <th style="padding:10px 14px;text-align:right;">بواسطة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            st.metric(f"إجمالي مصروفات {MONTH_AR[exp_mo]} {exp_yr}", f"{total_exp:,.0f} د.ل")
        else:
            st.info(f"لا توجد مصروفات لشهر {MONTH_AR[exp_mo]} {exp_yr}.")

    with tab_summary:
        sum_yr = st.selectbox("السنة", list(range(2022, today.year+2)), index=today.year-2022, key="expsum_yr")
        totals = db.expense_yearly_totals(sum_yr)
        if totals:
            rows_html = ""
            grand = 0
            for t in totals:
                grand += t["total"]
                rows_html += f"""<tr>
                    <td style="font-weight:600;color:#1B2A47;"><span style="background:#8e44ad;color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{t['category']}</span></td>
                    <td style="text-align:center;">{t['tx_count']}</td>
                    <td style="font-weight:700;color:#c0392b;">{t['total']:,.0f} د.ل</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">التصنيف</th>
                    <th style="padding:10px 14px;text-align:center;">عدد العمليات</th>
                    <th style="padding:10px 14px;text-align:right;">الإجمالي</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            st.metric(f"إجمالي مصروفات {sum_yr}", f"{grand:,.0f} د.ل")

            # Monthly breakdown
            monthly = db.expense_monthly_summary(sum_yr)
            if monthly:
                st.markdown("---")
                st.markdown("#### 📅 التفصيل الشهري")
                # Group by month
                by_month = {}
                for m in monthly:
                    mk = m["month_key"]
                    if mk not in by_month:
                        by_month[mk] = []
                    by_month[mk].append(m)
                for mk in sorted(by_month.keys(), reverse=True):
                    yr_m, mo_m = int(mk[:4]), int(mk[5:7])
                    month_total = sum(m["total"] for m in by_month[mk])
                    st.markdown(f"**{MONTH_AR[mo_m]} {yr_m}** — {month_total:,.0f} د.ل")
                    for m in by_month[mk]:
                        st.markdown(f"- {m['category']}: **{m['total']:,.0f} د.ل** ({m['tx_count']} عملية)")
        else:
            st.info(f"لا توجد مصروفات في {sum_yr}.")

# ══════════════════════════════════════════════════════════════════
# إدارة المستخدمين (admin فقط)
# ══════════════════════════════════════════════════════════════════

elif page == "👑 إدارة المستخدمين":
    require("all")
    st.markdown('<div class="sh">👑 إدارة المستخدمين والصلاحيات</div>', unsafe_allow_html=True)

    # Initialize view state
    usr_nav_options = ["📋 المستخدمون الحاليون", "➕ مستخدم جديد"]
    if "_usr_view" not in st.session_state or st.session_state["_usr_view"] not in usr_nav_options:
        st.session_state["_usr_view"] = usr_nav_options[0]

    chosen_usr = st.radio("", usr_nav_options, horizontal=True,
                          label_visibility="hidden", key="_usr_view")
    st.markdown("---")

    if chosen_usr == "📋 المستخدمون الحاليون":
        # Show persistent feedback from previous delete/add action
        if st.session_state.get("_user_del_msg"):
            ok_flag, del_msg = st.session_state.pop("_user_del_msg")
            if ok_flag: st.success(f"✅ {del_msg}")
            else:       st.error(f"⚠️ {del_msg}")

        users=db.get_all_users()
        if users:
            # Resolve current user id — fallback to DB lookup if not in session
            current_uid = st.session_state.get("user_id")
            if not current_uid:
                with db.get_db() as _conn:
                    _row = _conn.execute("SELECT id FROM users WHERE username=?",
                                         (st.session_state["username"],)).fetchone()
                    current_uid = _row["id"] if _row else None
                st.session_state["user_id"] = current_uid

            admin_count = sum(1 for x in users if x["role"]=="admin")
            for u in users:
                role_label  = ROLE_AR.get(u["role"], u["role"])
                active_label= "✅ نشط" if u["is_active"] else "🔴 غير نشط"
                last_login  = (u.get("last_login","") or "—")[:16]
                col_info, col_del = st.columns([5, 1])
                with col_info:
                    accent = '#1B2A47' if u['role']=='admin' else '#27ae60' if u['role']=='hr' else '#8a97a8'
                    st.markdown(f"""
                    <div style="background:#f8fafc;border:1px solid #d0d8e4;border-right:4px solid {accent};
                        border-radius:8px;padding:10px 16px;font-family:'Cairo',sans-serif;direction:rtl;">
                        <span style="font-weight:700;font-size:15px;">{u['display_name']}</span>
                        <code style="background:#e2e8f0;padding:1px 8px;border-radius:4px;font-size:12px;margin-right:8px;">{u['username']}</code>
                        <span style="background:{accent};color:white;padding:2px 10px;border-radius:10px;font-size:11px;font-weight:700;">{role_label}</span>
                        <span style="color:#777;font-size:12px;margin-right:12px;">{active_label} · آخر دخول: {last_login}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with col_del:
                    is_self       = (u["id"] == current_uid)
                    is_last_admin = (u["role"]=="admin" and admin_count <= 1)
                    if not is_self and not is_last_admin:
                        if st.button("🗑️ حذف", key=f"del_user_{u['id']}", type="primary"):
                            _confirm_del_user(u["id"], u["username"], current_uid, st.session_state["username"])
                    else:
                        reason = "حسابك" if is_self else "آخر admin"
                        st.markdown(f'<div style="color:#aaa;font-size:12px;padding:8px 0;">🔒 {reason}</div>', unsafe_allow_html=True)
                st.markdown("")

    elif chosen_usr == "➕ مستخدم جديد":
        with st.form("new_user"):
            c1,c2=st.columns(2)
            nu=c1.text_input("اسم المستخدم *")
            nd=c1.text_input("الاسم المعروض *")
            np1=c2.text_input("كلمة المرور *",type="password")
            np2=c2.text_input("تأكيد كلمة المرور *",type="password")
            nr=c1.selectbox("الدور",["hr","viewer","admin"],format_func=lambda x:ROLE_AR[x])
            sv_u=st.form_submit_button("✅ إنشاء المستخدم",type="primary")
        if sv_u:
            if not nu.strip() or not nd.strip(): st.error("جميع الحقول مطلوبة")
            elif np1!=np2: st.error("كلمتا المرور غير متطابقتين")
            else:
                ok,msg=db.create_user(nu.strip(),nd.strip(),np1,nr,None,st.session_state["username"])
                if ok:
                    st.session_state["_user_del_msg"] = (True, msg)
                    st.session_state["_usr_view"] = "📋 المستخدمون الحاليون"
                    st.rerun()
                else:
                    st.error(f"⚠️ {msg}")

# ══════════════════════════════════════════════════════════════════
# السحوبات الشخصية
# ══════════════════════════════════════════════════════════════════
elif page == "💼 السحوبات الشخصية":
    require("all")
    st.markdown('<div class="sh">💼 السحوبات الشخصية</div>', unsafe_allow_html=True)

    partners = db.partner_list()
    tab_log, tab_history, tab_report = st.tabs(["➕ تسجيل سحب", "📋 السجل الكامل", "📊 التقارير"])

    # ── تسجيل سحب ──────────────────────────────────────────────
    with tab_log:
        st.subheader("تسجيل سحب جديد")

        # Show result message from confirmation dialog
        if st.session_state.get("_wd_msg"):
            ok_f, wd_msg = st.session_state.pop("_wd_msg")
            if ok_f: st.success(f"✅ {wd_msg}")
            else:    st.error(f"⚠️ {wd_msg}")

        active_partners = [p for p in partners if p["is_active"]]
        c1, c2 = st.columns(2)
        with c1:
            sel_partner = st.selectbox(
                "الشخص *",
                [p["id"] for p in active_partners],
                format_func=lambda x: next((p["name"] for p in active_partners if p["id"]==x), ""),
                key="wd_partner"
            )
            amount = st.number_input("المبلغ (د.ل) *", min_value=0.0, step=50.0, key="wd_amount")
        with c2:
            w_date = st.date_input("التاريخ *", value=today, key="wd_date")
            desc   = st.text_input("الوصف", placeholder="مثال: مصاريف شخصية، سحب نقدي", key="wd_desc")

        # Unsaved warning — show if amount has been entered but not saved
        form_touched = amount > 0 or bool(st.session_state.get("wd_desc","").strip())
        if form_touched:
            st.markdown('<div class="warn">⚠️ لديك بيانات غير محفوظة — لا تنسَ الضغط على زر التسجيل قبل مغادرة هذه الصفحة.</div>', unsafe_allow_html=True)
            st.markdown("")

        if st.button("✅ تسجيل السحب", type="primary", use_container_width=True, key="wd_submit"):
            if amount <= 0:
                st.error("⚠️ الرجاء إدخال مبلغ صحيح أكبر من صفر.")
            else:
                partner_name = next((p["name"] for p in active_partners if p["id"]==sel_partner), "")
                _confirm_withdrawal(partner_name, amount, w_date.isoformat(),
                                    desc, sel_partner, st.session_state["username"])

    # ── السجل الكامل ────────────────────────────────────────────
    with tab_history:
        st.subheader("سجل جميع السحوبات")
        if st.session_state.get("_wd_msg"):
            ok_f, wd_msg = st.session_state.pop("_wd_msg")
            if ok_f: st.success(f"✅ {wd_msg}")
            else:    st.error(f"⚠️ {wd_msg}")
        fc1, fc2, fc3 = st.columns(3)
        f_partner = fc1.selectbox("الشخص", ["الكل"] + [p["id"] for p in partners],
                                  format_func=lambda x: "الجميع" if x=="الكل" else next((p["name"] for p in partners if p["id"]==x),""),
                                  key="f_partner")
        f_year  = fc2.selectbox("السنة", list(range(2024, today.year+2)), index=today.year-2024, key="f_year")
        f_month = fc3.selectbox("الشهر", ["الكل"]+list(range(1,13)),
                                format_func=lambda x: "كل الأشهر" if x=="الكل" else MONTH_AR[x],
                                key="f_month")

        recs = db.withdrawal_get(
            partner_id = f_partner if f_partner != "الكل" else None,
            year       = f_year,
            month      = f_month if f_month != "الكل" else None
        )
        if recs:
            total_shown = sum(r["amount"] for r in recs)
            rows_html = ""
            for r in recs:
                rows_html += f"""<tr>
                    <td style="color:#555;">{r['w_date']}</td>
                    <td style="font-weight:700;color:#1B2A47;">{r['partner_name']}</td>
                    <td style="font-weight:700;color:#c0392b;font-size:15px;">{r['amount']:,.0f} د.ل</td>
                    <td style="color:#555;">{r.get('description','') or '—'}</td>
                    <td style="color:#8a97a8;font-size:12px;">{r.get('logged_by','') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 14px;text-align:right;">التاريخ</th>
                    <th style="padding:10px 14px;text-align:right;">الشخص</th>
                    <th style="padding:10px 14px;text-align:right;">المبلغ</th>
                    <th style="padding:10px 14px;text-align:right;">الوصف</th>
                    <th style="padding:10px 14px;text-align:right;">سُجِّل بواسطة</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:8px;font-family:'Cairo',sans-serif;">
                إجمالي المعروض: <strong style="color:#c0392b;">{total_shown:,.0f} د.ل</strong> | عدد السجلات: {len(recs)}
            </div>
            """, unsafe_allow_html=True)

            # Export buttons
            st.markdown("")
            period_lbl = f"{MONTH_AR[f_month]} {f_year}" if f_month != "الكل" else str(f_year)
            ex1, ex2 = st.columns(2)
            csv_w = "التاريخ,الشخص,المبلغ,الوصف,سُجِّل بواسطة\n"
            csv_w += "\n".join(
                f"{r['w_date']},{r['partner_name']},{r['amount']},{r.get('description','')},{r.get('logged_by','')}"
                for r in recs)
            ex1.download_button("⬇️ تصدير CSV", data=csv_w.encode("utf-8-sig"),
                                file_name=f"سحوبات_{f_year}.csv", mime="text/csv",
                                use_container_width=True)
            try:
                from withdrawals_pdf import generate_withdrawals_pdf
                pdf_bytes = generate_withdrawals_pdf(
                    records=recs,
                    title_ar="تقرير السحوبات الشخصية",
                    period_label=period_lbl,
                    logged_by=st.session_state["username"],
                )
                ex2.download_button("📄 تصدير PDF", data=pdf_bytes,
                                    file_name=f"سحوبات_{f_year}.pdf", mime="application/pdf",
                                    use_container_width=True)
            except Exception as e:
                ex2.error(f"PDF: {e}")

            # ── Edit / Delete a record ───────────────────────────
            st.markdown("---")
            st.markdown("#### ✏️ تعديل أو حذف سجل")
            sel_rec = st.selectbox(
                "اختر السجل:",
                [r["id"] for r in recs],
                format_func=lambda x: next(
                    (f"{r['w_date']} | {r['partner_name']} | {r['amount']:,.0f} د.ل"
                     for r in recs if r["id"]==x), ""),
                key="sel_wd_rec"
            )
            chosen_rec = next((r for r in recs if r["id"]==sel_rec), None)
            if chosen_rec:
                ed1, ed2 = st.columns(2)
                if ed1.button("✏️ تعديل", use_container_width=True, key="btn_edit_wd"):
                    _edit_withdrawal(chosen_rec, st.session_state["username"])
                if ed2.button("🗑️ حذف", type="primary", use_container_width=True, key="btn_del_wd"):
                    _delete_withdrawal(chosen_rec)
        else:
            st.info("لا توجد سجلات للفترة المحددة.")

    # ── التقارير ────────────────────────────────────────────────
    with tab_report:
        r_year = st.selectbox("السنة", list(range(2024, today.year+2)), index=today.year-2024, key="r_year")

        # Year-to-date cards per partner
        yearly = db.withdrawal_yearly_totals(r_year)
        if any(r["total"] for r in yearly):
            st.markdown(f"#### إجمالي سحوبات {r_year}")
            cols = st.columns(len(yearly))
            for col, r in zip(cols, yearly):
                col.metric(r["partner_name"],
                           f"{r['total']:,.0f} د.ل" if r["total"] else "0 د.ل",
                           f"{r['tx_count']} عملية")
            st.markdown("---")

        # Monthly breakdown table
        st.markdown(f"#### التفصيل الشهري — {r_year}")
        summary = db.withdrawal_summary(r_year)
        if summary:
            # Build month × partner matrix
            partner_ids   = [p["id"]   for p in partners if p["is_active"]]
            partner_names = [p["name"] for p in partners if p["is_active"]]
            # index by (partner_id, month)
            data = {(r["partner_id"], int(r["month"])): r["total"] for r in summary}

            header_cells = "".join(f'<th style="padding:10px 14px;text-align:right;font-weight:700;">{n}</th>' for n in partner_names)
            header_cells += '<th style="padding:10px 14px;text-align:right;font-weight:700;">الإجمالي</th>'

            rows_html = ""
            month_totals = {pid: 0.0 for pid in partner_ids}
            for m in range(1, 13):
                cells = ""
                row_total = 0.0
                for pid in partner_ids:
                    val = data.get((pid, m), 0) or 0
                    month_totals[pid] += val
                    row_total += val
                    color = "#c0392b" if val > 0 else "#8a97a8"
                    cells += f'<td style="font-weight:600;color:{color};">{val:,.0f} د.ل</td>'
                rt_color = "#c0392b" if row_total > 0 else "#8a97a8"
                cells += f'<td style="font-weight:700;color:{rt_color};">{row_total:,.0f} د.ل</td>'
                rows_html += f'<tr><td style="font-weight:700;color:#1B2A47;">{MONTH_AR[m]}</td>{cells}</tr>'

            # Totals row
            total_cells = ""
            grand = 0.0
            for pid in partner_ids:
                grand += month_totals[pid]
                total_cells += f'<td style="font-weight:700;color:#c0392b;">{month_totals[pid]:,.0f} د.ل</td>'
            total_cells += f'<td style="font-weight:700;color:#1B2A47;font-size:15px;">{grand:,.0f} د.ل</td>'

            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;margin-top:8px;">
                <thead>
                    <tr style="background:#1B2A47;color:white;">
                        <th style="padding:10px 14px;text-align:right;font-weight:700;">الشهر</th>
                        {header_cells}
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
                <tfoot>
                    <tr style="background:#edf2f7;font-weight:700;">
                        <td style="padding:10px 14px;color:#1B2A47;font-weight:700;">الإجمالي</td>
                        {total_cells}
                    </tr>
                </tfoot>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
            table tfoot td{{padding:10px 14px;}}</style>
            """, unsafe_allow_html=True)

            # Export buttons for yearly report
            st.markdown("")
            all_recs = db.withdrawal_get(year=r_year)
            re1, re2 = st.columns(2)
            csv_yr = "التاريخ,الشخص,المبلغ,الوصف,سُجِّل بواسطة\n"
            csv_yr += "\n".join(
                f"{r['w_date']},{r['partner_name']},{r['amount']},{r.get('description','')},{r.get('logged_by','')}"
                for r in all_recs)
            re1.download_button("⬇️ تصدير CSV (السنة كاملة)", data=csv_yr.encode("utf-8-sig"),
                                file_name=f"سحوبات_سنوي_{r_year}.csv", mime="text/csv",
                                use_container_width=True)
            try:
                from withdrawals_pdf import generate_withdrawals_pdf
                pdf_yr = generate_withdrawals_pdf(
                    records=all_recs,
                    title_ar="التقرير السنوي للسحوبات الشخصية",
                    period_label=str(r_year),
                    logged_by=st.session_state["username"],
                )
                re2.download_button("📄 تصدير PDF (السنة كاملة)", data=pdf_yr,
                                    file_name=f"سحوبات_سنوي_{r_year}.pdf", mime="application/pdf",
                                    use_container_width=True)
            except Exception as e:
                re2.error(f"PDF: {e}")

        else:
            st.info(f"لا توجد سحوبات مسجلة في {r_year}.")

        # Add partner section (admin)
        if can("admin"):
            st.markdown("---")
            st.markdown("#### ➕ إضافة شخص جديد")
            with st.form("add_partner_form"):
                new_name = st.text_input("الاسم")
                add_p = st.form_submit_button("إضافة", type="primary")
            if add_p:
                ok, msg = db.partner_add(new_name, st.session_state["username"])
                if ok: st.success(f"✅ {msg}"); st.rerun()
                else:  st.error(f"⚠️ {msg}")

elif page == "🔒 الأمان":
    st.markdown('<div class="sh">🔒 إعدادات الأمان</div>', unsafe_allow_html=True)
    tab_pw, tab_audit, tab_backup = st.tabs(["🔑 تغيير كلمة المرور", "📜 سجل التدقيق", "💾 النسخ الاحتياطي"])

    with tab_pw:
        with st.form("pw_form"):
            old=st.text_input("كلمة المرور الحالية",type="password")
            new1=st.text_input("كلمة المرور الجديدة",type="password")
            new2=st.text_input("تأكيد كلمة المرور الجديدة",type="password")
            sv_pw=st.form_submit_button("🔒 تغيير كلمة المرور",type="primary")
        if sv_pw:
            if new1!=new2: st.error("كلمتا المرور غير متطابقتين")
            else:
                ok,msg=db.change_password(st.session_state["username"],old,new1)
                if ok: st.success(f"✅ {msg}")
                else: st.error(f"⚠️ {msg}")
        st.markdown("---")
        st.subheader("بيانات الجلسة الحالية")
        st.markdown(f"""
        | | |
        |---|---|
        | المستخدم | `{st.session_state['username']}` |
        | الدور | {ROLE_AR.get(st.session_state.get('user_role',''),'—')} |
        | الجلسة | نشطة منذ بدء التشغيل |
        """)

    with tab_audit:
        st.subheader("سجل التدقيق الكامل")
        st.caption("جميع العمليات الحساسة مسجلة تلقائياً — لا يمكن حذف هذا السجل")
        log=db.get_audit_log(limit=150)
        if log:
            ACTION_COLOR = {
                "LOGIN":"#27ae60","LOGOUT":"#8a97a8","FINALIZE_PAYROLL":"#1B2A47",
                "REOPEN_PAYROLL":"#e67e22","DELETE":"#c0392b","ADD":"#2980b9",
                "UPDATE":"#f39c12","CHANGE_PASSWORD":"#8e44ad",
            }
            rows_html = ""
            for e in log:
                action = e.get("action","")
                color  = next((v for k,v in ACTION_COLOR.items() if k in action), "#555")
                rows_html += f"""<tr>
                    <td style="color:#555;font-size:12px;white-space:nowrap;">{(e.get('ts','') or '')[:16]}</td>
                    <td style="font-weight:700;color:#1B2A47;">{e.get('username','')}</td>
                    <td style="text-align:center;"><span style="background:{color};color:white;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:700;">{action}</span></td>
                    <td style="color:#555;font-size:12px;">{e.get('entity','')}</td>
                    <td style="color:#555;font-size:12px;">{e.get('detail','') or '—'}</td>
                </tr>"""
            st.markdown(f"""
            <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:13px;margin-top:8px;">
                <thead><tr style="background:#1B2A47;color:white;">
                    <th style="padding:10px 12px;text-align:right;">التوقيت</th>
                    <th style="padding:10px 12px;text-align:right;">المستخدم</th>
                    <th style="padding:10px 12px;text-align:center;">الإجراء</th>
                    <th style="padding:10px 12px;text-align:right;">النوع</th>
                    <th style="padding:10px 12px;text-align:right;">التفاصيل</th>
                </tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
            <style>table tbody tr:nth-child(even){{background:#f8fafc;}}
            table tbody tr:hover{{background:#edf2f7;}}
            table tbody td{{padding:9px 12px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}</style>
            """, unsafe_allow_html=True)
            st.markdown("")
            csv_log = "التوقيت,المستخدم,الإجراء,النوع,التفاصيل\n"
            csv_log += "\n".join(f"{(e.get('ts','') or '')[:16]},{e.get('username','')},{e.get('action','')},{e.get('entity','')},{e.get('detail','') or ''}" for e in log)
            st.download_button("⬇️ تصدير سجل التدقيق", data=csv_log.encode("utf-8-sig"),
                               file_name="سجل_التدقيق.csv", mime="text/csv")
        else: st.info("السجل فارغ.")

    with tab_backup:
        st.subheader("💾 النسخ الاحتياطي لقاعدة البيانات")
        st.markdown('<div class="inf">✅ يتم حفظ نسخة احتياطية تلقائياً عند إقفال كل مسير شهري، وكذلك مرة واحدة يومياً عند فتح البرنامج. تُحفظ آخر 30 نسخة فقط.</div>', unsafe_allow_html=True)
        st.markdown("")

        if can("admin"):
            if st.button("💾 حفظ نسخة احتياطية الآن", type="primary"):
                ok, result = db.backup_db()
                if ok:
                    st.success(f"✅ تم حفظ النسخة الاحتياطية بنجاح")
                    st.code(result, language=None)
                else:
                    st.error(f"⚠️ فشل الحفظ: {result}")
            st.markdown("---")

        # List existing backups
        backup_dir = db.BACKUP_DIR
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("alkhayar_hr_backup_*.db"), reverse=True)
            if backups:
                st.markdown(f"**النسخ الاحتياطية المحفوظة ({len(backups)} نسخة):**")
                rows_html = ""
                for i, b in enumerate(backups, 1):
                    size_kb = round(b.stat().st_size / 1024, 1)
                    # Extract timestamp from filename
                    ts_part = b.stem.replace("alkhayar_hr_backup_", "").replace("_", " ", 1)
                    badge = "🟢" if i == 1 else "⚪"
                    label = " (الأحدث)" if i == 1 else ""
                    rows_html += f"""
                    <tr>
                        <td style="text-align:center;">{badge} {i}</td>
                        <td style="font-weight:600;color:#1B2A47;">{ts_part}{label}</td>
                        <td style="color:#555;">{size_kb} KB</td>
                        <td style="color:#555;font-size:12px;">{b.name}</td>
                    </tr>"""
                st.markdown(f"""
                <table style="width:100%;border-collapse:collapse;font-family:'Cairo',sans-serif;direction:rtl;font-size:14px;">
                    <thead>
                        <tr style="background:#1B2A47;color:white;">
                            <th style="padding:10px 14px;text-align:center;font-weight:700;">#</th>
                            <th style="padding:10px 14px;text-align:right;font-weight:700;">التاريخ والوقت</th>
                            <th style="padding:10px 14px;text-align:right;font-weight:700;">الحجم</th>
                            <th style="padding:10px 14px;text-align:right;font-weight:700;">اسم الملف</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
                <style>
                table tbody tr:nth-child(even){{background:#f8fafc;}}
                table tbody tr:hover{{background:#edf2f7;}}
                table tbody td{{padding:10px 14px;border-bottom:1px solid #e2e8f0;vertical-align:middle;}}
                </style>
                <div style="text-align:right;color:#8a97a8;font-size:12px;margin-top:8px;font-family:'Cairo',sans-serif;">
                    مسار مجلد النسخ الاحتياطية: {str(backup_dir)}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.info("لا توجد نسخ احتياطية بعد. اضغط الزر أعلاه لإنشاء أول نسخة.")
        else:
            st.info("مجلد النسخ الاحتياطية لم يُنشأ بعد.")
