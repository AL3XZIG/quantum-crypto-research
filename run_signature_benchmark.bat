@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found. Create it with: python -m venv .venv
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m experiments.signatures.run_benchmark --repetitions 100
if errorlevel 1 (
  echo.
  echo Benchmark failed. Read the error above.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m experiments.signatures.analyze_results
if errorlevel 1 (
  echo.
  echo Analysis failed. Read the error above.
  pause
  exit /b 1
)
echo.
echo Done. Check data\signature_benchmark.csv and results\
pause
