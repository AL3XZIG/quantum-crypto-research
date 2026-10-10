"""Small-scale Grover circuit simulation using Qiskit Aer.

This is a circuit-level simulation of a toy search problem, not a cryptographic attack.
The simulator's cost grows exponentially with the number of qubits.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_CSV = ROOT / "data" / "grover_circuit_results.csv"
OUTPUT_PLOT = ROOT / "results" / "figures" / "grover_success_probability.png"


def optimal_iterations(qubits: int, marked_states: int = 1) -> int:
    """Return the usual approximate Grover iteration count."""
    if qubits < 1:
        raise ValueError("qubits must be >= 1")
    space = 2**qubits
    if not 1 <= marked_states <= space:
        raise ValueError("marked_states must be between 1 and 2**qubits")
    return max(0, int(math.floor((math.pi / 4) * math.sqrt(space / marked_states))))


def theoretical_success_probability(
    qubits: int, iterations: int, marked_states: int = 1
) -> float:
    """Ideal success probability after Grover iterations for M marked states."""
    if qubits < 1 or iterations < 0:
        raise ValueError("qubits must be >= 1 and iterations must be >= 0")
    space = 2**qubits
    if not 1 <= marked_states <= space:
        raise ValueError("marked_states must be between 1 and 2**qubits")
    theta = math.asin(math.sqrt(marked_states / space))
    return math.sin((2 * iterations + 1) * theta) ** 2


def build_grover_circuit(qubits: int, target: str, iterations: int):
    """Build a Grover circuit marking exactly one computational-basis bitstring."""
    if qubits < 2:
        raise ValueError("Use at least 2 qubits for this implementation")
    if len(target) != qubits or any(bit not in "01" for bit in target):
        raise ValueError("target must be a bitstring whose length equals --qubits")
    if iterations < 0:
        raise ValueError("iterations must be >= 0")

    # Optional dependencies are imported here so the math helpers remain testable
    # without installing Qiskit.
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(qubits, qubits)
    circuit.h(range(qubits))

    def oracle() -> None:
        # Qiskit displays measurement strings as q_(n-1)...q_0.
        # Flip zero bits so the requested target maps to |11...1>.
        for qubit, bit in enumerate(target[::-1]):
            if bit == "0":
                circuit.x(qubit)
        circuit.h(qubits - 1)
        circuit.mcx(list(range(qubits - 1)), qubits - 1)
        circuit.h(qubits - 1)
        for qubit, bit in enumerate(target[::-1]):
            if bit == "0":
                circuit.x(qubit)

    def diffuser() -> None:
        circuit.h(range(qubits))
        circuit.x(range(qubits))
        circuit.h(qubits - 1)
        circuit.mcx(list(range(qubits - 1)), qubits - 1)
        circuit.h(qubits - 1)
        circuit.x(range(qubits))
        circuit.h(range(qubits))

    for _ in range(iterations):
        oracle()
        diffuser()

    circuit.measure(range(qubits), range(qubits))
    return circuit


def run_sweep(
    qubits: int = 4,
    target: str | None = None,
    shots: int = 2048,
    seed: int = 42,
) -> list[dict]:
    """Simulate iteration counts around the theoretical optimum."""
    if qubits < 2 or qubits > 12:
        raise ValueError("qubits must be between 2 and 12 for this demo")
    if shots < 1:
        raise ValueError("shots must be >= 1")
    target = target if target is not None else "1" * qubits
    if len(target) != qubits or any(bit not in "01" for bit in target):
        raise ValueError("target must be a bitstring whose length equals --qubits")

    try:
        from qiskit import transpile
        from qiskit_aer import AerSimulator
    except ImportError as exc:
        raise RuntimeError(
            "Qiskit is optional. Install it with: "
            "python -m pip install -r requirements-quantum.txt"
        ) from exc

    simulator = AerSimulator()
    optimum = optimal_iterations(qubits)
    max_iterations = min(optimum + 2, 2 * optimum + 1)
    rows: list[dict] = []

    for iterations in range(max_iterations + 1):
        circuit = build_grover_circuit(qubits, target, iterations)
        compiled = transpile(circuit, simulator, optimization_level=0)
        result = simulator.run(
            compiled, shots=shots, seed_simulator=seed + iterations
        ).result()
        counts = result.get_counts()
        target_count = int(counts.get(target, 0))
        rows.append({
            "qubits": qubits,
            "search_space": 2**qubits,
            "target": target,
            "iterations": iterations,
            "shots": shots,
            "target_count": target_count,
            "empirical_success_probability": target_count / shots,
            "theoretical_success_probability": theoretical_success_probability(
                qubits, iterations
            ),
            "theoretical_optimal_iterations": optimum,
        })

    return rows


def save_csv(rows: list[dict], path: Path = OUTPUT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("Cannot save an empty result set")
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def save_plot(rows: list[dict], path: Path = OUTPUT_PLOT) -> None:
    import matplotlib.pyplot as plt

    path.parent.mkdir(parents=True, exist_ok=True)
    iterations = [row["iterations"] for row in rows]
    empirical = [row["empirical_success_probability"] for row in rows]
    theoretical = [row["theoretical_success_probability"] for row in rows]

    plt.figure(figsize=(8, 5))
    plt.plot(iterations, theoretical, marker="o", label="Ideal theoretical probability")
    plt.plot(iterations, empirical, marker="x", linestyle="--", label="Aer simulation")
    plt.xlabel("Grover iterations")
    plt.ylabel("Probability of measuring the target")
    plt.ylim(0, 1.05)
    plt.title(f"Grover search: {rows[0]['qubits']} qubits, target={rows[0]['target']}")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a small-scale Grover circuit simulation with Qiskit Aer."
    )
    parser.add_argument("--qubits", type=int, default=4, help="Number of qubits (2..12)")
    parser.add_argument("--target", type=str, default=None, help="Target bitstring; defaults to all ones")
    parser.add_argument("--shots", type=int, default=2048, help="Measurements per iteration count")
    parser.add_argument("--seed", type=int, default=42, help="Base simulator seed")
    args = parser.parse_args()

    rows = run_sweep(args.qubits, args.target, args.shots, args.seed)
    save_csv(rows)
    save_plot(rows)
    optimum = optimal_iterations(args.qubits)
    best = max(rows, key=lambda row: row["empirical_success_probability"])
    print(f"Qubits: {args.qubits}; search space: {2**args.qubits}; target: {rows[0]['target']}")
    print(f"Theoretical optimal iterations: {optimum}")
    print(
        f"Best measured result: {best['iterations']} iterations, "
        f"success={best['empirical_success_probability']:.3f}, "
        f"theory={best['theoretical_success_probability']:.3f}"
    )
    print(f"CSV: {OUTPUT_CSV}")
    print(f"Plot: {OUTPUT_PLOT}")
    print("Note: this is a small toy search, not a break of a real cryptographic system.")


if __name__ == "__main__":
    main()
