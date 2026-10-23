"""Estimate counterfactual Bitcoin fee, block-capacity and node-storage impacts.

Reads the per-transaction CSV produced by bitcoin_pqc_size_model.py. This is a
scenario model, not a Bitcoin protocol implementation or a prediction of market
fees. It assumes ML-DSA-65-sized payloads already represented in the input CSV.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "data" / "bitcoin_pqc_size_model.csv"
DEFAULT_FEES = ROOT / "results" / "tables" / "bitcoin_pqc_fee_scenarios.csv"
DEFAULT_BLOCKS = ROOT / "results" / "tables" / "bitcoin_pqc_block_capacity.csv"
DEFAULT_STORAGE = ROOT / "results" / "tables" / "bitcoin_pqc_node_storage.csv"
DEFAULT_SUMMARY = ROOT / "data" / "bitcoin_pqc_network_impact_summary.json"
DEFAULT_FEE_PLOT = ROOT / "results" / "figures" / "bitcoin_pqc_fee_scenarios.png"
DEFAULT_BLOCK_PLOT = ROOT / "results" / "figures" / "bitcoin_pqc_block_capacity.png"
DEFAULT_STORAGE_PLOT = ROOT / "results" / "figures" / "bitcoin_pqc_node_storage.png"
DEFAULT_FEE_RATES = (1, 5, 10, 25, 50, 100)
DEFAULT_CONVERSION_SHARES = (0, 25, 50, 75, 100)
DEFAULT_BLOCK_WEIGHT_LIMIT = 4_000_000
DEFAULT_BLOCKS_PER_DAY = 144


def load_rows(path: Path) -> list[dict]:
    """Load and validate rows from the transaction-size experiment."""
    with path.open("r", newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError(f"No transaction rows found in {path}")
    required = {
        "original_total_size_bytes", "original_weight_units", "original_vsize_bytes",
        "modeled_total_size_bytes", "modeled_weight_units", "modeled_vsize_bytes",
        "recognized_ecdsa_signatures",
    }
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {', '.join(sorted(missing))}")
    numeric = required
    parsed = []
    for index, row in enumerate(rows, start=2):
        item = dict(row)
        for key in numeric:
            try:
                item[key] = int(row[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid integer in row {index}, column {key}") from exc
        if min(item["original_total_size_bytes"], item["modeled_total_size_bytes"],
               item["original_weight_units"], item["modeled_weight_units"],
               item["original_vsize_bytes"], item["modeled_vsize_bytes"]) <= 0:
            raise ValueError(f"Non-positive transaction metric in row {index}")
        parsed.append(item)
    return parsed


def fee_scenarios(rows: list[dict], rates: tuple[int, ...] = DEFAULT_FEE_RATES) -> list[dict]:
    """Calculate illustrative fee costs at fixed sat/vB rates for sampled transactions."""
    if not rows:
        raise ValueError("At least one transaction row is required")
    if any(rate <= 0 for rate in rates):
        raise ValueError("Fee rates must be positive integers in sat/vB")
    result = []
    for rate in rates:
        before = [math.ceil(row["original_vsize_bytes"] * rate) for row in rows]
        after = [math.ceil(row["modeled_vsize_bytes"] * rate) for row in rows]
        result.append({
            "fee_rate_sat_vB": rate,
            "sample_transactions": len(rows),
            "mean_fee_original_sat": round(mean(before), 2),
            "mean_fee_modeled_sat": round(mean(after), 2),
            "mean_fee_delta_sat": round(mean(after) - mean(before), 2),
            "median_fee_original_sat": median(before),
            "median_fee_modeled_sat": median(after),
            "median_fee_delta_sat": median(after) - median(before),
            "fee_increase_percent_of_mean": round(100 * (mean(after) - mean(before)) / mean(before), 2),
        })
    return result


def block_capacity_scenarios(
    rows: list[dict],
    block_weight_limit: int = DEFAULT_BLOCK_WEIGHT_LIMIT,
    shares: tuple[int, ...] = DEFAULT_CONVERSION_SHARES,
    blocks_per_day: int = DEFAULT_BLOCKS_PER_DAY,
) -> list[dict]:
    """Estimate full-block capacity from mean transaction metrics at conversion shares.

    A share of 25 means a hypothetical 25% of transactions are migrated. The
    average size/weight is linearly interpolated between the original and modeled
    sample means. Capacity excludes coinbase/header and other block-level overhead,
    so it is an upper bound, not an exact block packer.
    """
    if not rows:
        raise ValueError("At least one transaction row is required")
    if block_weight_limit <= 0 or blocks_per_day <= 0:
        raise ValueError("Block weight limit and blocks/day must be positive")
    if any(share < 0 or share > 100 for share in shares):
        raise ValueError("Conversion shares must be between 0 and 100")
    avg_original_weight = mean(r["original_weight_units"] for r in rows)
    avg_modeled_weight = mean(r["modeled_weight_units"] for r in rows)
    avg_original_bytes = mean(r["original_total_size_bytes"] for r in rows)
    avg_modeled_bytes = mean(r["modeled_total_size_bytes"] for r in rows)
    result = []
    for share in shares:
        fraction = share / 100
        avg_weight = avg_original_weight + fraction * (avg_modeled_weight - avg_original_weight)
        avg_bytes = avg_original_bytes + fraction * (avg_modeled_bytes - avg_original_bytes)
        tx_per_block = math.floor(block_weight_limit / avg_weight)
        payload_bytes = tx_per_block * avg_bytes
        daily_bytes = payload_bytes * blocks_per_day
        annual_bytes = daily_bytes * 365
        result.append({
            "modeled_transaction_share_percent": share,
            "sample_transactions": len(rows),
            "block_weight_limit_wu": block_weight_limit,
            "mean_transaction_weight_wu": round(avg_weight, 2),
            "mean_transaction_total_size_bytes": round(avg_bytes, 2),
            "estimated_transactions_per_full_block_upper_bound": tx_per_block,
            "estimated_transaction_payload_per_full_block_mb": round(payload_bytes / 1_000_000, 3),
            "assumed_full_blocks_per_day": blocks_per_day,
            "estimated_transaction_payload_per_day_gb": round(daily_bytes / 1_000_000_000, 3),
            "estimated_transaction_payload_per_year_gb": round(annual_bytes / 1_000_000_000, 3),
            "estimated_transaction_payload_per_year_tib": round(annual_bytes / (1024 ** 4), 4),
        })
    return result


def save_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        raise ValueError(f"Refusing to write an empty table to {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_plots(fees: list[dict], blocks: list[dict], paths: tuple[Path, Path, Path]) -> list[str]:
    """Write fee, block-capacity and storage PNGs; return names successfully written."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    fee_path, block_path, storage_path = paths
    written = []

    fee_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot([r["fee_rate_sat_vB"] for r in fees],
            [r["median_fee_original_sat"] for r in fees], marker="o", label="Original")
    ax.plot([r["fee_rate_sat_vB"] for r in fees],
            [r["median_fee_modeled_sat"] for r in fees], marker="o", label="Modeled ML-DSA-65")
    ax.set(xlabel="Fee rate (sat/vB)", ylabel="Median illustrative transaction fee (sat)",
           title="Fee impact at fixed fee rates")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(fee_path, dpi=160)
    plt.close(fig)
    written.append(str(fee_path))

    block_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot([r["modeled_transaction_share_percent"] for r in blocks],
            [r["estimated_transactions_per_full_block_upper_bound"] for r in blocks],
            marker="o")
    ax.set(xlabel="Hypothetical share of migrated transactions (%)",
           ylabel="Transactions per full block (upper bound)",
           title="Estimated block transaction capacity")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(block_path, dpi=160)
    plt.close(fig)
    written.append(str(block_path))

    storage_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot([r["modeled_transaction_share_percent"] for r in blocks],
            [r["estimated_transaction_payload_per_year_gb"] for r in blocks],
            marker="o")
    ax.set(xlabel="Hypothetical share of migrated transactions (%)",
           ylabel="Transaction payload per year (GB, decimal)",
           title="Full-block node-storage growth scenario")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(storage_path, dpi=160)
    plt.close(fig)
    written.append(str(storage_path))
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="CSV from bitcoin_pqc_size_model.py")
    parser.add_argument("--fees", type=Path, default=DEFAULT_FEES)
    parser.add_argument("--blocks", type=Path, default=DEFAULT_BLOCKS)
    parser.add_argument("--storage", type=Path, default=DEFAULT_STORAGE)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--fee-figure", type=Path, default=DEFAULT_FEE_PLOT)
    parser.add_argument("--block-figure", type=Path, default=DEFAULT_BLOCK_PLOT)
    parser.add_argument("--storage-figure", type=Path, default=DEFAULT_STORAGE_PLOT)
    parser.add_argument("--block-weight-limit", type=int, default=DEFAULT_BLOCK_WEIGHT_LIMIT)
    parser.add_argument("--blocks-per-day", type=int, default=DEFAULT_BLOCKS_PER_DAY)
    args = parser.parse_args()

    rows = load_rows(args.input)
    fees = fee_scenarios(rows)
    blocks = block_capacity_scenarios(rows, args.block_weight_limit, blocks_per_day=args.blocks_per_day)
    save_csv(fees, args.fees)
    save_csv(blocks, args.blocks)
    storage_columns = ("modeled_transaction_share_percent", "estimated_transaction_payload_per_full_block_mb", "assumed_full_blocks_per_day", "estimated_transaction_payload_per_day_gb", "estimated_transaction_payload_per_year_gb", "estimated_transaction_payload_per_year_tib")
    storage = [{key: row[key] for key in storage_columns} for row in blocks]
    save_csv(storage, args.storage)
    figures = save_plots(fees, blocks, (args.fee_figure, args.block_figure, args.storage_figure))
    summary = {
        "model": "counterfactual scenario; not a Bitcoin protocol implementation",
        "input_csv": str(args.input),
        "sample_transactions": len(rows),
        "transactions_with_recognized_ecdsa_signatures": sum(r["recognized_ecdsa_signatures"] > 0 for r in rows),
        "replacement_signature_bytes": 3309,
        "fee_rates_sat_vB": list(DEFAULT_FEE_RATES),
        "block_weight_limit_wu": args.block_weight_limit,
        "assumed_full_blocks_per_day": args.blocks_per_day,
        "fee_table": str(args.fees),
        "block_capacity_table": str(args.blocks),
        "node_storage_table": str(args.storage),
        "figures_written": figures,
        "limitations": [
            "Fee rates are fixed hypothetical sat/vB values; this does not predict fee-market equilibrium.",
            "The model assumes the upstream CSV's counterfactual signature replacement and its limitations.",
            "Block capacity is calculated from average sampled transaction weight and excludes coinbase, headers, witness commitment and packing effects; it is an upper bound.",
            "Storage projections assume every block is full, 144 blocks/day, 365 days/year, no pruning and no compression.",
            "Projected storage counts transaction payload bytes only and is not a measurement of actual Bitcoin node disk usage or bandwidth.",
            "A real ML-DSA migration would require protocol and consensus changes; this script does not create valid post-quantum Bitcoin transactions."
        ]
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Transactions analyzed: {len(rows)}")
    print(f"Fee table: {args.fees}")
    print(f"Block capacity table: {args.blocks}")
    print(f"Node storage table: {args.storage}")
    print(f"Summary: {args.summary}")
    if figures:
        print("Figures: " + ", ".join(figures))
    else:
        print("PNG figures skipped (install matplotlib to generate them).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
