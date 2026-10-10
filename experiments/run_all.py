"""Запуск полного прототипа исследования."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(module: str, *args: str) -> None:
    command = [sys.executable, "-m", module, *args]
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    run("experiments.grover.grover_model")
    # Circuit-level Grover sweep (requires qiskit/qiskit-aer; see
    # requirements-quantum.txt). Skipped gracefully when Qiskit is missing.
    try:
        run("experiments.grover.grover_circuit", "--qubits", "4")
    except subprocess.CalledProcessError as exc:
        print(f"Grover circuit simulation skipped: {exc}")
    run("experiments.signatures.run_benchmark", "--repetitions", "100")
    run("experiments.signatures.analyze_results")
    run("experiments.transaction.signature_overhead")


if __name__ == "__main__":
    main()
