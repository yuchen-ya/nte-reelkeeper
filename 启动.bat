@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Please run install.ps1 with Python 3.12 or newer first.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "main.py"
