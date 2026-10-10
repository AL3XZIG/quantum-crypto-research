"""Модель накладных расходов от размера цифровой подписи.

Сценарий эксперимента:

1. Берутся размеры подписей из результатов бенчмарка ``data/signature_benchmark.csv``
   (ECDSA P-256 и ML-DSA-65). Если файла нет — используются справочные значения
   из стандартов (FIPS 186-5 / FIPS 204), чтобы модель можно было запустить
   независимо от бенчмарка.
2. Для каждой схемы вычисляется суммарный объём подписных данных при разном
   числе подписей в транзакции (m-of-n, мультиподписи, пакетные переводы):
   ``total_signature_bytes(signature_size, signatures)``.
3. Накладные расходы сравниваются с базовой линией ECDSA и сохраняются в CSV
   для построения таблиц и графиков в статье.

Это аналитическая модель объёма данных, а не измерение блокчейна или сети.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_CSV = ROOT / "data" / "signature_benchmark.csv"
OUTPUT_CSV = ROOT / "data" / "signature_overhead_results.csv"

# Справочные размеры подписей в байтах (используются, если CSV бенчмарка
# отсутствует): DER-кодированная подпись ECDSA P-256 ~71-72 байта,
# детерминированная подпись ML-DSA-65 по FIPS 204 — ровно 3309 байт.
REFERENCE_SIZES = {
    "ECDSA": 72,
    "ML-DSA-65": 3309,
}

DEFAULT_SIGNATURE_COUNTS = [1, 5, 10, 50, 100, 250, 500, 1000]


def total_signature_bytes(signature_size: int, signatures: int) -> int:
    """Return the combined size of ``signatures`` signatures of one size."""
    if signature_size < 0 or signatures < 0:
        raise ValueError("signature_size and signatures must be >= 0")
    return signature_size * signatures


def overhead_ratio(pqc_size: int, baseline_size: int) -> float:
    """Return how many times larger the post-quantum signature is."""
    if baseline_size <= 0:
        raise ValueError("baseline_size must be > 0")
    return pqc_size / baseline_size


def load_signature_sizes(path: Path = BENCHMARK_CSV) -> dict[str, int]:
    """Read ``algorithm -> signature_bytes`` from the benchmark CSV if present."""
    if not path.exists():
        return {}
    sizes: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            try:
                sizes[row["algorithm"]] = int(row["signature_bytes"])
            except (KeyError, ValueError):
                continue
    return sizes


def get_scheme_sizes(path: Path = BENCHMARK_CSV) -> tuple[dict[str, int], str]:
    """Return signature sizes and their source ("benchmark" or "reference")."""
    sizes = load_signature_sizes(path)
    if {"ECDSA", "ML-DSA-65"} <= sizes.keys():
        return {"ECDSA": sizes["ECDSA"], "ML-DSA-65": sizes["ML-DSA-65"]}, "benchmark"
    return dict(REFERENCE_SIZES), "reference"


def run_model(
    scheme_sizes: dict[str, int],
    signature_counts: list[int],
    baseline: str = "ECDSA",
) -> list[dict]:
    """Compute per-count totals for every scheme plus the relative overhead."""
    if baseline not in scheme_sizes:
        raise ValueError(f"baseline scheme {baseline!r} missing from sizes")
    rows: list[dict] = []
    for count in signature_counts:
        row: dict[str, float | int] = {"signatures_per_transaction": count}
        for scheme, size in scheme_sizes.items():
            row[f"{scheme}_bytes_per_signature"] = size
            row[f"{scheme}_total_bytes"] = total_signature_bytes(size, count)
        baseline_total = total_signature_bytes(scheme_sizes[baseline], count)
        for scheme, size in scheme_sizes.items():
            row[f"{scheme}_overhead_vs_{baseline}"] = (
                total_signature_bytes(size, count) / baseline_total
            )
        rows.append(row)
    return rows


def save_csv(rows: list[dict], path: Path = OUTPUT_CSV) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("Cannot save an empty result set")
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_signature_counts(text: str) -> list[int]:
    counts = [int(part.strip()) for part in text.split(",") if part.strip()]
    if not counts or any(count < 1 for count in counts):
        raise ValueError("signature counts must be positive integers")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the transaction signature-size overhead model."
    )
    parser.add_argument(
        "--counts",
        type=str,
        default=None,
        help="Comma-separated number of signatures per transaction "
        f"(default: {','.join(map(str, DEFAULT_SIGNATURE_COUNTS))})",
    )
    args = parser.parse_args()

    print("Transaction overhead model")
    signature_counts = (
        parse_signature_counts(args.counts)
        if args.counts is not None
        else DEFAULT_SIGNATURE_COUNTS
    )
    scheme_sizes, source = get_scheme_sizes()
    rows = run_model(scheme_sizes, signature_counts)
    save_csv(rows)

    ecdsa_size = scheme_sizes["ECDSA"]
    mldsa_size = scheme_sizes["ML-DSA-65"]
    ratio = overhead_ratio(mldsa_size, ecdsa_size)
    print(f"Signature sizes source: {source}")
    print(
        f"ECDSA P-256: {ecdsa_size} bytes; ML-DSA-65: {mldsa_size} bytes "
        f"(x{ratio:.1f} larger)"
    )
    for row in rows:
        count = row["signatures_per_transaction"]
        print(
            f"{count:>5} signatures: ECDSA {row['ECDSA_total_bytes']:>10} B, "
            f"ML-DSA {row['ML-DSA-65_total_bytes']:>10} B, "
            f"overhead x{row['ML-DSA-65_overhead_vs_ECDSA']:.1f}"
        )
    print(f"CSV: {OUTPUT_CSV}")
    print("Note: this models data volume only, not blockchain or network measurements.")


if __name__ == "__main__":
    main()
