@echo off
chcp 65001 > nul
title Build Pipeline — الخيار HR v4

echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║         AlkhayarHR — Build Pipeline v4.0            ║
echo ║    PyInstaller + Inno Setup → AlkhayarHR_Setup.exe  ║
echo ╚══════════════════════════════════════════════════════╝
echo.

REM ── Verify Python ─────────────────────────────────────────────────────────────
python --version > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo         Install Python 3.11+ from https://www.python.org/
    echo         Make sure to check "Add Python to PATH" during install.
    pause & exit /b 1
)
for /f "tokens=*" %%i in ('python --version') do echo [OK] %%i detected

REM ── Step 1 — Install / upgrade all required packages ─────────────────────────
echo.
echo [STEP 1/4] Installing Python packages...
python -m pip install --upgrade pip --quiet
python -m pip install --upgrade ^
    streamlit ^
    pyinstaller ^
    pywebview ^
    reportlab ^
    arabic-reshaper ^
    python-bidi ^
    pandas ^
    openpyxl ^
    pillow ^
    --quiet
if errorlevel 1 (
    echo [ERROR] Package installation failed. Check internet connection.
    pause & exit /b 1
)
echo [OK] All packages installed.

REM ── Step 2 — Convert logo PNG to ICO ─────────────────────────────────────────
echo.
echo [STEP 2/4] Converting logo PNG to ICO...
python -c "from PIL import Image; img=Image.open('assets/sa_logo.png').convert('RGBA'); img.save('assets/sa_logo.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>nul
if exist "assets\sa_logo.ico" (
    echo [OK] assets\sa_logo.ico created.
    REM Patch spec and iss to use the icon
    powershell -Command "(Get-Content 'alkhayar_hr.spec') -replace '^# icon=.*', 'icon=str(BASE / \"assets\" / \"sa_logo.ico\"),' | Set-Content 'alkhayar_hr.spec'" 2>nul
    powershell -Command "(Get-Content 'installer.iss') -replace '^; SetupIconFile=', 'SetupIconFile=' | Set-Content 'installer.iss'" 2>nul
) else (
    echo [WARN] Could not create .ico — app will use default Windows icon. Continuing...
)

REM ── Step 3 — PyInstaller: bundle into dist\AlkhayarHR\ ────────────────────────
echo.
echo [STEP 3/4] Running PyInstaller (this takes 3-6 minutes)...
pyinstaller alkhayar_hr.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERROR] PyInstaller failed. See output above.
    pause & exit /b 1
)
echo [OK] App bundled to dist\AlkhayarHR\

REM ── Step 4 — Inno Setup: wrap into single Setup.exe ─────────────────────────
echo.
echo [STEP 4/4] Looking for Inno Setup compiler...

REM Common Inno Setup install paths
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe"       set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"

if %ISCC%=="" (
    echo.
    echo [WARN] Inno Setup not found. Skipping installer creation.
    echo        To create a proper Windows installer:
    echo          1. Download Inno Setup from: https://jrsoftware.org/isdl.php
    echo          2. Install it, then re-run this script.
    echo.
    echo [INFO] You can still distribute the app by copying:
    echo          dist\AlkhayarHR\  (the whole folder)
    echo        to the target PC and running AlkhayarHR.exe
    echo.
) else (
    echo [OK] Inno Setup found at %ISCC%
    mkdir installer_output 2>nul
    %ISCC% installer.iss
    if errorlevel 1 (
        echo [ERROR] Inno Setup failed. See output above.
        pause & exit /b 1
    )
    echo [OK] Installer created.
    for %%f in (installer_output\*.exe) do echo [FILE] %%f
)

REM ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo ╔══════════════════════════════════════════════════════╗
echo ║                    BUILD COMPLETE                   ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  App folder  : dist\AlkhayarHR\AlkhayarHR.exe       ║
echo ║  Installer   : installer_output\AlkhayarHR_Setup_*  ║
echo ╠══════════════════════════════════════════════════════╣
echo ║  Deploy: send AlkhayarHR_Setup_v4.0.exe to the PC   ║
echo ║  Install: double-click → Next → Finish → Done       ║
echo ╚══════════════════════════════════════════════════════╝
echo.
pause
