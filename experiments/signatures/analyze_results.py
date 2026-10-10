"""Build one consolidated signature comparison table and one timing chart."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "signature_benchmark.csv"
DEFAULT_OUTPUT = ROOT / "results"
DEFAULT_STATS = DEFAULT_OUTPUT / "tables" / "signature_benchmark_statistics.csv"

TIMING_METRICS = ("keygen_ms", "sign_ms", "verify_ms")
SIZE_METRICS = ("public_key_bytes", "private_key_bytes", "signature_bytes")
LABELS = {
    "keygen_ms": "Key generation",
    "sign_ms": "Signing",
    "verify_ms": "Verification",
}


def load_results(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"algorithm", "parameter", *TIMING_METRICS, *SIZE_METRICS}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing columns in {path}: {sorted(missing)}")
    if df.empty:
        raise ValueError(f"Benchmark CSV is empty: {path}")
    return df


def build_comparison_table(aggregate: pd.DataFrame, stats_path: Path) -> pd.DataFrame:
    """Combine aggregate timing/size metrics with run-to-run statistics."""
    output = []
    stats = pd.read_csv(stats_path) if stats_path.exists() else pd.DataFrame()
    for _, row in aggregate.iterrows():
        item = {
            "algorithm": row["algorithm"],
            "parameter": row["parameter"],
        }
        for metric in TIMING_METRICS:
            item[f"{metric}_mean"] = float(row[metric])
            match = stats[
                (stats["algorithm"] == row["algorithm"])
                & (stats["metric"] == metric)
            ] if not stats.empty else pd.DataFrame()
            if not match.empty:
                stat = match.iloc[0]
                item[f"{metric}_sd"] = float(stat["sample_sd"])
                item[f"{metric}_ci95_low"] = float(stat["ci95_low"])
                item[f"{metric}_ci95_high"] = float(stat["ci95_high"])
                item["independent_runs"] = int(stat["independent_runs"])
            else:
                item[f"{metric}_sd"] = float("nan")
                item[f"{metric}_ci95_low"] = float("nan")
                item[f"{metric}_ci95_high"] = float("nan")
                item["independent_runs"] = 1
        for metric in SIZE_METRICS:
            item[metric] = int(row[metric])
        output.append(item)
    return pd.DataFrame(output)


def make_comparison_plot(df: pd.DataFrame, output: Path) -> None:
    means = [f"{metric}_mean" for metric in TIMING_METRICS]
    plot_df = df.set_index("algorithm")[means].copy()
    plot_df.columns = [LABELS[metric] for metric in TIMING_METRICS]
    ax = plot_df.plot(kind="bar", figsize=(10, 5.5), logy=True, width=0.72)
    ax.set_ylabel("Mean time (ms, logarithmic scale)")
    ax.set_xlabel("")
    ax.set_title("ECDSA P-256 vs ML-DSA-65: signature performance")
    ax.set_xticklabels(ax.get_xticklabels(), rotation=0)
    ax.grid(axis="y", which="both", alpha=0.25)
    ax.legend(title="Operation")
    fig = ax.get_figure()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create one consolidated signature comparison table and one timing chart."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    args = parser.parse_args()

    aggregate = load_results(args.input)
    summary = args.output / "tables" / "comparison_summary.csv"
    chart = args.output / "figures" / "signature_comparison.png"
    summary.parent.mkdir(parents=True, exist_ok=True)
    chart.parent.mkdir(parents=True, exist_ok=True)

    comparison = build_comparison_table(aggregate, args.stats)
    comparison.to_csv(summary, index=False)
    make_comparison_plot(comparison, chart)

    # Remove the old split charts so the signature experiment has one main graph.
    for old_name in ("signature_times.png", "signature_sizes.png"):
        (args.output / "figures" / old_name).unlink(missing_ok=True)

    print(f"Comparison table: {summary}")
    print(f"Comparison chart: {chart}")


if __name__ == "__main__":
    main()
