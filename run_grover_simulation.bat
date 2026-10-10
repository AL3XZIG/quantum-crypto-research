@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment not found.
  echo Create it with: python -m venv .venv
  echo Then install quantum dependencies with:
  echo .venv\Scripts\python.exe -m pip install -r requirements-quantum.txt
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m experiments.grover.grover_circuit --qubits 4 --shots 2048
if errorlevel 1 (
  echo.
  echo Simulation failed. Read the error above.
  pause
  exit /b 1
)
echo.
echo Simulation completed. Check data\grover_circuit_results.csv
echo and results\figures\grover_success_probability.png
pause
