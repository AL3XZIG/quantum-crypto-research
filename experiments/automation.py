"""Run research experiments and collect timestamped artifacts.

The current benchmark API returns per-series means, not every operation's timing
sample. Raw files below preserve independent series results, not per-operation data.
"""
from __future__ import annotations

import argparse
import csv
import importlib.metadata
import math
import platform
import statistics
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from shutil import copy2

from experiments.signatures.ecdsa_benchmark import benchmark as benchmark_ecdsa
from experiments.signatures.mldsa_benchmark import benchmark as benchmark_mldsa

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RAW = RESULTS / "raw"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"
LOGS = RESULTS / "logs"

METRICS = ("keygen_ms", "sign_ms", "verify_ms", "public_key_bytes",
           "private_key_bytes", "signature_bytes")
T_CRITICAL = {
    2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
    8: 2.365, 9: 2.306, 10: 2.262, 11: 2.228, 12: 2.201, 13: 2.179,
    14: 2.160, 15: 2.145, 16: 2.131, 17: 2.120, 18: 2.110, 19: 2.101,
    20: 2.093, 21: 2.086, 22: 2.080, 23: 2.074, 24: 2.069, 25: 2.064,
    26: 2.060, 27: 2.056, 28: 2.052, 29: 2.048, 30: 2.045,
}


def make_dirs() -> None:
    for path in (DATA, RAW, TABLES, FIGURES, LOGS):
        path.mkdir(parents=True, exist_ok=True)


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not installed"


def save_environment(stamp: str) -> Path:
    packages = ("cryptography", "liboqs-python", "matplotlib", "pandas",
                "qiskit", "qiskit-aer", "pytest")
    lines = [
        f"Timestamp UTC: {datetime.now(timezone.utc).isoformat()}",
        f"Python: {sys.version.replace(chr(10), ' ')}",
        f"Platform: {platform.platform()}",
        "",
        "Package versions:",
        *[f"- {name}: {version(name)}" for name in packages],
    ]
    path = LOGS / f"environment_{stamp}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def ci95(values: list[float]) -> tuple[float, float]:
    avg = statistics.mean(values)
    n = len(values)
    if n < 2:
        return avg, avg
    # For n > 30, 1.96 is a close normal approximation.
    critical = T_CRITICAL.get(n, 1.96)
    margin = critical * statistics.stdev(values) / math.sqrt(n)
    return avg - margin, avg + margin


def run_benchmarks(stamp: str, runs: int, repetitions: int) -> list[dict]:
    rows = []
    mldsa_repetitions = max(30, repetitions // 2)
    for run_id in range(1, runs + 1):
        print(f"[{run_id}/{runs}] ECDSA benchmark...")
        results = [benchmark_ecdsa(repetitions=repetitions)]
        print(f"[{run_id}/{runs}] ML-DSA-65 benchmark...")
        results.append(benchmark_mldsa(repetitions=mldsa_repetitions))
        run_rows = []
        for result in results:
            row = asdict(result)
            row.update({
                "run_id": run_id,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "ecdsa_repetitions": repetitions,
                "mldsa_repetitions": mldsa_repetitions,
            })
            rows.append(row)
            run_rows.append(row)
        path = RAW / f"signature_benchmark_{stamp}_run{run_id:02d}.csv"
        write_csv(path, run_rows)
        print(f"Saved {path.relative_to(ROOT)}")
    return rows


def summarize(rows: list[dict]) -> Path:
    aggregate_rows, stats_rows = [], []
    for algorithm in sorted({row["algorithm"] for row in rows}):
        selected = [row for row in rows if row["algorithm"] == algorithm]
        aggregate = {"algorithm": algorithm, "parameter": selected[0]["parameter"]}
        for metric in METRICS:
            values = [float(row[metric]) for row in selected]
            aggregate[metric] = (
                statistics.mean(values) if metric.endswith("_ms")
                else int(round(statistics.median(values)))
            )
            low, high = ci95(values)
            stats_rows.append({
                "algorithm": algorithm, "parameter": selected[0]["parameter"],
                "metric": metric, "independent_runs": len(values),
                "mean": statistics.mean(values), "median": statistics.median(values),
                "sample_sd": statistics.stdev(values) if len(values) > 1 else 0.0,
                "ci95_low": low, "ci95_high": high,
            })
        aggregate_rows.append(aggregate)
    write_csv(DATA / "signature_benchmark.csv", aggregate_rows)
    path = TABLES / "signature_benchmark_statistics.csv"
    write_csv(path, stats_rows)
    return path


def run_module(module: str, stamp: str, extra_args: list[str] | None = None):
    log = LOGS / f"{module.replace('.', '_')}_{stamp}.txt"
    command = [sys.executable, "-m", module, *(extra_args or [])]
    result = subprocess.run(command, cwd=ROOT, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            check=False)
    log.write_text(result.stdout or "", encoding="utf-8")
    print((result.stdout or "").strip())
    print(f"{module}: {'OK' if result.returncode == 0 else 'FAILED'}; log: {log.relative_to(ROOT)}")
    return result.returncode, log


def run_grover(stamp: str, qubits: int, shots: int) -> str:
    try:
        import qiskit  # noqa: F401
        import qiskit_aer  # noqa: F401
    except ImportError:
        return "SKIPPED: optional Qiskit / Qiskit Aer packages are not installed."
    code, log = run_module(
        "experiments.grover.grover_circuit", stamp,
        ["--qubits", str(qubits), "--shots", str(shots)],
    )
    if code:
        return f"FAILED: see {log.relative_to(ROOT)}"
    source = DATA / "grover_circuit_results.csv"
    if source.exists():
        target = RAW / f"grover_circuit_{stamp}.csv"
        copy2(source, target)
        return f"OK; timestamped CSV copy: {target.relative_to(ROOT)}"
    return "FAILED: expected simulation CSV was not created."


def run_tests(stamp: str):
    log = LOGS / f"pytest_{stamp}.txt"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    log.write_text(result.stdout or "", encoding="utf-8")
    print(result.stdout or "")
    return result.returncode, log


def write_report(stamp: str, runs: int, repetitions: int, stats_path: Path,
                 grover_status: str, test_code: int, test_log: Path) -> Path:
    comparison_path = TABLES / "comparison_summary.csv"
    with stats_path.open(newline="", encoding="utf-8") as handle:
        stats = list(csv.DictReader(handle))
    with comparison_path.open(newline="", encoding="utf-8") as handle:
        comparison = list(csv.DictReader(handle))
    lines = [
        "# Automated experiment report", "",
        f"- Timestamp UTC: {stamp}",
        f"- Independent benchmark series per algorithm: {runs}",
        f"- ECDSA repetitions per operation and series: {repetitions}",
        f"- ML-DSA-65 repetitions per operation and series: {max(30, repetitions // 2)}",
        "- Timings are means returned by the existing benchmark functions.",
        "- Raw files preserve each independent series result, not each individual operation timing.",
        "", "## Consolidated signature comparison", "",
        "Times are shown as mean ± sample SD; 95% confidence intervals are included in parentheses.",
        "",
        "| Algorithm | Key generation (ms) | Signing (ms) | Verification (ms) | Public key (B) | Private key (B) | Signature (B) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in comparison:
        cells = [row["algorithm"]]
        for metric in ("keygen_ms", "sign_ms", "verify_ms"):
            mean = float(row[f"{metric}_mean"])
            sd = float(row[f"{metric}_sd"])
            low = float(row[f"{metric}_ci95_low"])
            high = float(row[f"{metric}_ci95_high"])
            cells.append(f"{mean:.6f} ± {sd:.6f} ([{low:.6f}, {high:.6f}])")
        cells.extend(str(int(row[name])) for name in
                     ("public_key_bytes", "private_key_bytes", "signature_bytes"))
        lines.append("| " + " | ".join(cells) + " |")
    lines += [
        "", "## Other experiments and checks", "",
        f"- Grover circuit simulation: {grover_status}",
        f"- Pytest exit code: {test_code}; log: {test_log.relative_to(ROOT)}",
        "- Grover complexity model is analytical, not a measured cryptographic runtime.",
        "- Signature overhead is a data-size model, not a network measurement.",
        "", "## Output locations", "",
        "- Raw series: results/raw/",
        "- Aggregate benchmark input: data/signature_benchmark.csv",
        f"- Statistics: {stats_path.relative_to(ROOT)}",
        "- Consolidated table: results/tables/comparison_summary.csv",
        "- Main signature chart: results/figures/signature_comparison.png",
        "- Statistics: results/tables/signature_benchmark_statistics.csv",
        "- Logs and environment: results/logs/",
        "", "## Limitations", "",
        "Timing depends on hardware, operating system, library builds, and system load. "
        "These results describe this implementation and environment only. The Grover "
        "experiment is a small toy simulation, not a break of real cryptography.",
        "",
    ]
    path = RESULTS / "report.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the research experiment pipeline.")
    parser.add_argument("--runs", type=int, default=10, help="Independent series; minimum 2.")
    parser.add_argument("--repetitions", type=int, default=100, help="Timed ECDSA repetitions per operation.")
    parser.add_argument("--qubits", type=int, default=4, help="Grover toy simulation qubits (2..12).")
    parser.add_argument("--shots", type=int, default=2048, help="Shots per Grover iteration count.")
    args = parser.parse_args()
    if args.runs < 2:
        parser.error("--runs must be >= 2")
    if args.repetitions < 2:
        parser.error("--repetitions must be >= 2")
    if not 2 <= args.qubits <= 12:
        parser.error("--qubits must be between 2 and 12")
    if args.shots < 1:
        parser.error("--shots must be >= 1")

    make_dirs()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Environment: {save_environment(stamp).relative_to(ROOT)}")
    try:
        rows = run_benchmarks(stamp, args.runs, args.repetitions)
    except Exception as exc:
        error_log = LOGS / f"benchmark_error_{stamp}.txt"
        error_log.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        print(f"Benchmark failed: {exc}. Details: {error_log.relative_to(ROOT)}")
        return 1

    stats_path = summarize(rows)
    failures = []
    for module in (
        "experiments.grover.grover_model",
        "experiments.transaction.signature_overhead",
        "experiments.signatures.analyze_results",
    ):
        code, _ = run_module(module, stamp)
        if code:
            failures.append(module)
    grover_status = run_grover(stamp, args.qubits, args.shots)
    test_code, test_log = run_tests(stamp)
    if test_code:
        failures.append("pytest")
    report = write_report(stamp, args.runs, args.repetitions, stats_path,
                          grover_status, test_code, test_log)
    print(f"Report: {report.relative_to(ROOT)}")
    if failures:
        print("Completed with failures: " + ", ".join(failures))
        return 1
    print("Automation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
