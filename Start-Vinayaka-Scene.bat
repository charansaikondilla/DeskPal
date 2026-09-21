@echo off
cd /d "%~dp0"
pyw -3 "%~dp0deskpal.py" --desktop-launch --modak-scene
if errorlevel 1 (
    echo Could not start DeskPal. Use Start-DeskPal.bat, then Settings - Emotes.
    pause
)
