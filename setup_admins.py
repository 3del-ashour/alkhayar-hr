"""
setup_admins.py — one-time admin reset.
Creates exactly three admin users (adel, salem, abdo) with the given password,
then deletes every other user. Backs up the database first.

Run on the server:  python setup_admins.py
"""
import os, secrets, hashlib, shutil
from datetime import datetime
import database as db

KEEP = {"adel": "عادل", "salem": "سالم", "abdo": "عبدو"}
PASSWORD = "507799"

def _hash(pw, salt):
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()

DBP = os.environ.get("ALKHAYAR_DB_PATH") or str(db.DB_PATH)

# 1) Back up first
bak = DBP + ".before_admins_" + datetime.now().strftime("%Y%m%d_%H%M%S")
shutil.copy(DBP, bak)
print("✓ Backup created:", bak)

db.init_db()

with db.get_db() as c:
    c.execute("PRAGMA foreign_keys=OFF")

    # 2) Create / reset the three admins
    for uname, dname in KEEP.items():
        salt = secrets.token_hex(16)
        ph = _hash(PASSWORD, salt)
        row = c.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
        if row:
            c.execute("""UPDATE users SET display_name=?, salt=?, password_hash=?,
                         role='admin', is_active=1, failed_attempts=0, locked_until=NULL
                         WHERE username=?""", (dname, salt, ph, uname))
            print(f"  ↻ updated {uname}")
        else:
            c.execute("""INSERT INTO users(username,display_name,salt,password_hash,role,is_active)
                         VALUES(?,?,?,?,'admin',1)""", (uname, dname, salt, ph))
            print(f"  + created {uname}")

    # 3) Delete every other user (detach their audit rows first so history is kept)
    others = [r["id"] for r in c.execute(
        "SELECT id FROM users WHERE username NOT IN (?,?,?)", tuple(KEEP.keys()))]
    for uid in others:
        c.execute("UPDATE audit_log SET user_id=NULL WHERE user_id=?", (uid,))
    c.execute("DELETE FROM users WHERE username NOT IN (?,?,?)", tuple(KEEP.keys()))
    print(f"  − deleted {len(others)} other user(s)")

# 4) Show final state
with db.get_db() as c:
    print("\nFinal users:")
    for r in c.execute("SELECT username, display_name, role FROM users ORDER BY username"):
        print(f"  • {r['username']} | {r['display_name']} | {r['role']}")
print("\nDone. All three log in with password:", PASSWORD)
