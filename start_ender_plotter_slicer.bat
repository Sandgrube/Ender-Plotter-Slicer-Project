@echo off
chcp 65001 >nul
setlocal EnableExtensions
title Ender Plotter Slicer - Launcher

REM ============================================================
REM  Ender Plotter Slicer launcher for Windows
REM  Put this file in the repository root and double-click it.
REM  It creates a local .venv folder, installs dependencies,
REM  verifies the imports, and starts the application.
REM ============================================================

cd /d "%~dp0"

if exist "main.py" goto :project_found
if exist "ender_plotter_slicer\__init__.py" goto :project_found

echo.
echo [ERROR] Repository root not found.
echo This batch file must be located next to main.py and the ender_plotter_slicer package folder.
echo.
pause
exit /b 1

:project_found
echo.
echo [OK] Project folder: %CD%

if not exist "requirements.txt" (
    echo.
    echo [ERROR] requirements.txt is missing.
    echo The launcher cannot install PySide6, svgpathtools, matplotlib and Pillow without it.
    echo.
    pause
    exit /b 1
)

set "PY_CMD="
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"

if not defined PY_CMD (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo.
    echo [ERROR] No suitable Python installation found.
    echo Install Python 3.10 or newer and enable "Add python.exe to PATH" in the installer.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python found: %PY_CMD%

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [INFO] Creating local virtual environment: .venv
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo.
        echo [ERROR] Could not create the virtual environment.
        echo Check your Python installation and folder permissions.
        echo.
        pause
        exit /b 1
    )
)

set "VPY=%CD%\.venv\Scripts\python.exe"

echo.
echo [INFO] Installing Python dependencies...
"%VPY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    echo.
    echo [ERROR] pip could not be updated.
    echo Check internet access, antivirus restrictions, or write permissions.
    echo.
    pause
    exit /b 1
)

"%VPY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Dependencies could not be installed.
    echo Typical causes: no internet connection or an incompatible Python version.
    echo.
    pause
    exit /b 1
)

echo.
echo [INFO] Verifying imports...
"%VPY%" -c "import PySide6, svgpathtools, matplotlib, PIL; print('Imports OK')"
if errorlevel 1 (
    echo.
    echo [ERROR] At least one required Python package cannot be imported.
    echo Delete the .venv folder and run this launcher again.
    echo.
    pause
    exit /b 1
)

echo.
echo [START] Launching Ender Plotter Slicer...
echo Keep this console window open while the app is running.
echo.
"%VPY%" -m ender_plotter_slicer
set "APP_EXIT=%ERRORLEVEL%"

echo.
if "%APP_EXIT%"=="0" (
    echo [OK] Application closed normally.
) else (
    echo [ERROR] Application exited with error code %APP_EXIT%.
    echo Read the error message above this line.
)

echo.
pause
exit /b %APP_EXIT%
