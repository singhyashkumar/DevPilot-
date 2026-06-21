@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================================================
echo   DevPilot - Premium Repository Intelligence Dashboard
echo ================================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [DevPilot] Creating isolated Python environment for first run...
    py -m venv .venv
    if errorlevel 1 goto :venv_error
)

".venv\Scripts\python.exe" run.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo DevPilot stopped with exit code %EXIT_CODE%.
    pause
)
endlocal
exit /b %EXIT_CODE%

:venv_error
echo.
echo [DevPilot] Could not create .venv with the Python launcher.
echo Install Python 3.10+ from python.org, reopen this folder, and run this file again.
pause
endlocal
exit /b 1
