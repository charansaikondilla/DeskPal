@echo off
title DeskPal
cd /d "%~dp0"

:: Starts the DeskPal service, brings Ganesh onto the desktop and opens
:: the DeskPal app window (no browser tabs, no console window).
::
:: The Windows "py" launcher is installed with Python even when "Add to
:: PATH" was left unticked, so it is tried first. The Microsoft Store
:: "python" alias is skipped on purpose - it only opens the Store.
where pyw >nul 2>&1 && ( start "" /B pyw -3 deskpal_launch_server.py --app & exit /b 0 )
where pythonw >nul 2>&1 && ( start "" /B pythonw deskpal_launch_server.py --app & exit /b 0 )
where py >nul 2>&1 && ( start "" /B py -3 deskpal_launch_server.py --app & exit /b 0 )

echo.
echo   DeskPal needs Python 3. Install it from https://www.python.org/downloads/
echo   (any version 3.10 or newer), then double-click this file again.
echo.
pause
exit /b 1
