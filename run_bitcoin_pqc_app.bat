@echo off
setlocal
cd /d "%~dp0"
python -m pip install -r requirements-app.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)
python -m streamlit run app_bitcoin_pqc.py
if errorlevel 1 pause
