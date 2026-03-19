@echo off
echo ============================================
echo   WASA Tournaments - Server Setup
echo ============================================
echo.

:: Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Download it from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [2/3] Installing dependencies...
python -m pip install -r requirements.txt

echo.
echo [3/3] Done!
echo.
echo To start the server, run:
echo   python app.py
echo.
pause
