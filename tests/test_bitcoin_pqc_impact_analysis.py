import csv
import tempfile
import unittest
from pathlib import Path

from experiments.transaction.bitcoin_pqc_impact_analysis import (
    block_scenarios,
    fee_scenarios,
    load_rows,
    storage_scenarios,
    write_csv,
)


SAMPLE = [
    {
        "original_total_size_bytes": 200, "modeled_total_size_bytes": 3400,
        "original_weight_units": 500, "modeled_weight_units": 9000,
        "original_vsize_bytes": 125, "modeled_vsize_bytes": 2250,
    },
    {
        "original_total_size_bytes": 400, "modeled_total_size_bytes": 3600,
        "original_weight_units": 1000, "modeled_weight_units": 9500,
        "original_vsize_bytes": 250, "modeled_vsize_bytes": 2375,
    },
]


class BitcoinPqcImpactAnalysisTests(unittest.TestCase):
    def test_fee_scenarios_use_vsize_and_rate(self):
        rows = fee_scenarios(SAMPLE, rates=(1, 10))
        self.assertEqual(rows[0]["mean_original_fee_sat"], 187.5)
        self.assertEqual(rows[0]["mean_modeled_fee_sat"], 2312.5)
        self.assertEqual(rows[1]["fee_rate_sat_vb"], 10)
        self.assertGreater(rows[1]["mean_fee_delta_sat"], rows[0]["mean_fee_delta_sat"])

    def test_block_capacity_falls_when_weight_increases(self):
        rows = block_scenarios(SAMPLE, limit=10000)
        original = next(r for r in rows if r["scenario"] == "original")
        modeled = next(r for r in rows if r["scenario"] == "modeled_ml_dsa_65")
        self.assertGreater(original["estimated_tx_per_block_using_mean"],
                           modeled["estimated_tx_per_block_using_mean"])
        self.assertEqual(modeled["hypothetical_blocks_for_sample"], 2)

    def test_storage_outputs_both_models(self):
        rows = storage_scenarios(SAMPLE, limit=10000, tx_per_day_values=(1000,))
        self.assertEqual(len(rows), 4)
        self.assertTrue(any(r["model"] == "fixed_block_weight_capacity_estimate" for r in rows))
        self.assertTrue(any(r["model"] == "equal_transaction_throughput_unconstrained" for r in rows))

    def test_load_rows_rejects_missing_columns(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.csv"
            path.write_text("txid,foo\nx,1\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rows(path)

    def test_write_csv_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "nested" / "out.csv"
            write_csv([{"x": 1}], path)
            with path.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(list(csv.DictReader(handle))[0]["x"], "1")


if __name__ == "__main__":
    unittest.main()
