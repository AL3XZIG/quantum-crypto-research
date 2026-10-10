@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    echo Create it with: python -m venv .venv
    pause
    exit /b 1
)

echo ==========================================
echo Quantum Crypto Research - Full Automation
echo ==========================================
echo.
".venv\Scripts\python.exe" -m experiments.automation %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Automation completed successfully.
    echo Check results\report.md
) else (
    echo Automation failed with exit code %EXIT_CODE%.
    echo Check the terminal output and results\logs\
)

pause
exit /b %EXIT_CODE%
