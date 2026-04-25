"""
database.py — Enterprise SQLite database layer
Alkhayar HR & Payroll System v4.0
"""

import sqlite3
import hashlib
import secrets
import calendar as _calendar
from datetime import datetime, date as _date
from pathlib import Path
from contextlib import contextmanager

import os as _os

# When running as a packaged .exe, launcher.py sets these env vars so that
# the database lives next to the executable (not inside the read-only bundle).
_db_env    = _os.environ.get("ALKHAYAR_DB_PATH")
_bak_env   = _os.environ.get("ALKHAYAR_BACKUP_DIR")

DB_PATH    = Path(_db_env)    if _db_env    else Path(__file__).parent / "hr_data" / "alkhayar_hr.db"
BACKUP_DIR = Path(_bak_env)   if _bak_env   else Path(__file__).parent / "backups"


def backup_db() -> tuple:
    """Copy the database to the backups folder with a timestamp filename.
    Returns (True, backup_path_str) on success or (False, error_msg) on failure.
    """
    import shutil
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if not DB_PATH.exists():
            return False, "ملف قاعدة البيانات غير موجود"
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dest = BACKUP_DIR / f"alkhayar_hr_backup_{ts}.db"
        # Use SQLite online backup API for a safe consistent copy
        import sqlite3 as _sq
        src_conn = _sq.connect(str(DB_PATH))
        dst_conn = _sq.connect(str(dest))
        src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()
        # Keep only the 30 most recent backups to avoid filling the disk
        all_backups = sorted(BACKUP_DIR.glob("alkhayar_hr_backup_*.db"), reverse=True)
        for old in all_backups[30:]:
            old.unlink(missing_ok=True)
        return True, str(dest)
    except Exception as e:
        return False, str(e)


def auto_backup_if_needed() -> None:
    """Run a backup automatically once per day (checks a marker file)."""
    marker = BACKUP_DIR / ".last_auto_backup"
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        if marker.exists() and marker.read_text().strip() == today_str:
            return  # already backed up today
        ok, _ = backup_db()
        if ok:
            marker.write_text(today_str)
    except Exception:
        pass  # never crash the app due to backup failure

BRANCH_NAMES = {
    "1": "الفرع الرئيسي",
    "2": "فرع السبعة",
    "3": "فرع الكنيسة",
    "7": "فرع مصراتة",
}


@contextmanager
def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT    NOT NULL UNIQUE,
            display_name TEXT    NOT NULL,
            salt         TEXT    NOT NULL,
            password_hash TEXT   NOT NULL,
            role         TEXT    NOT NULL DEFAULT 'hr'
                         CHECK(role IN ('admin','hr','viewer')),
            branch_access TEXT,
            is_active    INTEGER NOT NULL DEFAULT 1,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT,
            last_login   TEXT,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at   TEXT
        );

        CREATE TABLE IF NOT EXISTS departments (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ar   TEXT    NOT NULL UNIQUE,
            name_en   TEXT,
            branch_id TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT   NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS employees (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_number  TEXT    NOT NULL UNIQUE,
            full_name        TEXT    NOT NULL,
            department_id    INTEGER REFERENCES departments(id),
            branch_id        TEXT    NOT NULL,
            job_title        TEXT,
            employment_type  TEXT    NOT NULL DEFAULT 'full_time'
                             CHECK(employment_type IN ('full_time','part_time','contract')),
            hire_date        TEXT    NOT NULL,
            termination_date TEXT,
            termination_reason TEXT,
            status           TEXT    NOT NULL DEFAULT 'active'
                             CHECK(status IN ('active','terminated','on_leave','suspended')),
            phone            TEXT,
            national_id      TEXT,
            notes            TEXT,
            created_by       INTEGER REFERENCES users(id),
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT
        );

        CREATE TABLE IF NOT EXISTS allowance_types (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name_ar   TEXT    NOT NULL UNIQUE,
            name_en   TEXT,
            category  TEXT    NOT NULL DEFAULT 'allowance'
                      CHECK(category IN ('allowance','deduction')),
            is_taxable INTEGER NOT NULL DEFAULT 0,
            is_active  INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS salary_structures (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id    INTEGER NOT NULL REFERENCES employees(id),
            base_salary    REAL    NOT NULL CHECK(base_salary >= 0),
            currency       TEXT    NOT NULL DEFAULT 'LYD',
            effective_date TEXT    NOT NULL,
            reason         TEXT,
            created_by     INTEGER REFERENCES users(id),
            created_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS employee_allowances (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id       INTEGER NOT NULL REFERENCES employees(id),
            allowance_type_id INTEGER NOT NULL REFERENCES allowance_types(id),
            amount            REAL    NOT NULL CHECK(amount > 0),
            effective_date    TEXT    NOT NULL,
            end_date          TEXT,
            created_by        INTEGER REFERENCES users(id),
            created_at        TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS attendance (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            att_date    TEXT    NOT NULL,
            status      TEXT    NOT NULL DEFAULT 'present'
                        CHECK(status IN ('present','absent','half_day',
                                         'holiday','sick_leave','annual_leave')),
            notes       TEXT,
            created_by  INTEGER REFERENCES users(id),
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(employee_id, att_date)
        );

        CREATE TABLE IF NOT EXISTS advances (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id   INTEGER NOT NULL REFERENCES employees(id),
            amount        REAL    NOT NULL CHECK(amount > 0),
            issue_date    TEXT    NOT NULL,
            reason        TEXT,
            approved_by   TEXT,
            n_instalments INTEGER NOT NULL DEFAULT 1,
            status        TEXT    NOT NULL DEFAULT 'active'
                          CHECK(status IN ('active','settled','cancelled')),
            created_by    INTEGER REFERENCES users(id),
            created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS advance_instalments (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            advance_id     INTEGER NOT NULL REFERENCES advances(id),
            month_key      TEXT    NOT NULL,
            amount         REAL    NOT NULL CHECK(amount > 0),
            is_paid        INTEGER NOT NULL DEFAULT 0,
            paid_at        TEXT,
            payroll_line_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS payroll_periods (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            month_key        TEXT    NOT NULL UNIQUE,
            year             INTEGER NOT NULL,
            month            INTEGER NOT NULL,
            status           TEXT    NOT NULL DEFAULT 'draft'
                             CHECK(status IN ('draft','finalized')),
            total_gross      REAL    NOT NULL DEFAULT 0,
            total_deductions REAL    NOT NULL DEFAULT 0,
            total_net        REAL    NOT NULL DEFAULT 0,
            employee_count   INTEGER NOT NULL DEFAULT 0,
            finalized_at     TEXT,
            finalized_by     INTEGER REFERENCES users(id),
            created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS payroll_lines (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            period_id        INTEGER NOT NULL REFERENCES payroll_periods(id),
            employee_id      INTEGER NOT NULL REFERENCES employees(id),
            employee_snapshot TEXT   NOT NULL,
            base_salary      REAL    NOT NULL,
            working_days     INTEGER NOT NULL,
            absent_days      REAL    NOT NULL DEFAULT 0,
            daily_rate       REAL    NOT NULL,
            gross            REAL    NOT NULL,
            total_allowances REAL    NOT NULL DEFAULT 0,
            total_deductions REAL    NOT NULL DEFAULT 0,
            net_pay          REAL    NOT NULL,
            payslip_number   TEXT    NOT NULL UNIQUE,
            UNIQUE(period_id, employee_id)
        );

        CREATE TABLE IF NOT EXISTS payroll_items (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id        INTEGER NOT NULL REFERENCES payroll_lines(id),
            item_type      TEXT    NOT NULL
                           CHECK(item_type IN ('allowance','deduction','advance_deduction',
                                               'absence_deduction','bonus','penalty_deduction')),
            description_ar TEXT    NOT NULL,
            amount         REAL    NOT NULL,
            reference_id   INTEGER
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER REFERENCES users(id),
            username   TEXT,
            action     TEXT    NOT NULL,
            module     TEXT    NOT NULL,
            detail     TEXT,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS partners (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            is_active  INTEGER NOT NULL DEFAULT 1,
            created_at TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS partner_withdrawals (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id  INTEGER NOT NULL REFERENCES partners(id),
            amount      REAL    NOT NULL CHECK(amount > 0),
            w_date      TEXT    NOT NULL,
            description TEXT,
            logged_by   TEXT,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS custody_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            item_name TEXT NOT NULL,
            item_category TEXT NOT NULL DEFAULT 'أخرى',
            quantity INTEGER NOT NULL DEFAULT 1,
            issue_date TEXT NOT NULL,
            return_date TEXT,
            status TEXT NOT NULL DEFAULT 'issued' CHECK(status IN ('issued','returned','damaged','lost')),
            notes TEXT,
            issued_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cash_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            amount REAL NOT NULL CHECK(amount > 0),
            pay_date TEXT NOT NULL,
            description TEXT,
            approved_by TEXT,
            logged_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS penalties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            penalty_type TEXT NOT NULL DEFAULT 'خصم مالي' CHECK(penalty_type IN ('خصم مالي','إنذار','إنذار مع خصم','إيقاف')),
            amount REAL NOT NULL DEFAULT 0 CHECK(amount >= 0),
            penalty_date TEXT NOT NULL,
            reason TEXT NOT NULL,
            month_key TEXT,
            deducted INTEGER NOT NULL DEFAULT 0,
            issued_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS salary_holds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL REFERENCES employees(id),
            month_key TEXT NOT NULL,
            reason TEXT NOT NULL,
            held_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(employee_id, month_key)
        );

        CREATE TABLE IF NOT EXISTS company_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount > 0),
            expense_date TEXT NOT NULL,
            month_key TEXT NOT NULL,
            description TEXT,
            logged_by TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_expense_month ON company_expenses(month_key);
        CREATE INDEX IF NOT EXISTS idx_custody_emp ON custody_items(employee_id);
        CREATE INDEX IF NOT EXISTS idx_custody_status ON custody_items(status);
        CREATE INDEX IF NOT EXISTS idx_cash_emp ON cash_payments(employee_id);
        CREATE INDEX IF NOT EXISTS idx_penalty_emp ON penalties(employee_id);
        CREATE INDEX IF NOT EXISTS idx_hold_emp ON salary_holds(employee_id);
        CREATE INDEX IF NOT EXISTS idx_emp_status   ON employees(status);
        CREATE INDEX IF NOT EXISTS idx_emp_branch   ON employees(branch_id);
        CREATE INDEX IF NOT EXISTS idx_sal_emp      ON salary_structures(employee_id);
        CREATE INDEX IF NOT EXISTS idx_att_emp_date ON attendance(employee_id, att_date);
        CREATE INDEX IF NOT EXISTS idx_adv_emp      ON advances(employee_id);
        CREATE INDEX IF NOT EXISTS idx_pl_period    ON payroll_lines(period_id);
        CREATE INDEX IF NOT EXISTS idx_audit_date   ON audit_log(created_at);
        """)
        # Partial unique index on national_id — skip gracefully if duplicates exist in old data
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_emp_national_id
                ON employees(national_id)
                WHERE national_id IS NOT NULL AND national_id != ''
            """)
        except Exception:
            pass  # Existing duplicate national_ids prevent index creation; enforce via app layer
    _migrate_db()
    _seed_initial_data()


def _migrate_db():
    """Apply schema migrations that cannot be handled by CREATE TABLE IF NOT EXISTS."""
    with get_db() as conn:
        # ── Fix payroll_items CHECK constraint to include penalty_deduction ──
        row = conn.execute("""
            SELECT sql FROM sqlite_master WHERE type='table' AND name='payroll_items'
        """).fetchone()
        if row and "penalty_deduction" not in row["sql"]:
            conn.executescript("""
                PRAGMA foreign_keys=OFF;
                BEGIN;
                CREATE TABLE IF NOT EXISTS payroll_items_new (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    line_id     INTEGER NOT NULL REFERENCES payroll_lines(id) ON DELETE CASCADE,
                    item_type   TEXT NOT NULL
                                CHECK(item_type IN ('allowance','deduction','advance_deduction',
                                                    'absence_deduction','bonus','penalty_deduction')),
                    description_ar TEXT,
                    amount      REAL NOT NULL DEFAULT 0,
                    reference_id INTEGER
                );
                INSERT INTO payroll_items_new SELECT * FROM payroll_items;
                DROP TABLE payroll_items;
                ALTER TABLE payroll_items_new RENAME TO payroll_items;
                COMMIT;
                PRAGMA foreign_keys=ON;
            """)


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _seed_initial_data():
    with get_db() as conn:
        # Only seed the admin account if NO users exist at all (brand-new DB)
        # Never auto-recreate users that were intentionally deleted by an admin
        no_users = not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if no_users:
            salt = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO users(username,display_name,salt,password_hash,role) VALUES(?,?,?,?,'admin')",
                ("admin","مدير النظام",salt,_hash_pw("AlKhayar@2024",salt))
            )
            salt = secrets.token_hex(32)
            conn.execute(
                "INSERT INTO users(username,display_name,salt,password_hash,role) VALUES(?,?,?,?,'hr')",
                ("hr","مسؤول الموارد البشرية",salt,_hash_pw("HR@Alkhayar2024",salt))
            )

        for name_ar, name_en in [
            ("إدارة","Management"),("مبيعات","Sales"),
            ("مستودع","Warehouse"),("مواصلات","Transport"),("محاسبة","Accounting")
        ]:
            conn.execute("INSERT OR IGNORE INTO departments(name_ar,name_en) VALUES(?,?)",(name_ar,name_en))

        # Seed partners if none exist
        if not conn.execute("SELECT 1 FROM partners LIMIT 1").fetchone():
            for name in ["سالم عاشور", "عبد الرؤوف"]:
                conn.execute("INSERT INTO partners(name) VALUES(?)", (name,))

        for name_ar, name_en, cat in [
            ("بدل سكن","Housing Allowance","allowance"),
            ("بدل مواصلات","Transport Allowance","allowance"),
            ("بدل اتصالات","Communication Allowance","allowance"),
            ("بدل طبي","Medical Allowance","allowance"),
            ("مكافأة أداء","Performance Bonus","allowance"),
            ("خصم تأخير","Late Penalty","deduction"),
            ("خصم تأديبي","Disciplinary Deduction","deduction"),
        ]:
            conn.execute("INSERT OR IGNORE INTO allowance_types(name_ar,name_en,category) VALUES(?,?,?)",
                         (name_ar,name_en,cat))

        if not conn.execute("SELECT 1 FROM employees LIMIT 1").fetchone():
            _seed_employees(conn)


def _seed_employees(conn):
    pass  # No default employees — all employees added manually via the UI


# ── Auth ──────────────────────────────────────────────────────────
def auth_login(username:str, password:str) -> tuple:
    import time
    from datetime import datetime, timedelta
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? AND is_active=1",(username,)
        ).fetchone()
        if not row:
            time.sleep(1)
            return False,"اسم المستخدم أو كلمة المرور غير صحيحة",{}
        user = dict(row)
        if user["locked_until"]:
            lock_dt = datetime.fromisoformat(user["locked_until"])
            if datetime.now() < lock_dt:
                mins = int((lock_dt-datetime.now()).total_seconds()/60)+1
                time.sleep(1)  # constant-time response to prevent account enumeration
                return False,f"الحساب مقفل. حاول بعد {mins} دقيقة",{}
            else:
                conn.execute("UPDATE users SET locked_until=NULL,failed_attempts=0 WHERE id=?",(user["id"],))
        if _hash_pw(password,user["salt"]) != user["password_hash"]:
            attempts = user["failed_attempts"]+1
            if attempts >= 5:
                locked = (datetime.now()+timedelta(minutes=15)).isoformat()
                conn.execute("UPDATE users SET failed_attempts=?,locked_until=? WHERE id=?",(attempts,locked,user["id"]))
                _write_audit(conn,user["id"],username,"LOGIN_FAILED_LOCKED","auth","قفل الحساب")
                return False,"تم قفل الحساب. انتظر 15 دقيقة",{}
            conn.execute("UPDATE users SET failed_attempts=? WHERE id=?",(attempts,user["id"]))
            time.sleep(1)
            return False,f"كلمة المرور غير صحيحة ({5-attempts} محاولات متبقية)",{}
        conn.execute("UPDATE users SET failed_attempts=0,locked_until=NULL,last_login=? WHERE id=?",
                     (datetime.now().isoformat(),user["id"]))
        _write_audit(conn,user["id"],username,"LOGIN","auth","تسجيل دخول ناجح")
        return True,user["display_name"],{
            "id":user["id"],"username":user["username"],
            "display_name":user["display_name"],"role":user["role"],
            "branch_access":user["branch_access"]
        }


def auth_change_password(user_id:int,username:str,old_pw:str,new_pw:str)->tuple:
    if len(new_pw)<8:
        return False,"كلمة المرور يجب أن تكون 8 أحرف على الأقل"
    with get_db() as conn:
        row = conn.execute("SELECT salt,password_hash FROM users WHERE id=?",(user_id,)).fetchone()
        if not row or _hash_pw(old_pw,row["salt"])!=row["password_hash"]:
            return False,"كلمة المرور الحالية غير صحيحة"
        ns = secrets.token_hex(32)
        conn.execute("UPDATE users SET salt=?,password_hash=?,updated_at=? WHERE id=?",
                     (ns,_hash_pw(new_pw,ns),datetime.now().isoformat(),user_id))
        _write_audit(conn,user_id,username,"PASSWORD_CHANGE","auth","تغيير كلمة المرور")
    return True,"تم تغيير كلمة المرور بنجاح"


# ── Employee ──────────────────────────────────────────────────────
def emp_list(status:str="active",branch_id:str=None)->list:
    q = "SELECT e.*,d.name_ar as dept_name FROM employees e LEFT JOIN departments d ON e.department_id=d.id WHERE e.status=?"
    params=[status]
    if branch_id:
        q+=" AND e.branch_id=?"; params.append(branch_id)
    q+=" ORDER BY e.employee_number"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def emp_all(branch_id:str=None)->list:
    q = "SELECT e.*,d.name_ar as dept_name FROM employees e LEFT JOIN departments d ON e.department_id=d.id"
    params=[]
    if branch_id:
        q+=" WHERE e.branch_id=?"; params.append(branch_id)
    q+=" ORDER BY e.employee_number"
    with get_db() as conn:
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def emp_get(emp_id:int)->dict|None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT e.*,d.name_ar as dept_name FROM employees e LEFT JOIN departments d ON e.department_id=d.id WHERE e.id=?",
            (emp_id,)
        ).fetchone()
        return dict(row) if row else None


def emp_add(data:dict,created_by:int)->int:
    with get_db() as conn:
        # Robust: extract all numeric suffixes and use MAX+1
        all_nums = conn.execute("SELECT employee_number FROM employees").fetchall()
        parsed = []
        for r in all_nums:
            try: parsed.append(int(r["employee_number"].split("-")[-1]))
            except: pass
        num = max(parsed)+1 if parsed else 1
        emp_num = f"EMP-{num:04d}"
        cur = conn.execute("""
            INSERT INTO employees(employee_number,full_name,department_id,branch_id,
                job_title,employment_type,hire_date,phone,national_id,notes,created_by,status)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'active')
        """,(emp_num,data["full_name"],data.get("department_id"),data["branch_id"],
              data.get("job_title",""),data.get("employment_type","full_time"),
              data["hire_date"],data.get("phone",""),data.get("national_id",""),
              data.get("notes",""),created_by))
        emp_id = cur.lastrowid
        _write_audit(conn,created_by,None,"ADD_EMPLOYEE","employees",f"إضافة: {emp_num} — {data['full_name']}")
        if data.get("base_salary",0)>0:
            conn.execute("INSERT INTO salary_structures(employee_id,base_salary,effective_date,reason,created_by) VALUES(?,?,?,'راتب بداية التعيين',?)",
                         (emp_id,data["base_salary"],data["hire_date"],created_by))
        return emp_id


def emp_update(emp_id:int,data:dict,updated_by:int)->None:
    with get_db() as conn:
        conn.execute("""
            UPDATE employees SET full_name=?,department_id=?,branch_id=?,job_title=?,
                employment_type=?,phone=?,national_id=?,notes=?,status=?,
                termination_date=?,termination_reason=?,updated_at=?
            WHERE id=?
        """,(data["full_name"],data.get("department_id"),data["branch_id"],
              data.get("job_title",""),data.get("employment_type","full_time"),
              data.get("phone",""),data.get("national_id",""),data.get("notes",""),
              data["status"],data.get("termination_date"),data.get("termination_reason"),
              datetime.now().isoformat(),emp_id))
        _write_audit(conn,updated_by,None,"UPDATE_EMPLOYEE","employees",
                     f"تعديل ID={emp_id}: {data['full_name']} → {data['status']}")


# ── Salary ────────────────────────────────────────────────────────
def salary_get_base(emp_id:int)->float:
    with get_db() as conn:
        row = conn.execute(
            "SELECT base_salary FROM salary_structures WHERE employee_id=? ORDER BY effective_date DESC LIMIT 1",
            (emp_id,)
        ).fetchone()
        return row["base_salary"] if row else 0.0


def salary_set(emp_id:int,amount:float,effective_date:str,reason:str,created_by:int)->None:
    with get_db() as conn:
        conn.execute("INSERT INTO salary_structures(employee_id,base_salary,effective_date,reason,created_by) VALUES(?,?,?,?,?)",
                     (emp_id,amount,effective_date,reason,created_by))
        _write_audit(conn,created_by,None,"SET_SALARY","payroll",
                     f"راتب موظف ID={emp_id}: {amount} د.ل من {effective_date}")


def salary_history(emp_id:int)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT ss.*,u.display_name as set_by_name FROM salary_structures ss
            LEFT JOIN users u ON ss.created_by=u.id
            WHERE ss.employee_id=? ORDER BY ss.effective_date DESC
        """,(emp_id,)).fetchall()]


# ── Allowances ────────────────────────────────────────────────────
def allowance_types_list(category:str=None)->list:
    with get_db() as conn:
        if category:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM allowance_types WHERE category=? AND is_active=1",(category,)).fetchall()]
        return [dict(r) for r in conn.execute(
            "SELECT * FROM allowance_types WHERE is_active=1").fetchall()]


def emp_allowances_get(emp_id:int,month_key:str)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT ea.*,at.name_ar,at.category FROM employee_allowances ea
            JOIN allowance_types at ON ea.allowance_type_id=at.id
            WHERE ea.employee_id=? AND ea.effective_date<=?
              AND (ea.end_date IS NULL OR ea.end_date>=?)
        """,(emp_id,month_key+"-01",month_key+"-01")).fetchall()]


def emp_allowance_add(emp_id:int,allowance_type_id:int,amount:float,
                       effective_date:str,created_by:int)->None:
    with get_db() as conn:
        conn.execute("INSERT INTO employee_allowances(employee_id,allowance_type_id,amount,effective_date,created_by) VALUES(?,?,?,?,?)",
                     (emp_id,allowance_type_id,amount,effective_date,created_by))
        at = conn.execute("SELECT name_ar FROM allowance_types WHERE id=?",(allowance_type_id,)).fetchone()["name_ar"]
        _write_audit(conn,created_by,None,"ADD_ALLOWANCE","payroll",
                     f"إضافة {at} للموظف ID={emp_id}: {amount} د.ل")


# ── Attendance ────────────────────────────────────────────────────
def attendance_save_day(records:list,created_by:int)->None:
    with get_db() as conn:
        for rec in records:
            conn.execute("""
                INSERT INTO attendance(employee_id,att_date,status,notes,created_by)
                VALUES(?,?,?,?,?)
                ON CONFLICT(employee_id,att_date)
                DO UPDATE SET status=excluded.status,notes=excluded.notes,created_by=excluded.created_by
            """,(rec["employee_id"],rec["date"],rec["status"],rec.get("notes",""),created_by))
        if records:
            _write_audit(conn,created_by,None,"ATTENDANCE","attendance",
                         f"تسجيل حضور {records[0]['date']}: {len(records)} موظف")


def attendance_absences_count(emp_id:int,year:int,month:int)->dict:
    prefix = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        rows = conn.execute(
            "SELECT status,COUNT(*) as cnt FROM attendance WHERE employee_id=? AND att_date LIKE ? GROUP BY status",
            (emp_id,prefix+"%")
        ).fetchall()
        counts = {r["status"]:r["cnt"] for r in rows}
        return {"absent":counts.get("absent",0),"half_day":counts.get("half_day",0),
                "sick_leave":counts.get("sick_leave",0)}


# ── Advances ──────────────────────────────────────────────────────
def advance_add(emp_id:int,amount:float,issue_date:str,reason:str,
                approved_by:str,n_months:int,created_by:int)->int:
    if n_months < 1:
        raise ValueError("عدد الأقساط يجب أن يكون 1 على الأقل")
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO advances(employee_id,amount,issue_date,reason,
                approved_by,n_instalments,created_by)
            VALUES(?,?,?,?,?,?,?)
        """,(emp_id,amount,issue_date,reason,approved_by,n_months,created_by))
        adv_id = cur.lastrowid
        d = _date.fromisoformat(issue_date)
        inst_amount = round(amount/n_months,2)
        sm = d.month+1 if d.month<12 else 1
        sy = d.year if d.month<12 else d.year+1
        for i in range(n_months):
            m = (sm-1+i)%12+1
            y = sy+(sm-1+i)//12
            mk = f"{y:04d}-{m:02d}"
            amt = inst_amount
            if i==n_months-1:
                amt = round(amount-inst_amount*(n_months-1),2)
            conn.execute("INSERT INTO advance_instalments(advance_id,month_key,amount) VALUES(?,?,?)",
                         (adv_id,mk,amt))
        _write_audit(conn,created_by,None,"ADD_ADVANCE","advances",
                     f"سلفة موظف ID={emp_id}: {amount} د.ل / {n_months} أشهر")
        return adv_id


def advance_deduction_month(emp_id:int,year:int,month:int)->list:
    mk = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT ai.*,a.amount as total_advance,a.id as advance_id
            FROM advance_instalments ai JOIN advances a ON ai.advance_id=a.id
            WHERE a.employee_id=? AND ai.month_key=? AND ai.is_paid=0
        """,(emp_id,mk)).fetchall()]


def advances_active(emp_id:int=None)->list:
    with get_db() as conn:
        q = """
            SELECT a.*,e.full_name,e.employee_number,
                   COALESCE(SUM(CASE WHEN ai.is_paid=0 THEN ai.amount ELSE 0 END),0) as remaining
            FROM advances a JOIN employees e ON a.employee_id=e.id
            LEFT JOIN advance_instalments ai ON ai.advance_id=a.id
            WHERE a.status='active'
        """
        params=[]
        if emp_id:
            q+=" AND a.employee_id=?"; params.append(emp_id)
        q+=" GROUP BY a.id ORDER BY a.issue_date DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


# ── Payroll Engine ────────────────────────────────────────────────
def _working_days(year:int,month:int)->int:
    # Only Friday (4) is off — Saturday through Thursday are working days
    return sum(
        1 for d in range(1,_calendar.monthrange(year,month)[1]+1)
        if _date(year,month,d).weekday() != 4
    )


def payroll_compute_line(emp_id:int,year:int,month:int)->dict:
    mk = f"{year:04d}-{month:02d}"
    emp = emp_get(emp_id)
    if not emp: raise ValueError(f"موظف غير موجود: {emp_id}")
    import json as _json2
    snapshot = _json2.dumps({
        "employee_number":emp["employee_number"],"full_name":emp["full_name"],
        "branch_id":emp["branch_id"],"job_title":emp.get("job_title",""),
        "dept_name":emp.get("dept_name",""),
    },ensure_ascii=False)

    # Check salary hold first
    is_held = salary_hold_check(emp_id,mk)

    base   = salary_get_base(emp_id)
    wdays  = _working_days(year,month)
    daily  = round(base/wdays,4) if wdays>0 else 0.0
    counts = attendance_absences_count(emp_id,year,month)
    absent_days = counts["absent"]+counts["half_day"]*0.5+counts["sick_leave"]
    absence_ded = round(daily*absent_days,2)
    allowances  = emp_allowances_get(emp_id,mk)
    alw_sum     = sum(a["amount"] for a in allowances if a["category"]=="allowance")
    alw_ded     = sum(a["amount"] for a in allowances if a["category"]=="deduction")
    adv_insts   = advance_deduction_month(emp_id,year,month)
    adv_ded     = round(sum(i["amount"] for i in adv_insts),2)
    pen_insts   = penalty_deductions_month(emp_id,year,month)
    pen_ded     = round(sum(p["amount"] for p in pen_insts),2)
    gross       = round(base+alw_sum,2)
    total_ded   = round(absence_ded+alw_ded+adv_ded+pen_ded,2)
    net         = round(max(0.0,gross-total_ded),2)

    # Build line_items for payslip display
    line_items = []

    if is_held:
        # Salary held — zero out net and add hold line
        net = 0.0
        total_ded = gross
        line_items.append({
            "type": "hold",
            "desc": "إيقاف مرتب",
            "amount": gross,
        })
    else:
        for a in allowances:
            line_items.append({
                "type": a["category"],          # "allowance" or "deduction"
                "desc": a["name_ar"],
                "amount": a["amount"],
            })
        if absence_ded > 0:
            line_items.append({
                "type": "absence",
                "desc": f"خصم الغياب ({absent_days} يوم)",
                "amount": absence_ded,
            })
        for inst in adv_insts:
            line_items.append({
                "type": "advance",
                "desc": "خصم قسط سلفة",
                "amount": inst["amount"],
            })
        for pen in pen_insts:
            line_items.append({
                "type": "penalty",
                "desc": f"عقوبة: {pen['reason']}",
                "amount": pen["amount"],
            })

    return {
        # Core identifiers
        "employee_id":       emp_id,
        "employee_number":   emp["employee_number"],
        "full_name":         emp["full_name"],
        "employee_name":     emp["full_name"],           # alias for app.py
        "branch_id":         emp["branch_id"],
        "branch_name":       BRANCH_NAMES.get(str(emp["branch_id"]), str(emp["branch_id"])),
        "dept_name":         emp.get("dept_name", ""),
        "job_title":         emp.get("job_title", ""),
        # Period
        "month_key":         mk,
        "year":              year,
        "month":             month,
        # Salary components
        "base_salary":       base,
        "working_days":      wdays,
        "absent_days":       absent_days,
        "daily_rate":        daily,
        # Allowances / deductions
        "allowances":        allowances,
        "allowances_sum":    alw_sum,
        "total_allowances":  alw_sum,                   # alias for app.py
        "allowances_ded":    alw_ded,
        "bonus":             0,                         # one-time bonuses included in alw_sum
        # Advances
        "adv_instalments":   adv_insts,
        "advance_deduction": adv_ded,
        # Penalties
        "pen_instalments":   pen_insts,
        "penalty_deduction": pen_ded,
        # Salary hold
        "is_held":           is_held,
        # Totals
        "absence_deduction": absence_ded,
        "gross":             gross,
        "gross_salary":      gross,                     # alias for app.py
        "total_deductions":  total_ded,
        "net_pay":           net,
        "net_salary":        net,                       # alias for app.py
        # Detail lines for payslip rendering
        "line_items":        line_items,
        # Snapshot
        "employee_snapshot": snapshot,
    }


def payroll_preview(year:int,month:int)->list:
    return [payroll_compute_line(e["id"],year,month) for e in emp_list(status="active")]


def payroll_finalize(year:int,month:int,finalized_by:int)->int:
    import json
    mk = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id, status FROM payroll_periods WHERE month_key=?", (mk,)
        ).fetchone()
        if existing and existing["status"] == "finalized":
            raise ValueError(f"مسير {mk} مُقفل مسبقاً")
        lines = payroll_preview(year,month)
        if not lines: raise ValueError("لا يوجد موظفون نشطون")
        total_gross      = sum(l["gross"] for l in lines)
        total_deductions = sum(l["total_deductions"] for l in lines)
        total_net        = sum(l["net_pay"] for l in lines)
        fin_at           = datetime.now().isoformat()

        if existing:
            # Draft exists (was reopened) — update in place and wipe old lines
            period_id = existing["id"]
            conn.execute("""
                UPDATE payroll_periods
                SET status='finalized', total_gross=?, total_deductions=?,
                    total_net=?, employee_count=?, finalized_at=?, finalized_by=?
                WHERE id=?
            """, (total_gross, total_deductions, total_net,
                  len(lines), fin_at, finalized_by, period_id))
            # Remove old payroll lines so we can re-insert clean ones
            old_line_ids = [r["id"] for r in conn.execute(
                "SELECT id FROM payroll_lines WHERE period_id=?", (period_id,)
            ).fetchall()]
            for lid in old_line_ids:
                conn.execute("DELETE FROM payroll_items WHERE line_id=?", (lid,))
            conn.execute("DELETE FROM payroll_lines WHERE period_id=?", (period_id,))
        else:
            cur = conn.execute("""
                INSERT INTO payroll_periods(month_key,year,month,status,
                    total_gross,total_deductions,total_net,employee_count,finalized_at,finalized_by)
                VALUES(?,?,?,'finalized',?,?,?,?,?,?)
            """, (mk, year, month, total_gross, total_deductions, total_net,
                  len(lines), fin_at, finalized_by))
            period_id = cur.lastrowid
        for i,line in enumerate(lines,1):
            ps_num = f"PSL-{year}-{month:02d}-{i:04d}"
            cur2 = conn.execute("""
                INSERT INTO payroll_lines(period_id,employee_id,employee_snapshot,
                    base_salary,working_days,absent_days,daily_rate,
                    gross,total_allowances,total_deductions,net_pay,payslip_number)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,(period_id,line["employee_id"],line["employee_snapshot"],
                  line["base_salary"],line["working_days"],line["absent_days"],
                  line["daily_rate"],line["gross"],line["allowances_sum"],
                  line["total_deductions"],line["net_pay"],ps_num))
            line_id = cur2.lastrowid
            for alw in line["allowances"]:
                conn.execute("INSERT INTO payroll_items(line_id,item_type,description_ar,amount,reference_id) VALUES(?,?,?,?,?)",
                             (line_id,"allowance" if alw["category"]=="allowance" else "deduction",
                              alw["name_ar"],alw["amount"],alw.get("allowance_type_id")))
            if line["absence_deduction"]>0:
                conn.execute("INSERT INTO payroll_items(line_id,item_type,description_ar,amount) VALUES(?,'absence_deduction',?,?)",
                             (line_id,f"خصم الغياب ({line['absent_days']} يوم)",line["absence_deduction"]))
            for inst in line["adv_instalments"]:
                conn.execute("INSERT INTO payroll_items(line_id,item_type,description_ar,amount,reference_id) VALUES(?,'advance_deduction','خصم قسط سلفة',?,?)",
                             (line_id,inst["amount"],inst["advance_id"]))
                conn.execute("UPDATE advance_instalments SET is_paid=1,paid_at=?,payroll_line_id=? WHERE id=?",
                             (datetime.now().isoformat(),line_id,inst["id"]))
            conn.execute("""
                UPDATE advances SET status='settled'
                WHERE employee_id=? AND status='active'
                AND id NOT IN (SELECT DISTINCT advance_id FROM advance_instalments WHERE is_paid=0)
            """,(line["employee_id"],))
            for pen in line.get("pen_instalments",[]):
                conn.execute("INSERT INTO payroll_items(line_id,item_type,description_ar,amount,reference_id) VALUES(?,'penalty_deduction',?,?,?)",
                             (line_id,f"عقوبة: {pen['reason']}",pen["amount"],pen["id"]))
                conn.execute("UPDATE penalties SET deducted=1 WHERE id=?",(pen["id"],))
        _write_audit(conn,finalized_by,None,"FINALIZE_PAYROLL","payroll",
                     f"إقفال مسير {mk}: {len(lines)} موظف | صافي={total_net:,.2f} د.ل")
        return period_id


def payroll_get_period(year:int,month:int)->dict|None:
    mk = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        row = conn.execute("""
            SELECT pp.*, COALESCE(u.display_name, CAST(pp.finalized_by AS TEXT), '—') as finalized_by_name
            FROM payroll_periods pp
            LEFT JOIN users u ON pp.finalized_by = u.id
            WHERE pp.month_key=?
        """,(mk,)).fetchone()
        if not row:
            return None
        d = dict(row)
        # Overwrite finalized_by with display name for app.py convenience
        d["finalized_by"] = d.get("finalized_by_name", "—") or "—"
        return d


def payroll_get_lines(period_id:int)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT pl.*,e.employee_number,e.full_name,e.branch_id FROM payroll_lines pl
            JOIN employees e ON pl.employee_id=e.id
            WHERE pl.period_id=? ORDER BY e.employee_number
        """,(period_id,)).fetchall()]


def payroll_get_line_items(line_id:int)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM payroll_items WHERE line_id=? ORDER BY item_type",(line_id,)
        ).fetchall()]


# ── Reports ───────────────────────────────────────────────────────
def report_payroll_history(limit:int=12)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT pp.*,u.display_name as finalized_by_name FROM payroll_periods pp
            LEFT JOIN users u ON pp.finalized_by=u.id
            ORDER BY pp.month_key DESC LIMIT ?
        """,(limit,)).fetchall()]


def report_employee_summary()->dict:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM employees WHERE status='active'").fetchone()[0]
        by_branch = [dict(r) for r in conn.execute("""
            SELECT e.branch_id,
                   COUNT(*) as emp_count,
                   COALESCE(SUM(ss.base_salary),0) as total_base
            FROM employees e
            LEFT JOIN salary_structures ss
                ON ss.employee_id=e.id
                AND ss.id=(SELECT MAX(s2.id) FROM salary_structures s2 WHERE s2.employee_id=e.id)
            WHERE e.status='active'
            GROUP BY e.branch_id
        """).fetchall()]
        by_dept = [dict(r) for r in conn.execute("""
            SELECT d.name_ar,COUNT(*) as cnt FROM employees e
            LEFT JOIN departments d ON e.department_id=d.id
            WHERE e.status='active' GROUP BY e.department_id
        """).fetchall()]
        total_payroll = conn.execute("""
            SELECT COALESCE(SUM(ss.base_salary),0) FROM salary_structures ss
            WHERE ss.id IN (SELECT MAX(id) FROM salary_structures GROUP BY employee_id)
            AND ss.employee_id IN (SELECT id FROM employees WHERE status='active')
        """).fetchone()[0]
        return {"total_active":total,"by_branch":by_branch,"by_dept":by_dept,
                "total_monthly_payroll":total_payroll}


def report_audit_log(limit:int=200)->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT al.*,u.display_name FROM audit_log al
            LEFT JOIN users u ON al.user_id=u.id
            ORDER BY al.created_at DESC LIMIT ?
        """,(limit,)).fetchall()]


def dept_list()->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM departments WHERE is_active=1 ORDER BY name_ar"
        ).fetchall()]


def users_list()->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id,username,display_name,role,is_active,last_login,created_at FROM users ORDER BY id"
        ).fetchall()]


def user_add(username:str,display_name:str,password:str,role:str,created_by:int)->None:
    salt = secrets.token_hex(32)
    with get_db() as conn:
        conn.execute("INSERT INTO users(username,display_name,salt,password_hash,role) VALUES(?,?,?,?,?)",
                     (username,display_name,salt,_hash_pw(password,salt),role))
        _write_audit(conn,created_by,None,"ADD_USER","users",f"إضافة مستخدم: {username} ({role})")


def user_delete(target_user_id:int, deleted_by_id:int, deleted_by_username:str) -> tuple:
    """حذف مستخدم — لا يمكن حذف آخر admin أو حذف نفسك."""
    with get_db() as conn:
        row = conn.execute("SELECT username,role FROM users WHERE id=?",(target_user_id,)).fetchone()
        if not row:
            return False,"المستخدم غير موجود"
        if target_user_id == deleted_by_id:
            return False,"لا يمكنك حذف حسابك أنت"
        if row["role"] == "admin":
            admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND is_active=1").fetchone()[0]
            if admins <= 1:
                return False,"لا يمكن حذف آخر مدير نظام في النظام"
        conn.execute("DELETE FROM users WHERE id=?",(target_user_id,))
        _write_audit(conn, deleted_by_id, deleted_by_username,
                     "DELETE_USER","users",
                     f"حذف المستخدم: {row['username']} ({row['role']})")
    return True, f"تم حذف المستخدم '{row['username']}' بنجاح"


def write_audit(user_id:int,username:str,action:str,module:str,detail:str)->None:
    with get_db() as conn:
        _write_audit(conn,user_id,username,action,module,detail)


def _write_audit(conn,user_id,username,action,module,detail):
    conn.execute("INSERT INTO audit_log(user_id,username,action,module,detail) VALUES(?,?,?,?,?)",
                 (user_id,username,action,module,detail))


# ── Custody (عهدة) ───────────────────────────────────────────────
def custody_add(emp_id:int,item_name:str,category:str,quantity:int,
                issue_date:str,notes:str=None,issued_by:str=None)->tuple:
    if not item_name or not item_name.strip():
        return False,"اسم الصنف مطلوب"
    if quantity<1:
        return False,"الكمية يجب أن تكون 1 على الأقل"
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO custody_items(employee_id,item_name,item_category,quantity,
                    issue_date,notes,issued_by)
                VALUES(?,?,?,?,?,?,?)
            """,(emp_id,item_name.strip(),category or 'أخرى',quantity,issue_date,
                  notes,issued_by))
            _write_audit(conn,None,issued_by,"ADD_CUSTODY","custody",
                         f"تسليم عهدة للموظف ID={emp_id}: {item_name} ×{quantity}")
        return True,"تم تسجيل العهدة بنجاح"
    except Exception as e:
        return False,str(e)


def custody_list(emp_id:int=None,status:str=None)->list:
    with get_db() as conn:
        q = """
            SELECT ci.*,e.full_name,e.employee_number
            FROM custody_items ci
            JOIN employees e ON ci.employee_id=e.id
            WHERE 1=1
        """
        params=[]
        if emp_id:
            q+=" AND ci.employee_id=?"; params.append(emp_id)
        if status:
            q+=" AND ci.status=?"; params.append(status)
        q+=" ORDER BY ci.issue_date DESC, ci.id DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def custody_return(custody_id:int,return_date:str=None,status:str='returned')->tuple:
    if status not in ('returned','damaged','lost'):
        return False,"حالة غير صالحة"
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id,status FROM custody_items WHERE id=?",(custody_id,)).fetchone()
            if not row:
                return False,"السجل غير موجود"
            if row["status"] != 'issued':
                return False,"هذا الصنف ليس في حالة تسليم"
            rd = return_date or datetime.now().strftime("%Y-%m-%d")
            conn.execute("UPDATE custody_items SET status=?,return_date=? WHERE id=?",
                         (status,rd,custody_id))
        return True,"تم تحديث حالة العهدة"
    except Exception as e:
        return False,str(e)


def custody_summary()->list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT e.id as employee_id,e.full_name,e.employee_number,
                   COUNT(ci.id) as issued_count
            FROM custody_items ci
            JOIN employees e ON ci.employee_id=e.id
            WHERE ci.status='issued'
            GROUP BY e.id
            ORDER BY issued_count DESC
        """).fetchall()]


# ── Cash Payments (صرف قيمة نقدية) ───────────────────────────────
def cash_payment_add(emp_id:int,amount:float,pay_date:str,
                     description:str=None,approved_by:str=None,
                     logged_by:str=None)->tuple:
    if amount<=0:
        return False,"المبلغ يجب أن يكون أكبر من صفر"
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO cash_payments(employee_id,amount,pay_date,description,
                    approved_by,logged_by)
                VALUES(?,?,?,?,?,?)
            """,(emp_id,amount,pay_date,description,approved_by,logged_by))
            _write_audit(conn,None,logged_by,"ADD_CASH_PAYMENT","cash_payments",
                         f"صرف نقدي للموظف ID={emp_id}: {amount} د.ل")
        return True,"تم تسجيل الصرف بنجاح"
    except Exception as e:
        return False,str(e)


def cash_payment_list(emp_id:int=None,year:int=None,month:int=None)->list:
    with get_db() as conn:
        q = """
            SELECT cp.*,e.full_name,e.employee_number
            FROM cash_payments cp
            JOIN employees e ON cp.employee_id=e.id
            WHERE 1=1
        """
        params=[]
        if emp_id:
            q+=" AND cp.employee_id=?"; params.append(emp_id)
        if year:
            q+=" AND strftime('%Y',cp.pay_date)=?"; params.append(str(year))
        if month:
            q+=" AND strftime('%m',cp.pay_date)=?"; params.append(f"{month:02d}")
        q+=" ORDER BY cp.pay_date DESC, cp.id DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def cash_payment_delete(payment_id:int)->tuple:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM cash_payments WHERE id=?",(payment_id,)).fetchone()
            if not row:
                return False,"السجل غير موجود"
            conn.execute("DELETE FROM cash_payments WHERE id=?",(payment_id,))
        return True,"تم حذف السجل"
    except Exception as e:
        return False,str(e)


def cash_payment_edit(payment_id:int,amount:float,pay_date:str,
                      description:str,edited_by:str=None)->tuple:
    if amount<=0:
        return False,"المبلغ يجب أن يكون أكبر من صفر"
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM cash_payments WHERE id=?",(payment_id,)).fetchone()
            if not row:
                return False,"السجل غير موجود"
            conn.execute("""
                UPDATE cash_payments SET amount=?,pay_date=?,description=?,logged_by=?
                WHERE id=?
            """,(amount,pay_date,description,edited_by,payment_id))
        return True,"تم تعديل السجل بنجاح"
    except Exception as e:
        return False,str(e)


def cash_payment_summary(year:int)->list:
    """Returns year-to-date total per employee."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT e.id as employee_id,e.full_name,e.employee_number,
                   COUNT(cp.id) as tx_count,
                   SUM(cp.amount) as total
            FROM cash_payments cp
            JOIN employees e ON cp.employee_id=e.id
            WHERE strftime('%Y',cp.pay_date)=?
            GROUP BY e.id
            ORDER BY e.employee_number
        """,(str(year),)).fetchall()
        return [dict(r) for r in rows]


# ── Penalties (عقوبات) ───────────────────────────────────────────
def penalty_add(emp_id:int,penalty_type:str,amount:float,penalty_date:str,
                reason:str,month_key:str=None,issued_by:str=None)->tuple:
    if not reason or not reason.strip():
        return False,"سبب العقوبة مطلوب"
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO penalties(employee_id,penalty_type,amount,penalty_date,
                    reason,month_key,issued_by)
                VALUES(?,?,?,?,?,?,?)
            """,(emp_id,penalty_type,amount,penalty_date,reason.strip(),
                  month_key,issued_by))
            _write_audit(conn,None,issued_by,"ADD_PENALTY","penalties",
                         f"عقوبة للموظف ID={emp_id}: {penalty_type} — {amount} د.ل")
        return True,"تم تسجيل العقوبة بنجاح"
    except Exception as e:
        return False,str(e)


def penalty_list(emp_id:int=None,year:int=None)->list:
    with get_db() as conn:
        q = """
            SELECT p.*,e.full_name,e.employee_number
            FROM penalties p
            JOIN employees e ON p.employee_id=e.id
            WHERE 1=1
        """
        params=[]
        if emp_id:
            q+=" AND p.employee_id=?"; params.append(emp_id)
        if year:
            q+=" AND strftime('%Y',p.penalty_date)=?"; params.append(str(year))
        q+=" ORDER BY p.penalty_date DESC, p.id DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def penalty_delete(penalty_id:int)->tuple:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM penalties WHERE id=?",(penalty_id,)).fetchone()
            if not row:
                return False,"السجل غير موجود"
            conn.execute("DELETE FROM penalties WHERE id=?",(penalty_id,))
        return True,"تم حذف العقوبة"
    except Exception as e:
        return False,str(e)


def penalty_deductions_month(emp_id:int,year:int,month:int)->list:
    mk = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT p.* FROM penalties p
            WHERE p.employee_id=? AND p.month_key=? AND p.deducted=0
              AND p.amount>0
        """,(emp_id,mk)).fetchall()]


# ── Salary Hold (إيقاف مرتب) ────────────────────────────────────
def salary_hold_add(emp_id:int,month_key:str,reason:str,held_by:str=None)->tuple:
    if not reason or not reason.strip():
        return False,"سبب الإيقاف مطلوب"
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO salary_holds(employee_id,month_key,reason,held_by)
                VALUES(?,?,?,?)
            """,(emp_id,month_key,reason.strip(),held_by))
            _write_audit(conn,None,held_by,"ADD_SALARY_HOLD","salary_holds",
                         f"إيقاف مرتب موظف ID={emp_id} لشهر {month_key}")
        return True,"تم إيقاف المرتب بنجاح"
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            return False,"المرتب موقوف مسبقاً لهذا الشهر"
        return False,str(e)


def salary_hold_remove(emp_id:int,month_key:str)->tuple:
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM salary_holds WHERE employee_id=? AND month_key=?",
                (emp_id,month_key)
            ).fetchone()
            if not row:
                return False,"لا يوجد إيقاف لهذا الشهر"
            conn.execute("DELETE FROM salary_holds WHERE employee_id=? AND month_key=?",
                         (emp_id,month_key))
        return True,"تم رفع إيقاف المرتب"
    except Exception as e:
        return False,str(e)


def salary_hold_list(month_key:str=None,emp_id:int=None)->list:
    with get_db() as conn:
        q = """
            SELECT sh.*,e.full_name,e.employee_number
            FROM salary_holds sh
            JOIN employees e ON sh.employee_id=e.id
            WHERE 1=1
        """
        params=[]
        if month_key:
            q+=" AND sh.month_key=?"; params.append(month_key)
        if emp_id:
            q+=" AND sh.employee_id=?"; params.append(emp_id)
        q+=" ORDER BY sh.month_key DESC, e.employee_number"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def salary_hold_check(emp_id:int,month_key:str)->bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM salary_holds WHERE employee_id=? AND month_key=?",
            (emp_id,month_key)
        ).fetchone()
        return row is not None


# ── Company Expenses (مصروفات الشركة) ────────────────────────────
EXPENSE_CATEGORIES = [
    "وجبات / معيشة", "إيجار", "كهرباء", "مياه", "اتصالات / إنترنت",
    "وقود / مواصلات", "صيانة", "مستلزمات مكتبية", "نظافة", "أخرى"
]

def expense_add(category:str,amount:float,expense_date:str,month_key:str,
                description:str,logged_by:str)->tuple:
    if amount <= 0:
        return False,"المبلغ يجب أن يكون أكبر من صفر"
    if not category or not category.strip():
        return False,"التصنيف مطلوب"
    try:
        with get_db() as conn:
            conn.execute("""
                INSERT INTO company_expenses(category,amount,expense_date,month_key,description,logged_by)
                VALUES(?,?,?,?,?,?)
            """,(category.strip(),amount,expense_date,month_key,
                 (description or "").strip(),logged_by))
            _write_audit(conn,None,logged_by,"ADD_EXPENSE","expenses",
                         f"مصروف {category}: {amount} د.ل — {month_key}")
        return True,"تم تسجيل المصروف بنجاح"
    except Exception as e:
        return False,str(e)


def expense_list(month_key:str=None,year:int=None,category:str=None)->list:
    with get_db() as conn:
        q = "SELECT * FROM company_expenses WHERE 1=1"
        params=[]
        if month_key:
            q+=" AND month_key=?"; params.append(month_key)
        if year:
            q+=" AND strftime('%Y',expense_date)=?"; params.append(str(year))
        if category:
            q+=" AND category=?"; params.append(category)
        q+=" ORDER BY expense_date DESC, id DESC"
        return [dict(r) for r in conn.execute(q,params).fetchall()]


def expense_delete(expense_id:int)->tuple:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM company_expenses WHERE id=?",(expense_id,)).fetchone()
            if not row:
                return False,"السجل غير موجود"
            conn.execute("DELETE FROM company_expenses WHERE id=?",(expense_id,))
        return True,"تم حذف السجل"
    except Exception as e:
        return False,str(e)


def expense_edit(expense_id:int,category:str,amount:float,expense_date:str,
                 description:str,edited_by:str)->tuple:
    if amount <= 0:
        return False,"المبلغ يجب أن يكون أكبر من صفر"
    try:
        with get_db() as conn:
            conn.execute("""
                UPDATE company_expenses SET category=?,amount=?,expense_date=?,description=?,logged_by=?
                WHERE id=?
            """,(category.strip(),amount,expense_date,(description or "").strip(),edited_by,expense_id))
        return True,"تم تعديل السجل بنجاح"
    except Exception as e:
        return False,str(e)


def expense_monthly_summary(year:int)->list:
    """Monthly totals per category for a given year."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT month_key, category, SUM(amount) as total, COUNT(*) as tx_count
            FROM company_expenses
            WHERE strftime('%Y',expense_date)=?
            GROUP BY month_key, category
            ORDER BY month_key DESC, category
        """,(str(year),)).fetchall()
        return [dict(r) for r in rows]


def expense_yearly_totals(year:int)->list:
    """Year-to-date total per category."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT category, COUNT(*) as tx_count, SUM(amount) as total
            FROM company_expenses
            WHERE strftime('%Y',expense_date)=?
            GROUP BY category
            ORDER BY total DESC
        """,(str(year),)).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# Compatibility aliases — maps app.py function calls to database.py
# ══════════════════════════════════════════════════════════════════

import json as _json

def verify_login(username: str, password: str):
    ok, msg, user = auth_login(username, password)
    return (ok, msg, user)

def get_employees(status: str = "active", branch_id: str = None) -> list:
    if status == "all":
        return emp_all(branch_id=branch_id)
    return emp_list(status=status, branch_id=branch_id)

def get_employee(emp_id: int) -> dict | None:
    return emp_get(emp_id)

def add_employee(data: dict, created_by_username: str = "system") -> tuple:
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (created_by_username,)
            ).fetchone()
            created_by = uid["id"] if uid else 1
        emp_id = emp_add(data, created_by)
        return True, f"تم إضافة الموظف بنجاح"
    except Exception as e:
        return False, str(e)

def update_employee(emp_id: int, data: dict, updated_by_username: str = "system") -> tuple:
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (updated_by_username,)
            ).fetchone()
            updated_by = uid["id"] if uid else 1
        emp_update(emp_id, data, updated_by)
        return True, "تم تحديث بيانات الموظف بنجاح"
    except Exception as e:
        return False, str(e)

def get_current_salary(emp_id: int) -> dict:
    base = salary_get_base(emp_id)
    with get_db() as conn:
        row = conn.execute("""
            SELECT ss.*, u.display_name as set_by_name
            FROM salary_structures ss
            LEFT JOIN users u ON ss.created_by = u.id
            WHERE ss.employee_id = ?
            ORDER BY ss.effective_date DESC LIMIT 1
        """, (emp_id,)).fetchone()
    if row:
        return dict(row)
    return {"base_salary": 0.0, "currency": "LYD"}

def set_salary(emp_id: int, base: float, items: list,
               effective_date: str, reason: str = "",
               approved_by: str = "",
               created_by_username: str = "system") -> tuple:
    """
    تحديث الراتب الأساسي مع البدلات.
    items = [{"type": "allowance"|"deduction", "name": str, "amount": float}, ...]
    """
    if base < 0:
        return False, "لا يمكن أن يكون الراتب الأساسي سالباً"
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (created_by_username,)
            ).fetchone()
            created_by = uid["id"] if uid else 1

        salary_set(emp_id, base, effective_date, reason or "تحديث الراتب", created_by)

        if items:
            for item in items:
                try:
                    item_name  = item.get("name", "")
                    item_cat   = item.get("type", "allowance")
                    item_amt   = float(item.get("amount", 0))
                    is_pct     = bool(item.get("is_percentage", 0))
                    # If percentage flag is set, compute absolute amount from base salary
                    if is_pct and base > 0:
                        item_amt = round(base * item_amt / 100, 2)
                    if not item_name or item_amt <= 0:
                        continue
                    with get_db() as conn2:
                        at_row = conn2.execute(
                            "SELECT id FROM allowance_types WHERE name_ar=? AND category=?",
                            (item_name, item_cat)
                        ).fetchone()
                        if at_row:
                            at_id = at_row["id"]
                        else:
                            cur = conn2.execute(
                                "INSERT OR IGNORE INTO allowance_types(name_ar,category) VALUES(?,?)",
                                (item_name, item_cat)
                            )
                            at_id = cur.lastrowid or conn2.execute(
                                "SELECT id FROM allowance_types WHERE name_ar=?", (item_name,)
                            ).fetchone()["id"]
                    emp_allowance_add(emp_id, at_id, item_amt, effective_date, created_by)
                except Exception:
                    pass
        return True, "تم حفظ هيكل الراتب بنجاح"
    except Exception as e:
        return False, str(e)

def get_salary_history(emp_id: int) -> list:
    rows = salary_history(emp_id)
    result = []
    for i, h in enumerate(rows):
        mk = (h.get("effective_date") or "")[:7]
        alws = emp_allowances_get(emp_id, mk) if mk else []
        allowances_sum = sum(a["amount"] for a in alws if a["category"] == "allowance")
        result.append({
            **h,
            "is_current":  i == 0,
            "allowances":  allowances_sum,
            "approved_by": h.get("reason", ""),  # salary_structures has no approved_by column
        })
    return result

def get_departments() -> list:
    return dept_list()

def get_attendance_month(year: int, month: int, emp_id: int = None) -> list:
    prefix = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        if emp_id:
            rows = conn.execute("""
                SELECT a.*, e.full_name, e.employee_number, e.branch_id
                FROM attendance a JOIN employees e ON a.employee_id = e.id
                WHERE a.att_date LIKE ? AND a.employee_id = ?
                ORDER BY a.att_date
            """, (prefix + "%", emp_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT a.*, e.full_name, e.employee_number, e.branch_id
                FROM attendance a JOIN employees e ON a.employee_id = e.id
                WHERE a.att_date LIKE ?
                ORDER BY a.att_date, e.employee_number
            """, (prefix + "%",)).fetchall()
        return [dict(r) for r in rows]

def record_attendance(emp_id: int, att_date: str, status: str,
                       created_by_username: str = "system") -> None:
    with get_db() as conn:
        uid = conn.execute(
            "SELECT id FROM users WHERE username=?", (created_by_username,)
        ).fetchone()
        created_by = uid["id"] if uid else 1
    attendance_save_day([{"employee_id": emp_id, "date": att_date, "status": status}],
                         created_by)

def _count_att_status(emp_id: int, year: int, month: int, status: str) -> int:
    prefix = f"{year:04d}-{month:02d}"
    with get_db() as conn:
        row = conn.execute("""
            SELECT COUNT(*) FROM attendance
            WHERE employee_id=? AND att_date LIKE ? AND status=?
        """, (emp_id, prefix + "%", status)).fetchone()
        return row[0] if row else 0

def get_advances(emp_id: int = None, status: str = None) -> list:
    with get_db() as conn:
        q = """
            SELECT a.*, e.full_name, e.employee_number,
                   COALESCE(SUM(CASE WHEN ai.is_paid=0 THEN ai.amount ELSE 0 END),0) as remaining
            FROM advances a
            JOIN employees e ON a.employee_id = e.id
            LEFT JOIN advance_instalments ai ON ai.advance_id = a.id
        """
        params = []
        conditions = []
        if status:
            conditions.append("a.status=?")
            params.append(status)
        if emp_id:
            conditions.append("a.employee_id=?")
            params.append(emp_id)
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " GROUP BY a.id ORDER BY a.issue_date DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]

def add_advance(emp_id: int, amount: float, issue_date: str,
                reason: str, approved_by: str, n_months: int,
                created_by_username: str = "system") -> tuple:
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (created_by_username,)
            ).fetchone()
            created_by = uid["id"] if uid else 1
        adv_id = advance_add(emp_id, amount, issue_date, reason,
                             approved_by, n_months, created_by)
        return True, "تم تسجيل السلفة بنجاح", adv_id
    except Exception as e:
        return False, str(e), None

def add_adjustment(emp_id: int, month_key: str, adj_type: str,
                    description: str, amount: float,
                    created_by_username: str = "system") -> None:
    """One-time bonus or deduction for a specific month."""
    with get_db() as conn:
        uid = conn.execute(
            "SELECT id FROM users WHERE username=?", (created_by_username,)
        ).fetchone()
        created_by = uid["id"] if uid else 1
        # Map to allowance_types — find or create
        cat = "allowance" if adj_type.upper() == "BONUS" else "deduction"
        at_row = conn.execute(
            "SELECT id FROM allowance_types WHERE name_ar=? AND category=?",
            (description, cat)
        ).fetchone()
        if not at_row:
            cur = conn.execute(
                "INSERT OR IGNORE INTO allowance_types(name_ar, category) VALUES(?,?)",
                (description, cat)
            )
            at_id = cur.lastrowid or conn.execute(
                "SELECT id FROM allowance_types WHERE name_ar=?", (description,)
            ).fetchone()["id"]
        else:
            at_id = at_row["id"]

        yr, mo = int(month_key[:4]), int(month_key[5:7])
        eff = f"{yr:04d}-{mo:02d}-01"
        last_day = _calendar.monthrange(yr, mo)[1]
        end = f"{yr:04d}-{mo:02d}-{last_day:02d}"
        conn.execute("""
            INSERT INTO employee_allowances(employee_id, allowance_type_id,
                amount, effective_date, end_date, created_by)
            VALUES(?,?,?,?,?,?)
        """, (emp_id, at_id, float(amount), eff, end, created_by))
        _write_audit(conn, created_by, created_by_username,
                     "ADD_ADJUSTMENT", "payroll",
                     f"{'مكافأة' if adj_type=='BONUS' else 'خصم'} {emp_id}: {amount} د.ل شهر {month_key}")

def calculate_payslip(emp_id: int, year: int, month: int) -> dict:
    return payroll_compute_line(emp_id, year, month)

def get_payroll_run(month_key: str) -> dict | None:
    yr, mo = int(month_key[:4]), int(month_key[5:7])
    return payroll_get_period(yr, mo)

def get_payroll_entries(month_key: str) -> list:
    period = get_payroll_run(month_key)
    if not period:
        return []
    lines = payroll_get_lines(period["id"])
    result = []
    for line in lines:
        raw_items = payroll_get_line_items(line["id"])
        # Normalize payroll_items keys to match payroll_compute_line format
        # payroll_items uses: item_type, description_ar
        # app.py expects:     type,      desc
        items = [
            {
                "type":   i["item_type"],
                "desc":   i["description_ar"],
                "amount": i["amount"],
            }
            for i in raw_items
        ]
        absence_ded = sum(i["amount"] for i in items if i["type"] == "absence_deduction")
        advance_ded = sum(i["amount"] for i in items if i["type"] == "advance_deduction")
        allowances  = sum(i["amount"] for i in items if i["type"] == "allowance")
        result.append({
            **line,
            "employee_name":     line.get("full_name", ""),
            "net_salary":        line.get("net_pay", 0),
            "gross_salary":      line.get("gross", 0),
            "branch_name":       BRANCH_NAMES.get(str(line.get("branch_id", "")), ""),
            "bonus":             allowances,
            "absence_deduction": absence_ded,
            "advance_deduction": advance_ded,
            "line_items":        items,
        })
    return result

def get_payroll_history() -> list:
    rows = report_payroll_history(24)
    result = []
    for h in rows:
        result.append({
            **h,
            "pay_period":   h.get("month_key", ""),
            "finalized_by": h.get("finalized_by_name", "—") or "—",
        })
    return result

def finalize_payroll(year: int, month: int,
                      finalized_by_username: str = "admin") -> tuple:
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (finalized_by_username,)
            ).fetchone()
            finalized_by = uid["id"] if uid else 1
        payroll_finalize(year, month, finalized_by)
        mk = f"{year:04d}-{month:02d}"
        # Automatic backup after every successful month close
        backup_db()
        return True, f"تم إقفال مسير {mk} بنجاح — تم حفظ نسخة احتياطية تلقائياً ✅"
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)

def reopen_payroll(year: int, month: int, reopened_by_username: str) -> tuple:
    """Admin-only: reset a finalized payroll period back to draft so it can be corrected."""
    mk = f"{year:04d}-{month:02d}"
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id, status FROM payroll_periods WHERE month_key=?", (mk,)
            ).fetchone()
            if not row:
                return False, f"لا يوجد مسير لشهر {mk}"
            if row["status"] != "finalized":
                return False, "هذا المسير ليس مُقفلاً"
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (reopened_by_username,)
            ).fetchone()
            reopened_by_id = uid["id"] if uid else 1
            # Reset period to draft and clear finalization stamps
            conn.execute("""
                UPDATE payroll_periods
                SET status='draft', finalized_at=NULL, finalized_by=NULL
                WHERE month_key=?
            """, (mk,))
            _write_audit(conn, reopened_by_id, None, "REOPEN_PAYROLL", "payroll",
                         f"إعادة فتح مسير {mk} بواسطة {reopened_by_username}")
        return True, f"تم إعادة فتح مسير {mk} — يمكنك الآن إجراء التعديلات وإعادة الإقفال"
    except Exception as e:
        return False, str(e)

def get_all_users() -> list:
    return users_list()

def create_user(username: str, display_name: str, password: str,
                role: str, branch_access, created_by_username: str = "admin") -> tuple:
    try:
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (created_by_username,)
            ).fetchone()
            created_by = uid["id"] if uid else 1
        user_add(username, display_name, password, role, created_by)
        return True, f"تم إنشاء المستخدم '{username}' بنجاح"
    except Exception as e:
        return False, str(e)

def change_password(username: str, old_pw: str, new_pw: str) -> tuple:
    with get_db() as conn:
        uid = conn.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()
        if not uid:
            return False, "المستخدم غير موجود"
        user_id = uid["id"]
    return auth_change_password(user_id, username, old_pw, new_pw)

def audit_log(username: str, action: str, detail: str = "") -> None:
    with get_db() as conn:
        uid = conn.execute(
            "SELECT id FROM users WHERE username=?", (username,)
        ).fetchone()
        user_id = uid["id"] if uid else None
        _write_audit(conn, user_id, username, action, "app", detail)

def get_audit_log(limit: int = 200) -> list:
    rows = report_audit_log(limit)
    result = []
    for r in rows:
        result.append({
            **r,
            "ts":        r.get("created_at", ""),
            "entity":    r.get("module", ""),
            "entity_id": "",
        })
    return result

def get_dashboard_kpis() -> dict:
    summary = report_employee_summary()
    hist = report_payroll_history(1)
    last = hist[0] if hist else {}
    adv = advances_active()
    total_adv = sum((a.get("remaining") or 0) for a in adv)
    return {
        # Keys aligned with app.py expectations
        "active_employees":    summary["total_active"],
        "total_payroll":       summary["total_monthly_payroll"],
        "outstanding_advances": total_adv,
        "n_active_advances":   len(adv),
        "last_payroll_month":  last.get("month_key", ""),
        "last_payroll_net":    last.get("total_net", 0),
        "branch_data":         summary["by_branch"],
        "by_dept":             summary["by_dept"],
    }

def get_salary_report() -> list:
    emps = emp_list()
    mk = _date.today().strftime("%Y-%m")
    rows = []
    for e in emps:
        base = salary_get_base(e["id"])
        alws = emp_allowances_get(e["id"], mk)
        allowances_sum = sum(a["amount"] for a in alws if a["category"] == "allowance")
        with get_db() as conn:
            ss_row = conn.execute(
                "SELECT effective_date FROM salary_structures WHERE employee_id=? ORDER BY effective_date DESC LIMIT 1",
                (e["id"],)
            ).fetchone()
        rows.append({
            "employee_id":     e["id"],
            "employee_number": e["employee_number"],
            "full_name":       e["full_name"],
            "branch_id":       e["branch_id"],
            "dept_name":       e.get("dept_name", ""),
            "job_title":       e.get("job_title", ""),
            "base_salary":     base,
            "allowances":      allowances_sum,
            "effective_date":  ss_row["effective_date"] if ss_row else "",
        })
    return rows

def delete_employee(emp_id: int, deleted_by_username: str = "admin") -> tuple:
    """حذف موظف نهائياً مع كل سجلاته المرتبطة."""
    try:
        emp = emp_get(emp_id)
        if not emp:
            return False, "الموظف غير موجود"
        name = emp["full_name"]
        num  = emp["employee_number"]
        with get_db() as conn:
            uid = conn.execute(
                "SELECT id FROM users WHERE username=?", (deleted_by_username,)
            ).fetchone()
            deleted_by = uid["id"] if uid else 1

            conn.execute("PRAGMA foreign_keys=OFF")
            # Delete in FK-safe order
            conn.execute("""
                DELETE FROM payroll_items WHERE line_id IN (
                    SELECT pl.id FROM payroll_lines pl
                    JOIN payroll_periods pp ON pl.period_id = pp.id
                    WHERE pl.employee_id = ?
                )
            """, (emp_id,))
            conn.execute("DELETE FROM payroll_lines WHERE employee_id=?", (emp_id,))
            conn.execute("""
                DELETE FROM advance_instalments WHERE advance_id IN (
                    SELECT id FROM advances WHERE employee_id=?
                )
            """, (emp_id,))
            conn.execute("DELETE FROM advances WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM employee_allowances WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM attendance WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM salary_structures WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM custody_items WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM cash_payments WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM penalties WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM salary_holds WHERE employee_id=?", (emp_id,))
            conn.execute("DELETE FROM employees WHERE id=?", (emp_id,))
            conn.execute("PRAGMA foreign_keys=ON")

            _write_audit(conn, deleted_by, deleted_by_username,
                         "DELETE_EMPLOYEE", "employees",
                         f"حذف نهائي: {num} — {name}")
        return True, f"تم حذف الموظف {num} — {name} نهائياً"
    except Exception as e:
        return False, str(e)


def get_conn():
    """للاستخدام المباشر — يعيد connection."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def rl(rows) -> list:
    """Convert sqlite3.Row or list of Rows to plain dicts. Always returns a list."""
    if rows is None:
        return []
    if isinstance(rows, list):
        return [dict(r) for r in rows]
    # Single sqlite3.Row — wrap in list
    return [dict(rows)]

def get_adjustments_month(month_key: str) -> list:
    """Return one-time adjustments (bounded allowances) for a given month."""
    yr, mo = int(month_key[:4]), int(month_key[5:7])
    eff = f"{month_key}-01"
    last_day = _calendar.monthrange(yr, mo)[1]
    end = f"{month_key}-{last_day:02d}"
    with get_db() as conn:
        rows = conn.execute("""
            SELECT ea.amount, ea.created_at, ea.effective_date, ea.end_date,
                   at.name_ar as description,
                   at.category,
                   e.full_name,
                   CASE WHEN at.category='allowance' THEN 'bonus' ELSE 'deduction' END as adj_type
            FROM employee_allowances ea
            JOIN allowance_types at ON ea.allowance_type_id = at.id
            JOIN employees e ON ea.employee_id = e.id
            WHERE ea.effective_date = ? AND ea.end_date = ?
            ORDER BY ea.created_at DESC
        """, (eff, end)).fetchall()
        return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════════
# الشركاء — Partners & Withdrawals
# ══════════════════════════════════════════════════════════════════

def partner_list() -> list:
    with get_db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM partners ORDER BY id"
        ).fetchall()]


def partner_add(name: str, logged_by: str) -> tuple:
    name = name.strip()
    if not name:
        return False, "الاسم مطلوب"
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO partners(name) VALUES(?)", (name,))
        return True, f"تمت إضافة الشريك '{name}'"
    except Exception as e:
        return False, str(e)


def withdrawal_add(partner_id: int, amount: float, w_date: str,
                   description: str, logged_by: str) -> tuple:
    if amount <= 0:
        return False, "المبلغ يجب أن يكون أكبر من صفر"
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO partner_withdrawals(partner_id,amount,w_date,description,logged_by) VALUES(?,?,?,?,?)",
                (partner_id, amount, w_date, description.strip(), logged_by)
            )
        return True, f"تم تسجيل السحب بنجاح"
    except Exception as e:
        return False, str(e)


def withdrawal_delete(withdrawal_id: int) -> tuple:
    try:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM partner_withdrawals WHERE id=?", (withdrawal_id,)).fetchone()
            if not row:
                return False, "السجل غير موجود"
            conn.execute("DELETE FROM partner_withdrawals WHERE id=?", (withdrawal_id,))
        return True, "تم حذف السجل"
    except Exception as e:
        return False, str(e)


def withdrawal_get(partner_id=None, year=None, month=None) -> list:
    with get_db() as conn:
        q = """
            SELECT pw.*, p.name as partner_name
            FROM partner_withdrawals pw
            JOIN partners p ON pw.partner_id = p.id
            WHERE 1=1
        """
        params = []
        if partner_id:
            q += " AND pw.partner_id=?"; params.append(partner_id)
        if year:
            q += " AND strftime('%Y', pw.w_date)=?"; params.append(str(year))
        if month:
            q += " AND strftime('%m', pw.w_date)=?"; params.append(f"{month:02d}")
        q += " ORDER BY pw.w_date DESC, pw.id DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def withdrawal_summary(year: int) -> list:
    """Returns monthly totals per partner for a given year."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.id as partner_id, p.name as partner_name,
                   strftime('%m', pw.w_date) as month,
                   SUM(pw.amount) as total
            FROM partner_withdrawals pw
            JOIN partners p ON pw.partner_id = p.id
            WHERE strftime('%Y', pw.w_date)=?
            GROUP BY p.id, strftime('%m', pw.w_date)
            ORDER BY p.id, month
        """, (str(year),)).fetchall()
        return [dict(r) for r in rows]


def withdrawal_yearly_totals(year: int) -> list:
    """Returns year-to-date total per partner."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.id as partner_id, p.name as partner_name,
                   COUNT(pw.id) as tx_count,
                   SUM(pw.amount) as total
            FROM partners p
            LEFT JOIN partner_withdrawals pw
                ON pw.partner_id = p.id
                AND strftime('%Y', pw.w_date)=?
            WHERE p.is_active=1
            GROUP BY p.id
            ORDER BY p.id
        """, (str(year),)).fetchall()
        return [dict(r) for r in rows]


def withdrawal_edit(withdrawal_id: int, amount: float, w_date: str,
                    description: str, edited_by: str) -> tuple:
    """Edit an existing withdrawal record."""
    if amount <= 0:
        return False, "المبلغ يجب أن يكون أكبر من صفر"
    try:
        with get_db() as conn:
            row = conn.execute(
                "SELECT id FROM partner_withdrawals WHERE id=?", (withdrawal_id,)
            ).fetchone()
            if not row:
                return False, "السجل غير موجود"
            conn.execute("""
                UPDATE partner_withdrawals
                SET amount=?, w_date=?, description=?, logged_by=?
                WHERE id=?
            """, (amount, w_date, description.strip(), edited_by, withdrawal_id))
        return True, "تم تعديل السجل بنجاح"
    except Exception as e:
        return False, str(e)
