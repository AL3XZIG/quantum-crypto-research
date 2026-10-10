import csv

import pytest

from experiments.transaction.signature_overhead import (
    DEFAULT_SIGNATURE_COUNTS,
    get_scheme_sizes,
    overhead_ratio,
    parse_signature_counts,
    run_model,
    save_csv,
    total_signature_bytes,
)


def test_total_signature_bytes_multiplies_size_by_count():
    assert total_signature_bytes(3309, 10) == 33090
    assert total_signature_bytes(72, 0) == 0


def test_total_signature_bytes_rejects_negative_values():
    with pytest.raises(ValueError):
        total_signature_bytes(-1, 5)
    with pytest.raises(ValueError):
        total_signature_bytes(64, -5)


def test_overhead_ratio():
    assert overhead_ratio(3309, 72) == pytest.approx(3309 / 72)
    with pytest.raises(ValueError):
        overhead_ratio(3309, 0)


def test_run_model_computes_totals_and_relative_overhead():
    sizes = {"ECDSA": 72, "ML-DSA-65": 3309}
    rows = run_model(sizes, [1, 10])
    assert len(rows) == 2
    first, tenth = rows
    assert first["ECDSA_total_bytes"] == 72
    assert first["ML-DSA-65_total_bytes"] == 3309
    assert tenth["ML-DSA-65_total_bytes"] == 33090
    # The relative overhead does not depend on the number of signatures.
    assert first["ML-DSA-65_overhead_vs_ECDSA"] == pytest.approx(
        tenth["ML-DSA-65_overhead_vs_ECDSA"]
    )
    assert first["ECDSA_overhead_vs_ECDSA"] == pytest.approx(1.0)


def test_run_model_requires_baseline_scheme():
    with pytest.raises(ValueError):
        run_model({"ML-DSA-65": 3309}, [1], baseline="ECDSA")


def test_get_scheme_sizes_falls_back_to_reference(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    sizes, source = get_scheme_sizes(missing)
    assert source == "reference"
    assert sizes["ECDSA"] < sizes["ML-DSA-65"]


def test_get_scheme_sizes_prefers_benchmark_csv(tmp_path):
    path = tmp_path / "signature_benchmark.csv"
    path.write_text(
        "algorithm,signature_bytes\nECDSA,71\nML-DSA-65,3309\n", encoding="utf-8"
    )
    sizes, source = get_scheme_sizes(path)
    assert source == "benchmark"
    assert sizes == {"ECDSA": 71, "ML-DSA-65": 3309}


def test_parse_signature_counts():
    assert parse_signature_counts("1, 2,3") == [1, 2, 3]
    with pytest.raises(ValueError):
        parse_signature_counts("0,5")
    with pytest.raises(ValueError):
        parse_signature_counts("")


def test_save_csv_roundtrip(tmp_path):
    rows = run_model(dict(get_scheme_sizes()[0]), DEFAULT_SIGNATURE_COUNTS[:2])
    path = tmp_path / "overhead.csv"
    save_csv(rows, path)
    with path.open(newline="", encoding="utf-8") as file:
        loaded = list(csv.DictReader(file))
    assert len(loaded) == 2
    assert int(loaded[0]["signatures_per_transaction"]) == DEFAULT_SIGNATURE_COUNTS[0]


def test_save_csv_rejects_empty_rows(tmp_path):
    with pytest.raises(ValueError):
        save_csv([], tmp_path / "empty.csv")
