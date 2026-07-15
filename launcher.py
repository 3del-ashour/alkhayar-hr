"""
launcher.py — Desktop launcher for الخيار HR v4
Opens the Streamlit app in a native window (no browser, no terminal).
Bundled with PyInstaller → wrapped by Inno Setup into AlkhayarHR_Setup.exe

Data storage strategy (best practice):
  • App files  → wherever the user installed (e.g. C:\Program Files\AlkhayarHR)  [READ-ONLY after install]
  • User data  → %APPDATA%\AlkhayarHR\   [writable, survives app updates/reinstalls]
"""

import sys
import os
import threading
import time
import socket
import subprocess
import webview

# ── Resolve base path (works both in dev and after PyInstaller bundles) ────────
if getattr(sys, "frozen", False):
    BASE_DIR = sys._MEIPASS          # read-only bundle extracted by PyInstaller
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_SCRIPT = os.path.join(BASE_DIR, "app.py")
PORT       = 8501
URL        = f"http://127.0.0.1:{PORT}"

# ── Data directory: %APPDATA%\AlkhayarHR  (writable, user-specific) ───────────
# On Windows:  C:\Users\<username>\AppData\Roaming\AlkhayarHR
# In dev mode: same folder as the script
if getattr(sys, "frozen", False):
    _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    DATA_DIR = os.path.join(_appdata, "AlkhayarHR")
else:
    DATA_DIR = BASE_DIR

os.environ["ALKHAYAR_DB_PATH"]    = os.path.join(DATA_DIR, "hr_data", "alkhayar_hr.db")
os.environ["ALKHAYAR_BACKUP_DIR"] = os.path.join(DATA_DIR, "backups")

os.makedirs(os.path.join(DATA_DIR, "hr_data"), exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "backups"), exist_ok=True)


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    """Return True if something is listening on host:port."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _start_streamlit():
    """Launch Streamlit as a subprocess (hidden on Windows)."""
    creationflags = 0
    if sys.platform == "win32":
        # CREATE_NO_WINDOW — hides the console window
        creationflags = 0x08000000

    subprocess.Popen(
        [
            sys.executable, "-m", "streamlit", "run", APP_SCRIPT,
            "--server.port", str(PORT),
            "--server.headless", "true",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "false",
            "--browser.gatherUsageStats", "false",
            "--theme.base", "light",
        ],
        cwd=BASE_DIR,
        creationflags=creationflags,
    )


def _wait_for_server(timeout: int = 30):
    """Block until Streamlit is up, or raise after timeout seconds."""
    start = time.time()
    while time.time() - start < timeout:
        if _port_open(PORT):
            return
        time.sleep(0.3)
    raise RuntimeError(f"Streamlit did not start within {timeout}s")


def main():
    # Start Streamlit in background thread
    t = threading.Thread(target=_start_streamlit, daemon=True)
    t.start()

    # Show a simple loading splash while we wait
    # (webview window opens as soon as server is ready)
    _wait_for_server()

    # Open native desktop window
    webview.create_window(
        title="الخيار للسيارات — نظام الموارد البشرية",
        url=URL,
        width=1280,
        height=820,
        min_size=(900, 600),
        resizable=True,
        text_select=True,
    )
    webview.start(debug=False)


if __name__ == "__main__":
    main()
