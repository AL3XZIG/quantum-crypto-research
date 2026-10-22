"""Counterfactual Bitcoin transaction-size model: ECDSA signatures -> ML-DSA-65-sized payloads.

This parses real raw Bitcoin transactions from Blockstream Esplora, replaces
strict-DER ECDSA signature-shaped items in script pushes/witness stacks, and
recomputes serialized size, weight and vsize. It is a size scenario, NOT a valid
Bitcoin protocol upgrade. ML-DSA-65 signatures are 3309 bytes (NIST FIPS 204).
Standard library only; matplotlib is optional for plotting.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
import urllib.error
import urllib.request
from email.utils import parsedate_to_datetime
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API = "https://blockstream.info/api"
DEFAULT_CSV = ROOT / "data" / "bitcoin_pqc_size_model.csv"
DEFAULT_SUMMARY = ROOT / "data" / "bitcoin_pqc_size_summary.json"
DEFAULT_FIGURE = ROOT / "results" / "figures" / "bitcoin_pqc_size_comparison.png"
DEFAULT_TABLE = ROOT / "results" / "tables" / "bitcoin_pqc_size_summary.csv"
ML_DSA_65_SIGNATURE_BYTES = 3309
SIGHASH_TYPES = {1, 2, 3, 0x81, 0x82, 0x83}
_REQUEST_MIN_INTERVAL_SECONDS = 0.0
_LAST_REQUEST_STARTED = 0.0


class TransactionFormatError(ValueError):
    """Malformed raw transaction serialization."""


def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    if pos >= len(data):
        raise TransactionFormatError("Unexpected end while reading CompactSize")
    marker = data[pos]
    pos += 1
    if marker < 0xFD:
        return marker, pos
    width = {0xFD: 2, 0xFE: 4, 0xFF: 8}[marker]
    if pos + width > len(data):
        raise TransactionFormatError("Truncated CompactSize")
    value = int.from_bytes(data[pos:pos + width], "little")
    minimum = {2: 0xFD, 4: 0x10000, 8: 0x100000000}[width]
    if value < minimum:
        raise TransactionFormatError("Non-canonical CompactSize")
    return value, pos + width


def varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("CompactSize cannot be negative")
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + value.to_bytes(2, "little")
    if value <= 0xFFFFFFFF:
        return b"\xfe" + value.to_bytes(4, "little")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return b"\xff" + value.to_bytes(8, "little")
    raise ValueError("CompactSize too large")


def is_der_ecdsa_signature_item(item: bytes) -> bool:
    """Recognize strict-DER ECDSA signature plus Bitcoin sighash byte."""
    if not 9 <= len(item) <= 73 or item[-1] not in SIGHASH_TYPES:
        return False
    der = item[:-1]
    if len(der) < 8 or der[0] != 0x30 or der[1] != len(der) - 2 or der[2] != 0x02:
        return False
    r_len = der[3]
    s_tag = 4 + r_len
    if r_len == 0 or s_tag + 2 > len(der) or der[s_tag] != 0x02:
        return False
    s_len = der[s_tag + 1]
    s_start = s_tag + 2
    if s_len == 0 or s_start + s_len != len(der):
        return False
    for integer in (der[4:s_tag], der[s_start:s_start + s_len]):
        if not integer or integer[0] & 0x80:
            return False
        if len(integer) > 1 and integer[0] == 0 and not (integer[1] & 0x80):
            return False
    return True


def push_data(data: bytes) -> bytes:
    n = len(data)
    if n == 0:
        return b"\x00"
    if n <= 75:
        return bytes([n]) + data
    if n <= 0xFF:
        return b"\x4c" + bytes([n]) + data
    if n <= 0xFFFF:
        return b"\x4d" + n.to_bytes(2, "little") + data
    if n <= 0xFFFFFFFF:
        return b"\x4e" + n.to_bytes(4, "little") + data
    raise ValueError("Pushdata too large")


def replace_script(script: bytes, replacement_size: int) -> tuple[bytes, int]:
    out, pos, replaced = bytearray(), 0, 0
    while pos < len(script):
        start = pos
        opcode = script[pos]
        pos += 1
        if opcode == 0:
            out.extend(script[start:pos])
            continue
        if 1 <= opcode <= 75:
            size = opcode
        elif opcode == 0x4C:
            if pos + 1 > len(script):
                raise TransactionFormatError("Truncated OP_PUSHDATA1")
            size = script[pos]
            pos += 1
        elif opcode == 0x4D:
            if pos + 2 > len(script):
                raise TransactionFormatError("Truncated OP_PUSHDATA2")
            size = int.from_bytes(script[pos:pos + 2], "little")
            pos += 2
        elif opcode == 0x4E:
            if pos + 4 > len(script):
                raise TransactionFormatError("Truncated OP_PUSHDATA4")
            size = int.from_bytes(script[pos:pos + 4], "little")
            pos += 4
        else:
            out.extend(script[start:pos])
            continue
        if pos + size > len(script):
            raise TransactionFormatError("Pushdata exceeds script length")
        item = script[pos:pos + size]
        pos += size
        if is_der_ecdsa_signature_item(item):
            out.extend(push_data(b"\x00" * replacement_size))
            replaced += 1
        else:
            out.extend(script[start:pos])
    return bytes(out), replaced


@dataclass
class TxInput:
    outpoint: bytes
    script_sig: bytes
    sequence: bytes
    witness: list[bytes] = field(default_factory=list)


@dataclass
class TxOutput:
    value: bytes
    script_pubkey: bytes


@dataclass
class Transaction:
    version: bytes
    inputs: list[TxInput]
    outputs: list[TxOutput]
    locktime: bytes
    has_witness: bool

    @classmethod
    def parse(cls, raw: bytes) -> "Transaction":
        if len(raw) < 10:
            raise TransactionFormatError("Transaction too short")
        pos, version = 4, raw[:4]
        has_witness = pos + 2 <= len(raw) and raw[pos] == 0 and raw[pos + 1] != 0
        if has_witness:
            pos += 2
        n_inputs, pos = read_varint(raw, pos)
        if n_inputs == 0:
            raise TransactionFormatError("Transaction has no inputs")
        inputs = []
        for _ in range(n_inputs):
            if pos + 36 > len(raw):
                raise TransactionFormatError("Truncated outpoint")
            outpoint = raw[pos:pos + 36]
            pos += 36
            n, pos = read_varint(raw, pos)
            if pos + n + 4 > len(raw):
                raise TransactionFormatError("Truncated input")
            script_sig = raw[pos:pos + n]
            pos += n
            sequence = raw[pos:pos + 4]
            pos += 4
            inputs.append(TxInput(outpoint, script_sig, sequence))
        n_outputs, pos = read_varint(raw, pos)
        outputs = []
        for _ in range(n_outputs):
            if pos + 8 > len(raw):
                raise TransactionFormatError("Truncated output value")
            value = raw[pos:pos + 8]
            pos += 8
            n, pos = read_varint(raw, pos)
            if pos + n > len(raw):
                raise TransactionFormatError("Truncated output script")
            outputs.append(TxOutput(value, raw[pos:pos + n]))
            pos += n
        if has_witness:
            for txin in inputs:
                n_items, pos = read_varint(raw, pos)
                for _ in range(n_items):
                    n, pos = read_varint(raw, pos)
                    if pos + n > len(raw):
                        raise TransactionFormatError("Truncated witness item")
                    txin.witness.append(raw[pos:pos + n])
                    pos += n
        if pos + 4 != len(raw):
            raise TransactionFormatError("Unexpected trailing transaction data")
        return cls(version, inputs, outputs, raw[pos:pos + 4], has_witness)

    def serialize(self, with_witness: bool = True) -> bytes:
        witness = with_witness and self.has_witness
        out = bytearray(self.version)
        if witness:
            out.extend(b"\x00\x01")
        out.extend(varint(len(self.inputs)))
        for txin in self.inputs:
            out.extend(txin.outpoint)
            out.extend(varint(len(txin.script_sig)))
            out.extend(txin.script_sig)
            out.extend(txin.sequence)
        out.extend(varint(len(self.outputs)))
        for txout in self.outputs:
            out.extend(txout.value)
            out.extend(varint(len(txout.script_pubkey)))
            out.extend(txout.script_pubkey)
        if witness:
            for txin in self.inputs:
                out.extend(varint(len(txin.witness)))
                for item in txin.witness:
                    out.extend(varint(len(item)))
                    out.extend(item)
        out.extend(self.locktime)
        return bytes(out)

    def replace_signatures(self, replacement_size: int) -> int:
        count = 0
        for txin in self.inputs:
            txin.script_sig, n = replace_script(txin.script_sig, replacement_size)
            count += n
            stack = []
            for item in txin.witness:
                if is_der_ecdsa_signature_item(item):
                    stack.append(b"\x00" * replacement_size)
                    count += 1
                else:
                    stack.append(item)
            txin.witness = stack
        return count

    def metrics(self) -> dict[str, int]:
        base = len(self.serialize(with_witness=False))
        total = len(self.serialize(with_witness=True))
        weight = base * 3 + total
        return {"base_size_bytes": base, "total_size_bytes": total,
                "weight_units": weight, "vsize_bytes": math.ceil(weight / 4)}


def request_bytes(url: str, retries: int = 6) -> bytes:
    """Fetch bytes with global request pacing, exponential backoff and Retry-After."""
    global _LAST_REQUEST_STARTED
    req = urllib.request.Request(url, headers={"User-Agent": "quantum-crypto-research/1.0"})
    for attempt in range(retries + 1):
        # Pace every API request, including tip, block metadata, txid lists and raw txs.
        elapsed = time.monotonic() - _LAST_REQUEST_STARTED
        wait_for_slot = _REQUEST_MIN_INTERVAL_SECONDS - elapsed
        if wait_for_slot > 0:
            time.sleep(wait_for_slot)
        _LAST_REQUEST_STARTED = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise RuntimeError(f"HTTP {exc.code} for {url}") from exc

            # Exponential backoff: 1, 2, 4, 8, 16, 32 seconds (capped at 60).
            wait_seconds = min(2 ** attempt, 60)
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            if retry_after:
                try:
                    wait_seconds = max(wait_seconds, float(retry_after))
                except ValueError:
                    try:
                        retry_time = parsedate_to_datetime(retry_after).timestamp()
                        wait_seconds = max(wait_seconds, retry_time - time.time())
                    except (TypeError, ValueError, OverflowError):
                        pass
            time.sleep(max(0, wait_seconds))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == retries:
                raise RuntimeError(f"Request failed for {url}: {exc}") from exc
            time.sleep(min(2 ** attempt, 60))
    raise RuntimeError(f"Request failed for {url}")


def get_json(url: str) -> dict | list:
    return json.loads(request_bytes(url).decode("utf-8"))


def fetch_recent_txids(api: str, count: int, delay: float) -> tuple[list[str], int]:
    api = api.rstrip("/")
    tip = int(request_bytes(f"{api}/blocks/tip/height").decode("ascii").strip())
    ids: list[str] = []
    height = tip
    while height >= 0 and len(ids) < count:
        block_hash = request_bytes(f"{api}/block-height/{height}").decode("ascii").strip()
        block = get_json(f"{api}/block/{block_hash}")
        # Esplora exposes all transaction IDs at /block/:hash/txids;
        # unlike /block/:hash/txs/:start_index, this endpoint has no paging suffix.
        page = get_json(f"{api}/block/{block_hash}/txids")
        if isinstance(page, list) and page:
            ids.extend(str(txid) for txid in page[:count - len(ids)])
        height -= 1
    if not ids:
        raise RuntimeError("Esplora returned no transaction IDs")
    return ids[:count], tip


def analyze_transaction(txid: str, raw_hex: str, replacement_size: int) -> dict:
    raw = bytes.fromhex(raw_hex.strip())
    tx = Transaction.parse(raw)
    if tx.serialize() != raw:
        raise TransactionFormatError("Raw transaction did not survive parse/serialize round-trip")
    original = tx.metrics()
    replacements = tx.replace_signatures(replacement_size)
    modeled = tx.metrics()
    return {
        "txid": txid, **{f"original_{k}": v for k, v in original.items()},
        "recognized_ecdsa_signatures": replacements,
        "replacement_signature_bytes": replacement_size,
        **{f"modeled_{k}": v for k, v in modeled.items()},
        "delta_total_size_bytes": modeled["total_size_bytes"] - original["total_size_bytes"],
        "delta_weight_units": modeled["weight_units"] - original["weight_units"],
        "delta_vsize_bytes": modeled["vsize_bytes"] - original["vsize_bytes"],
        "total_size_increase_percent": 100 * (modeled["total_size_bytes"] - original["total_size_bytes"]) / original["total_size_bytes"],
        "vsize_increase_percent": 100 * (modeled["vsize_bytes"] - original["vsize_bytes"]) / original["vsize_bytes"],
    }


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        raise ValueError("No valid transaction results")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_summary(rows: list[dict], tip: int, requested: int, api: str, sig_size: int) -> dict:
    changed = [r for r in rows if r["recognized_ecdsa_signatures"] > 0]
    total_pct = [r["total_size_increase_percent"] for r in changed]
    vsize_pct = [r["vsize_increase_percent"] for r in changed]
    return {
        "model": "counterfactual size model; not a Bitcoin protocol implementation",
        "api": api, "tip_height_at_collection": tip,
        "requested_transactions": requested, "analyzed_transactions": len(rows),
        "transactions_with_recognized_ecdsa_signatures": len(changed),
        "transactions_without_recognized_ecdsa_signatures": len(rows) - len(changed),
        "replacement_signature_bytes": sig_size,
        "mean_original_total_size_bytes": mean(r["original_total_size_bytes"] for r in rows),
        "median_original_total_size_bytes": median(r["original_total_size_bytes"] for r in rows),
        "mean_modeled_total_size_bytes": mean(r["modeled_total_size_bytes"] for r in rows),
        "median_modeled_total_size_bytes": median(r["modeled_total_size_bytes"] for r in rows),
        "mean_original_vsize_bytes": mean(r["original_vsize_bytes"] for r in rows),
        "median_original_vsize_bytes": median(r["original_vsize_bytes"] for r in rows),
        "mean_modeled_vsize_bytes": mean(r["modeled_vsize_bytes"] for r in rows),
        "median_modeled_vsize_bytes": median(r["modeled_vsize_bytes"] for r in rows),
        "mean_total_size_increase_percent_among_changed": mean(total_pct) if total_pct else None,
        "median_total_size_increase_percent_among_changed": median(total_pct) if total_pct else None,
        "mean_vsize_increase_percent_among_changed": mean(vsize_pct) if vsize_pct else None,
        "median_vsize_increase_percent_among_changed": median(vsize_pct) if vsize_pct else None,
        "limitations": [
            "Only strict-DER ECDSA-shaped stack items are replaced; this is structural recognition, not script execution.",
            "Schnorr signatures (including Taproot) are not classified as ECDSA and are left unchanged.",
            "The model does not define new Bitcoin consensus rules, sighash semantics, or a valid ML-DSA transaction format.",
            "Transactions without recognized ECDSA items are unchanged and included in overall means.",
            "Results describe only the sampled recent blocks, not the entire network or a future protocol upgrade."
        ]
    }


def save_summary_table(summary: dict, path: Path) -> None:
    """Write a compact comparison table in the same results/tables layout as other experiments."""
    path.parent.mkdir(parents=True, exist_ok=True)
    metrics = [
        ("Количество транзакций", summary["analyzed_transactions"], summary["analyzed_transactions"], 0, 0.0),
        ("Средний полный размер, байт", summary["mean_original_total_size_bytes"], summary["mean_modeled_total_size_bytes"],
         summary["mean_modeled_total_size_bytes"] - summary["mean_original_total_size_bytes"],
         100 * (summary["mean_modeled_total_size_bytes"] - summary["mean_original_total_size_bytes"]) / summary["mean_original_total_size_bytes"]),
        ("Медианный полный размер, байт", summary["median_original_total_size_bytes"], summary["median_modeled_total_size_bytes"],
         summary["median_modeled_total_size_bytes"] - summary["median_original_total_size_bytes"],
         100 * (summary["median_modeled_total_size_bytes"] - summary["median_original_total_size_bytes"]) / summary["median_original_total_size_bytes"]),
        ("Средний виртуальный размер (vsize), байт", summary["mean_original_vsize_bytes"], summary["mean_modeled_vsize_bytes"],
         summary["mean_modeled_vsize_bytes"] - summary["mean_original_vsize_bytes"],
         100 * (summary["mean_modeled_vsize_bytes"] - summary["mean_original_vsize_bytes"]) / summary["mean_original_vsize_bytes"]),
        ("Медианный виртуальный размер (vsize), байт", summary["median_original_vsize_bytes"], summary["median_modeled_vsize_bytes"],
         summary["median_modeled_vsize_bytes"] - summary["median_original_vsize_bytes"],
         100 * (summary["median_modeled_vsize_bytes"] - summary["median_original_vsize_bytes"]) / summary["median_original_vsize_bytes"]),
        ("Транзакции с распознанными ECDSA-подписями", summary["transactions_with_recognized_ecdsa_signatures"],
         summary["transactions_with_recognized_ecdsa_signatures"], 0, 0.0),
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Показатель", "Исходные транзакции", "Модель с ML-DSA-65", "Изменение", "Изменение, %"])
        for label, original, modeled, delta, pct in metrics:
            writer.writerow([label, round(original, 3) if isinstance(original, float) else original,
                             round(modeled, 3) if isinstance(modeled, float) else modeled,
                             round(delta, 3) if isinstance(delta, float) else delta, round(pct, 3)])


def save_plot(rows: list[dict], path: Path) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    selected = [r for r in rows if r["recognized_ecdsa_signatures"] > 0]
    if not selected:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    before = [r["original_total_size_bytes"] for r in selected]
    after = [r["modeled_total_size_bytes"] for r in selected]
    pct = [r["total_size_increase_percent"] for r in selected]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].scatter(before, after, s=12, alpha=0.65)
    limit = max(max(before), max(after))
    axes[0].plot([0, limit], [0, limit], linestyle="--")
    axes[0].set(xlabel="Original transaction size (bytes)", ylabel="Modeled transaction size (bytes)", title="Original vs modeled size")
    axes[1].hist(pct, bins=25)
    axes[1].set(xlabel="Total-size increase (%)", ylabel="Transactions", title="Increase distribution")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100, help="Recent confirmed transactions to sample (default: 100)")
    parser.add_argument("--api", default=DEFAULT_API, help="Esplora API base URL")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between API calls (seconds; conservative default for public API)")
    parser.add_argument("--signature-bytes", type=int, default=ML_DSA_65_SIGNATURE_BYTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = parser.parse_args()
    global _REQUEST_MIN_INTERVAL_SECONDS
    _REQUEST_MIN_INTERVAL_SECONDS = args.delay
    if args.count < 1 or args.signature_bytes < 1 or args.delay < 0:
        parser.error("--count and --signature-bytes must be positive; --delay must be non-negative")

    try:
        txids, tip = fetch_recent_txids(args.api, args.count, args.delay)
    except RuntimeError as exc:
        # If the public API keeps rate-limiting discovery, make one conservative
        # fallback attempt with a smaller sample after a cooldown.
        if "HTTP 429" not in str(exc) or args.count <= 400:
            raise
        print(f"[WARN] Rate limit while collecting transaction IDs; reducing sample {args.count} -> 400 and waiting 60 seconds.")
        time.sleep(60)
        args.count = 400
        txids, tip = fetch_recent_txids(args.api, args.count, args.delay)
    rows = []
    api = args.api.rstrip("/")
    for i, txid in enumerate(txids, 1):
        try:
            raw_hex = request_bytes(f"{api}/tx/{txid}/hex").decode("ascii")
            rows.append(analyze_transaction(txid, raw_hex, args.signature_bytes))
        except (RuntimeError, ValueError) as exc:
            print(f"[WARN] Skipping {txid}: {exc}")
        if i % 25 == 0 or i == len(txids):
            print(f"Processed {i}/{len(txids)} IDs; analyzed {len(rows)}")
    if not rows:
        raise RuntimeError("No transactions could be analyzed")
    write_csv(rows, args.output)
    summary = make_summary(rows, tip, args.count, api, args.signature_bytes)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    save_summary_table(summary, args.table)
    plotted = save_plot(rows, args.figure)
    print(f"CSV: {args.output}")
    print(f"Summary JSON: {args.summary}")
    print(f"Comparison table: {args.table}")
    print(f"Mean total size: {summary['mean_original_total_size_bytes']:.1f} -> {summary['mean_modeled_total_size_bytes']:.1f} bytes")
    print(f"Transactions with recognized ECDSA signatures: {summary['transactions_with_recognized_ecdsa_signatures']}/{len(rows)}")
    if plotted:
        print(f"Plot: {args.figure}")
    else:
        print("Plot skipped (optional matplotlib missing or no recognized ECDSA signatures).")
    print("IMPORTANT: counterfactual size model only; not a valid Bitcoin protocol implementation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
