import math

import pytest

from experiments.grover.grover_circuit import (
    build_grover_circuit,
    optimal_iterations,
    theoretical_success_probability,
)


def test_optimal_iterations_for_four_qubits():
    assert optimal_iterations(4) == 3


def test_grover_probability_matches_known_four_qubit_case():
    expected = math.sin(7 * math.asin(1 / 4)) ** 2
    assert theoretical_success_probability(4, 3) == pytest.approx(expected)


def test_target_validation():
    with pytest.raises(ValueError):
        build_grover_circuit(4, "101", 1)


def test_circuit_has_measurements_when_qiskit_is_installed():
    pytest.importorskip("qiskit")
    circuit = build_grover_circuit(3, "101", 1)
    assert circuit.num_qubits == 3
    assert circuit.num_clbits == 3
    assert circuit.count_ops().get("measure", 0) == 3


def test_run_sweep_with_aer_returns_expected_rows():
    """Actually execute the batched Aer sweep and validate its structure."""
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")

    from experiments.grover.grover_circuit import run_sweep

    qubits, shots = 3, 512
    rows = run_sweep(qubits=qubits, shots=shots, seed=42)
    optimum = optimal_iterations(qubits)

    # One row per iteration count from 0 up to the sweep maximum.
    assert len(rows) == min(optimum + 2, 2 * optimum + 1) + 1
    assert [row["iterations"] for row in rows] == list(range(len(rows)))
    for row in rows:
        assert row["qubits"] == qubits
        assert row["search_space"] == 2**qubits
        assert row["target"] == "1" * qubits
        assert row["shots"] == shots
        assert 0 <= row["target_count"] <= shots
        assert 0.0 <= row["empirical_success_probability"] <= 1.0
        assert row["theoretical_success_probability"] == pytest.approx(
            theoretical_success_probability(qubits, row["iterations"])
        )

    # At the optimal iteration count the empirical probability should be high
    # and close to the theoretical prediction.
    best_row = max(rows, key=lambda row: row["theoretical_success_probability"])
    assert best_row["empirical_success_probability"] > 0.7
    assert abs(
        best_row["empirical_success_probability"]
        - best_row["theoretical_success_probability"]
    ) < 0.15


def test_run_sweep_is_reproducible_with_same_seed():
    """The same seed must yield byte-identical results across runs."""
    pytest.importorskip("qiskit")
    pytest.importorskip("qiskit_aer")

    from experiments.grover.grover_circuit import run_sweep

    first = run_sweep(qubits=2, shots=256, seed=7)
    second = run_sweep(qubits=2, shots=256, seed=7)
    assert first == second
