"""
smart_backup.py — daily backup that only runs when the data actually changed.

- Makes a clean single-file snapshot (folds the WAL, canonical form).
- Hashes it and compares to the last backup's hash.
- If identical  -> does nothing (no duplicate copies).
- If different   -> saves alkhayar_<timestamp>.db in the backups dir,
                    optionally mirrors it to ALKHAYAR_BACKUP_MIRROR,
                    and prunes to the newest KEEP files.

Run:  python smart_backup.py
"""
import sys, os, hashlib, shutil, sqlite3, glob
from datetime import datetime

# make importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import database as db

DBP    = os.environ.get("ALKHAYAR_DB_PATH")    or str(db.DB_PATH)
BAK    = os.environ.get("ALKHAYAR_BACKUP_DIR") or str(db.BACKUP_DIR)
MIRROR = os.environ.get("ALKHAYAR_BACKUP_MIRROR")   # optional 2nd copy (e.g. Google Drive folder)
KEEP   = 60

os.makedirs(BAK, exist_ok=True)

# 1) clean single-file snapshot
tmp = os.path.join(BAK, ".snapshot.tmp")
if os.path.exists(tmp):
    os.remove(tmp)
conn = sqlite3.connect(DBP)
conn.execute("PRAGMA wal_checkpoint(FULL)")
conn.execute(f"VACUUM INTO '{tmp}'")
conn.close()

# 2) hash + compare
def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

new_hash = _sha(tmp)
marker = os.path.join(BAK, ".last_hash")
last_hash = open(marker).read().strip() if os.path.exists(marker) else ""

if new_hash == last_hash:
    os.remove(tmp)
    print(datetime.now().strftime("%Y-%m-%d %H:%M"), "- no changes since last backup, skipped.")
    sys.exit(0)

# 3) save the new backup
stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
dest = os.path.join(BAK, f"alkhayar_{stamp}.db")
shutil.move(tmp, dest)
with open(marker, "w") as f:
    f.write(new_hash)
print(datetime.now().strftime("%Y-%m-%d %H:%M"), "- backup created:", dest)

# 4) optional mirror to a second location
if MIRROR and os.path.isdir(MIRROR):
    try:
        shutil.copy(dest, os.path.join(MIRROR, f"alkhayar_{stamp}.db"))
        print("   mirrored to:", MIRROR)
    except Exception as e:
        print("   mirror failed:", e)

# 5) prune to newest KEEP
files = sorted(glob.glob(os.path.join(BAK, "alkhayar_*.db")))
for old in files[:-KEEP]:
    try:
        os.remove(old)
    except OSError:
        pass
