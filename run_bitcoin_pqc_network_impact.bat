@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment not found.
    echo Create it with: python -m venv .venv
    echo Then install dependencies: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo ==========================================
echo Bitcoin PQC - Network Impact Experiment
echo ==========================================
echo.
".venv\Scripts\python.exe" -m experiments.transaction.bitcoin_pqc_network_impact %*
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo Experiment completed.
    echo See results\bitcoin_pqc_network_impact_report.md
) else (
    echo Experiment failed with exit code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
