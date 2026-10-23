"""Estimate fee, block-capacity and node-storage impacts from a transaction-size CSV.

This is a counterfactual scenario analysis, not a Bitcoin protocol implementation.
It uses the original/modelled transaction metrics emitted by bitcoin_pqc_size_model.py.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "bitcoin_pqc_size_model.csv"
DEFAULT_TABLE_DIR = ROOT / "results" / "tables"
DEFAULT_FIGURE_DIR = ROOT / "results" / "figures"
DEFAULT_BLOCK_WEIGHT_LIMIT = 4_000_000
DEFAULT_FEE_RATES = (1, 5, 10, 25, 50, 100)
DEFAULT_TX_PER_DAY = (100_000, 300_000, 500_000)
BLOCKS_PER_DAY = 144


def load_rows(path: Path) -> list[dict[str, int]]:
    """Load rows from the existing size-model CSV and validate required metrics."""
    required = (
        "original_total_size_bytes", "modeled_total_size_bytes",
        "original_weight_units", "modeled_weight_units",
        "original_vsize_bytes", "modeled_vsize_bytes",
    )
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [name for name in required if name not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Input CSV is missing required columns: {', '.join(missing)}")
        rows = []
        for line_no, row in enumerate(reader, start=2):
            try:
                parsed = {name: int(row[name]) for name in required}
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric metric on CSV line {line_no}") from exc
            if any(value <= 0 for value in parsed.values()):
                raise ValueError(f"Metrics must be positive on CSV line {line_no}")
            rows.append(parsed)
    if not rows:
        raise ValueError(f"No transaction rows found in {path}")
    return rows


def fee_scenarios(rows: list[dict[str, int]], rates: tuple[int, ...] = DEFAULT_FEE_RATES) -> list[dict]:
    """Estimate fees using ceil(vsize * sat/vB); values are scenarios, not observed fees."""
    result = []
    for rate in rates:
        original_fees = [math.ceil(r["original_vsize_bytes"] * rate) for r in rows]
        modeled_fees = [math.ceil(r["modeled_vsize_bytes"] * rate) for r in rows]
        original_mean = mean(original_fees)
        modeled_mean = mean(modeled_fees)
        original_median = median(original_fees)
        modeled_median = median(modeled_fees)
        result.append({
            "fee_rate_sat_vb": rate,
            "sample_transactions": len(rows),
            "mean_original_fee_sat": round(original_mean, 3),
            "mean_modeled_fee_sat": round(modeled_mean, 3),
            "mean_fee_delta_sat": round(modeled_mean - original_mean, 3),
            "mean_fee_increase_percent": round(100 * (modeled_mean - original_mean) / original_mean, 3) if original_mean else 0,
            "median_original_fee_sat": original_median,
            "median_modeled_fee_sat": modeled_median,
            "median_fee_delta_sat": modeled_median - original_median,
            "median_fee_increase_percent": round(100 * (modeled_median - original_median) / original_median, 3) if original_median else 0,
        })
    return result


def _blocks_needed(weights: list[int], limit: int) -> int:
    """Greedily pack transactions in input order; returns a hypothetical block count."""
    blocks = 1
    used = 0
    for weight in weights:
        if weight > limit:
            raise ValueError(f"A transaction weight ({weight}) exceeds block limit ({limit})")
        if used + weight > limit:
            blocks += 1
            used = 0
        used += weight
    return blocks


def block_scenarios(rows: list[dict[str, int]], limit: int = DEFAULT_BLOCK_WEIGHT_LIMIT) -> list[dict]:
    """Compare estimated capacity and hypothetical packing under a fixed block-weight limit."""
    if limit <= 0:
        raise ValueError("Block weight limit must be positive")
    output = []
    for label, weight_key, size_key in (
        ("original", "original_weight_units", "original_total_size_bytes"),
        ("modeled_ml_dsa_65", "modeled_weight_units", "modeled_total_size_bytes"),
    ):
        weights = [r[weight_key] for r in rows]
        sizes = [r[size_key] for r in rows]
        avg_weight = mean(weights)
        med_weight = median(weights)
        capacity_mean = limit // avg_weight
        capacity_median = limit // med_weight
        output.append({
            "scenario": label,
            "block_weight_limit_wu": limit,
            "sample_transactions": len(rows),
            "mean_tx_weight_wu": round(avg_weight, 3),
            "median_tx_weight_wu": med_weight,
            "estimated_tx_per_block_using_mean": int(capacity_mean),
            "estimated_tx_per_block_using_median": int(capacity_median),
            "sample_total_weight_wu": sum(weights),
            "sample_total_serialized_bytes": sum(sizes),
            "hypothetical_blocks_for_sample": _blocks_needed(weights, limit),
        })
    return output


def storage_scenarios(
    rows: list[dict[str, int]],
    limit: int = DEFAULT_BLOCK_WEIGHT_LIMIT,
    tx_per_day_values: tuple[int, ...] = DEFAULT_TX_PER_DAY,
) -> list[dict]:
    """Project storage for equal traffic and fixed block capacity as separate scenarios.

    Equal-throughput projections intentionally ignore the fixed block-weight constraint.
    Fixed-capacity projections estimate full blocks using mean sample metrics and omit
    coinbase transactions, headers, witness/metadata overhead and other block overhead.
    """
    if limit <= 0:
        raise ValueError("Block weight limit must be positive")
    mean_original_size = mean(r["original_total_size_bytes"] for r in rows)
    mean_modeled_size = mean(r["modeled_total_size_bytes"] for r in rows)
    mean_original_weight = mean(r["original_weight_units"] for r in rows)
    mean_modeled_weight = mean(r["modeled_weight_units"] for r in rows)
    output = []
    for tx_day in tx_per_day_values:
        if tx_day <= 0:
            raise ValueError("Transactions per day must be positive")
        for label, size, weight in (
            ("original", mean_original_size, mean_original_weight),
            ("modeled_ml_dsa_65", mean_modeled_size, mean_modeled_weight),
        ):
            annual_bytes = size * tx_day * 365
            output.append({
                "model": "equal_transaction_throughput_unconstrained",
                "scenario": label,
                "transactions_per_day": tx_day,
                "mean_transaction_bytes": round(size, 3),
                "projected_chain_data_gb_per_year": round(annual_bytes / 1_000_000_000, 3),
                "note": "Same transaction count; ignores fixed block-weight capacity and is not a feasible forecast under the current limit.",
            })
        for label, size, weight in (
            ("original", mean_original_size, mean_original_weight),
            ("modeled_ml_dsa_65", mean_modeled_size, mean_modeled_weight),
        ):
            tx_per_block = max(1, int(limit // weight))
            annual_bytes = size * tx_per_block * BLOCKS_PER_DAY * 365
            output.append({
                "model": "fixed_block_weight_capacity_estimate",
                "scenario": label,
                "transactions_per_day": tx_per_block * BLOCKS_PER_DAY,
                "mean_transaction_bytes": round(size, 3),
                "projected_chain_data_gb_per_year": round(annual_bytes / 1_000_000_000, 3),
                "note": "Approximation using mean sample weight/size and 144 full blocks per day; excludes block overhead and coinbase.",
            })
    return output


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        raise ValueError("Cannot write an empty result table")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plots(fees: list[dict], blocks: list[dict], storage: list[dict], figure_dir: Path) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    figure_dir.mkdir(parents=True, exist_ok=True)
    created = []

    path = figure_dir / "bitcoin_pqc_fee_scenarios.png"
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot([r["fee_rate_sat_vb"] for r in fees], [r["mean_original_fee_sat"] for r in fees], marker="o", label="Original")
    ax.plot([r["fee_rate_sat_vb"] for r in fees], [r["mean_modeled_fee_sat"] for r in fees], marker="o", label="ML-DSA-65 model")
    ax.set(xlabel="Fee rate (sat/vB)", ylabel="Estimated mean fee (sat)", title="Estimated transaction fee by fee rate")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    created.append(path)

    path = figure_dir / "bitcoin_pqc_block_capacity.png"
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["Original", "ML-DSA-65 model"]
    vals = [next(r["estimated_tx_per_block_using_mean"] for r in blocks if r["scenario"] == "original"),
            next(r["estimated_tx_per_block_using_mean"] for r in blocks if r["scenario"] == "modeled_ml_dsa_65")]
    bars = ax.bar(labels, vals)
    ax.set(ylabel="Estimated transactions per block", title="Estimated capacity at fixed 4,000,000 WU")
    ax.bar_label(bars)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    created.append(path)

    fixed = [r for r in storage if r["model"] == "fixed_block_weight_capacity_estimate"]
    path = figure_dir / "bitcoin_pqc_storage_projection.png"
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = ["Original", "ML-DSA-65 model"]
    vals = [next(r["projected_chain_data_gb_per_year"] for r in fixed if r["scenario"] == "original"),
            next(r["projected_chain_data_gb_per_year"] for r in fixed if r["scenario"] == "modeled_ml_dsa_65")]
    bars = ax.bar(labels, vals)
    ax.set(ylabel="Estimated additional chain data (GB/year)", title="Storage projection at fixed block-weight capacity")
    ax.bar_label(bars, fmt="%.1f")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    created.append(path)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="CSV produced by bitcoin_pqc_size_model.py")
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURE_DIR)
    parser.add_argument("--block-weight-limit", type=int, default=DEFAULT_BLOCK_WEIGHT_LIMIT)
    args = parser.parse_args()
    rows = load_rows(args.input)
    fees = fee_scenarios(rows)
    blocks = block_scenarios(rows, args.block_weight_limit)
    storage = storage_scenarios(rows, args.block_weight_limit)
    fee_path = args.table_dir / "bitcoin_pqc_fee_scenarios.csv"
    block_path = args.table_dir / "bitcoin_pqc_block_capacity.csv"
    storage_path = args.table_dir / "bitcoin_pqc_storage_projection.csv"
    write_csv(fees, fee_path)
    write_csv(blocks, block_path)
    write_csv(storage, storage_path)
    figures = make_plots(fees, blocks, storage, args.figure_dir)
    print(f"Transactions analyzed: {len(rows)}")
    print(f"Fee scenarios: {fee_path}")
    print(f"Block capacity: {block_path}")
    print(f"Storage projection: {storage_path}")
    for path in figures:
        print(f"Figure: {path}")
    if not figures:
        print("PNG plots skipped: install matplotlib to enable plotting.")
    print("IMPORTANT: these are scenario estimates, not observed fees or a Bitcoin protocol implementation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
