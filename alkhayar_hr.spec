# alkhayar_hr.spec — PyInstaller spec for الخيار HR v4
# Run with:  pyinstaller alkhayar_hr.spec

import sys
from pathlib import Path

block_cipher = None
BASE = Path(SPECPATH)          # directory containing this .spec file

a = Analysis(
    [str(BASE / "launcher.py")],
    pathex=[str(BASE)],
    binaries=[],
    datas=[
        # App source files
        (str(BASE / "app.py"),              "."),
        (str(BASE / "database.py"),         "."),
        (str(BASE / "payslip_pdf.py"),      "."),
        (str(BASE / "withdrawals_pdf.py"),  "."),
        # Assets (logo, etc.)
        (str(BASE / "assets"),              "assets"),
        # Streamlit static files (required for offline use)
        (
            str(Path(sys.exec_prefix) / "Lib" / "site-packages" / "streamlit" / "static"),
            "streamlit/static",
        ),
        (
            str(Path(sys.exec_prefix) / "Lib" / "site-packages" / "streamlit" / "runtime"),
            "streamlit/runtime",
        ),
    ],
    hiddenimports=[
        # Streamlit internals
        "streamlit",
        "streamlit.runtime.scriptrunner.magic_funcs",
        "streamlit.web.cli",
        # Database
        "sqlite3",
        # PDF generation
        "reportlab",
        "reportlab.pdfbase.ttfonts",
        "reportlab.pdfbase.cidfonts",
        "reportlab.platypus",
        "reportlab.lib.pagesizes",
        "reportlab.lib.units",
        "reportlab.lib.colors",
        "reportlab.lib.styles",
        # Arabic text
        "arabic_reshaper",
        "bidi",
        "bidi.algorithm",
        # Data
        "pandas",
        "openpyxl",
        # WebView
        "webview",
        # Other
        "packaging",
        "packaging.version",
        "packaging.specifiers",
        "packaging.requirements",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "notebook", "IPython", "PIL.ImageQt"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # use COLLECT (folder output)
    name="AlkhayarHR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # no console window
    icon=str(BASE / "assets" / "sa_logo.ico") if (BASE / "assets" / "sa_logo.ico").exists() else None,
    version_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AlkhayarHR",
)
