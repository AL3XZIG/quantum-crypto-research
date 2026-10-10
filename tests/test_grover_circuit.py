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
