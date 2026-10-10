"""Общие структуры и утилиты бенчмарка цифровых подписей."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev
from time import perf_counter
from typing import Callable


@dataclass
class BenchmarkResult:
    algorithm: str
    parameter: str
    keygen_ms: float
    sign_ms: float
    verify_ms: float
    public_key_bytes: int
    private_key_bytes: int
    signature_bytes: int


def measure_ms(
    function: Callable[[], object],
    repetitions: int = 100,
    warmup: int = 5,
) -> float:
    """Return the arithmetic mean execution time in milliseconds.

    Warm-up calls are excluded from the measurement. The function is invoked
    once per repetition so that every timing sample represents one operation.
    """
    if repetitions < 1:
        raise ValueError("repetitions must be >= 1")
    if warmup < 0:
        raise ValueError("warmup must be >= 0")

    for _ in range(warmup):
        function()

    # Accumulate the total elapsed time instead of materialising a list of
    # per-sample timings. This keeps memory usage O(1) and avoids the cost of
    # building and traversing an intermediate list for large repetition
    # counts, while producing exactly the same arithmetic mean.
    total_ms = 0.0
    for _ in range(repetitions):
        start = perf_counter()
        function()
        total_ms += (perf_counter() - start) * 1000

    return total_ms / repetitions


def measure_ms_with_stats(
    function: Callable[[], object],
    repetitions: int = 100,
    warmup: int = 5,
) -> tuple[float, float]:
    """Return mean and sample standard deviation in milliseconds."""
    if repetitions < 2:
        raise ValueError("repetitions must be >= 2")

    for _ in range(warmup):
        function()

    samples = []
    for _ in range(repetitions):
        start = perf_counter()
        function()
        samples.append((perf_counter() - start) * 1000)

    return mean(samples), stdev(samples)
