import csv
import tempfile
import unittest
from pathlib import Path

from experiments.transaction.bitcoin_pqc_network_impact import (
    block_capacity_scenarios,
    fee_scenarios,
    load_rows,
)


def sample_rows():
    return [
        {
            "original_total_size_bytes": 100,
            "original_weight_units": 400,
            "original_vsize_bytes": 100,
            "modeled_total_size_bytes": 500,
            "modeled_weight_units": 2000,
            "modeled_vsize_bytes": 500,
            "recognized_ecdsa_signatures": 1,
        },
        {
            "original_total_size_bytes": 200,
            "original_weight_units": 800,
            "original_vsize_bytes": 200,
            "modeled_total_size_bytes": 200,
            "modeled_weight_units": 800,
            "modeled_vsize_bytes": 200,
            "recognized_ecdsa_signatures": 0,
        },
    ]


class BitcoinPqcNetworkImpactTests(unittest.TestCase):
    def test_fee_scenarios_compare_original_and_modeled_vsize(self):
        result = fee_scenarios(sample_rows(), rates=(1, 10))
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["mean_fee_original_sat"], 150)
        self.assertEqual(result[0]["mean_fee_modeled_sat"], 350)
        self.assertEqual(result[0]["mean_fee_delta_sat"], 200)
        self.assertEqual(result[1]["mean_fee_original_sat"], 1500)
        self.assertEqual(result[1]["mean_fee_modeled_sat"], 3500)

    def test_block_capacity_falls_when_average_weight_increases(self):
        result = block_capacity_scenarios(
            sample_rows(), block_weight_limit=4000, shares=(0, 100), blocks_per_day=144
        )
        self.assertEqual(result[0]["estimated_transactions_per_full_block_upper_bound"], 6)
        self.assertEqual(result[1]["estimated_transactions_per_full_block_upper_bound"], 2)
        self.assertGreater(
            result[1]["estimated_transaction_payload_per_year_gb"], 0
        )
        self.assertEqual(result[0]["assumed_full_blocks_per_day"], 144)

    def test_invalid_fee_rate_rejected(self):
        with self.assertRaises(ValueError):
            fee_scenarios(sample_rows(), rates=(0,))

    def test_invalid_conversion_share_rejected(self):
        with self.assertRaises(ValueError):
            block_capacity_scenarios(sample_rows(), shares=(101,))

    def test_load_rows_reads_existing_model_csv_schema(self):
        rows = sample_rows()
        fields = list(rows[0])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.csv"
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            loaded = load_rows(path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0]["original_vsize_bytes"], 100)
        self.assertEqual(loaded[1]["recognized_ecdsa_signatures"], 0)


if __name__ == "__main__":
    unittest.main()
