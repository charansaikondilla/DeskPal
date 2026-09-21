@echo off
setlocal enabledelayedexpansion
title DeskPal launcher
cd /d "%~dp0"

rem ===================================================================
rem   DeskPal - double-click this file to wake up your desktop buddy
rem ===================================================================

set "PY="

rem 1) the Windows python launcher (installed with python.org builds)
where pyw >nul 2>&1 && set "PY=pyw -3"
if not defined PY (
    where pythonw >nul 2>&1 && set "PY=pythonw"
)
if not defined PY (
    where py >nul 2>&1 && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)

rem 2) common install locations, in case PATH was never set up
if not defined PY (
    for %%P in (
        "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
        "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
        "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
        "%LOCALAPPDATA%\Programs\Python\Python310\pythonw.exe"
        "%ProgramFiles%\Python313\pythonw.exe"
        "%ProgramFiles%\Python312\pythonw.exe"
        "%ProgramFiles%\Python311\pythonw.exe"
        "%ProgramFiles%\Python310\pythonw.exe"
    ) do (
        if not defined PY if exist %%P set "PY=%%P"
    )
)

if not defined PY goto :nopython

start "" %PY% "%~dp0deskpal.py"
exit /b 0

:nopython
echo.
echo   =====================================================
echo     Python is not installed yet - it is free and quick
echo   =====================================================
echo.
echo   1. Go to     https://www.python.org/downloads/
echo   2. Download Python for Windows and run the installer
echo   3. IMPORTANT: tick  "Add python.exe to PATH"  on the
echo      first screen of the installer
echo   4. Finish the install, then double-click this file again
echo.
echo   (Nothing else is needed - your buddy uses only what
echo    comes with Python.)
echo.
pause
exit /b 1
