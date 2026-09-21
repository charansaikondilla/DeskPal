@echo off
title DeskPal - troubleshooting
cd /d "%~dp0"

echo ============================================================
echo   DeskPal troubleshooting
echo ============================================================
echo.
echo This window starts your buddy WITH a console so you can see
echo any message it prints.  Keep this window open while testing.
echo.

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
    echo   Python was not found on this computer.
    echo   Install it from https://www.python.org/downloads/
    echo   and tick "Add python.exe to PATH" during setup.
    echo.
    pause
    exit /b 1
)

echo Using: %PY%
%PY% -c "import sys; print('Python', sys.version)"
%PY% -c "import tkinter; print('tkinter OK, version', tkinter.TkVersion)"
echo.
echo Starting the buddy.  Close this window to stop it.
echo.
%PY% "%~dp0deskpal.py" --no-lock

echo.
echo The buddy has stopped.
echo A detailed log is kept in:  %%APPDATA%%\DeskPal\log.txt
echo.
pause
