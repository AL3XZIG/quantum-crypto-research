"""Build one consolidated signature comparison table and one timing chart."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "signature_benchmark.csv"
DEFAULT_OUTPUT = ROOT / "results"
SUMMARY = DEFAULT_OUTPUT / "tables" / "comparison_summary.csv"
CHART = DEFAULT_OUTPUT / "figures" / "signature_comparison.png"


def load_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {
        "algorithm", "parameter", "keygen_ms", "sign_ms", "verify_ms",
        "public_key_bytes", "private_key_bytes", "signature_bytes",
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if df.empty:
        raise ValueError("Benchmark CSV is empty.")
    return df


def make_comparison_plot(df: pd.DataFrame, output: Path) -> None:
    metrics = ["keygen_ms", "sign_ms", "verify_ms"]
    labels = ["Key generation", "Signing", "Verification"]
    ax = df.set_index("algorithm")[metrics].plot(
        kind="bar", figsize=(10, 5), logy=True, width=0.72
    )
    ax.set_ylabel("Mean time (ms, logarithmic scale)")
    ax.set_xlabel("")
    ax.set_title("ECDSA P-256 vs ML-DSA-65: performance comparison")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    ax.legend(labels, title="Operation")
    ax.grid(axis="y", which="both", alpha=0.25)
    fig = ax.get_figure()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the main signature comparison chart from the consolidated results table."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = args.output / "tables" / "comparison_summary.csv"
    chart = args.output / "figures" / "signature_comparison.png"
    summary.parent.mkdir(parents=True, exist_ok=True)
    chart.parent.mkdir(parents=True, exist_ok=True)

    # The automation pipeline writes the richer table with run-to-run statistics.
    # For standalone use, fall back to the latest benchmark CSV.
    source = summary if summary.exists() else args.input
    df = load_results(source)
    make_comparison_plot(df, chart)

    # Remove legacy signature charts so this experiment has one main graph.
    for old_name in ("signature_times.png", "signature_sizes.png"):
        (args.output / "figures" / old_name).unlink(missing_ok=True)

    print(f"Comparison table: {summary if summary.exists() else args.input}")
    print(f"Comparison chart: {chart}")


if __name__ == "__main__":
    main()
