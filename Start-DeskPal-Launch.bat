@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0deskpal_launch_server.py" --open
    exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0deskpal_launch_server.py" --open
    exit /b
)
echo Python was not found. Use Start-Buddy.bat for setup instructions.
pause
