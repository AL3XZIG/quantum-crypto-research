import unittest

from experiments.transaction.bitcoin_pqc_size_model import (
    Transaction,
    analyze_transaction,
    is_der_ecdsa_signature_item,
    push_data,
    varint,
)


def make_tx(script_sig: bytes = b"", witness: list[bytes] | None = None) -> bytes:
    """Build a tiny synthetic transaction for serialization/parser tests."""
    witness = witness or []
    version = b"\x02\x00\x00\x00"
    outpoint = b"\x11" * 32 + b"\x00\x00\x00\x00"
    sequence = b"\xff\xff\xff\xff"
    txout = (1000).to_bytes(8, "little") + varint(1) + b"\x51"
    if witness:
        raw = bytearray(version + b"\x00\x01" + b"\x01" + outpoint)
    else:
        raw = bytearray(version + b"\x01" + outpoint)
    raw.extend(varint(len(script_sig)))
    raw.extend(script_sig)
    raw.extend(sequence)
    raw.extend(b"\x01" + txout)
    if witness:
        raw.extend(varint(len(witness)))
        for item in witness:
            raw.extend(varint(len(item)))
            raw.extend(item)
    raw.extend(b"\x00\x00\x00\x00")
    return bytes(raw)


class BitcoinPqcSizeModelTests(unittest.TestCase):
    def setUp(self):
        # Structurally valid, tiny DER integers plus SIGHASH_ALL.
        self.signature = bytes.fromhex("3006020101020101") + b"\x01"

    def test_der_ecdsa_item_recognized(self):
        self.assertTrue(is_der_ecdsa_signature_item(self.signature))

    def test_schnorr_length_item_not_recognized_as_ecdsa(self):
        self.assertFalse(is_der_ecdsa_signature_item(b"\x01" * 64))

    def test_legacy_transaction_round_trips_and_grows(self):
        raw = make_tx(script_sig=push_data(self.signature))
        tx = Transaction.parse(raw)
        self.assertEqual(tx.serialize(), raw)
        original_size = tx.metrics()["total_size_bytes"]
        count = tx.replace_signatures(3309)
        self.assertEqual(count, 1)
        modeled = tx.metrics()["total_size_bytes"]
        self.assertGreater(modeled, original_size + 3200)

    def test_witness_transaction_round_trips_and_grows(self):
        raw = make_tx(witness=[self.signature, b"\x02" * 33])
        tx = Transaction.parse(raw)
        self.assertEqual(tx.serialize(), raw)
        original = tx.metrics()
        self.assertEqual(tx.replace_signatures(3309), 1)
        modeled = tx.metrics()
        self.assertGreater(modeled["total_size_bytes"], original["total_size_bytes"])
        self.assertGreater(modeled["weight_units"], original["weight_units"])

    def test_analysis_reports_vsize_and_delta(self):
        raw = make_tx(script_sig=push_data(self.signature))
        row = analyze_transaction("test-txid", raw.hex(), 3309)
        self.assertEqual(row["recognized_ecdsa_signatures"], 1)
        self.assertGreater(row["delta_total_size_bytes"], 0)
        self.assertGreater(row["delta_vsize_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
