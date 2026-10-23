"""Local Streamlit dashboard for Bitcoin post-quantum size scenarios.

Run from the repository root:
    python -m streamlit run app_bitcoin_pqc.py

This dashboard is an educational counterfactual model, not a Bitcoin protocol
implementation and not a prediction of future fee-market prices.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from experiments.transaction.bitcoin_pqc_network_impact import (
    DEFAULT_BLOCK_WEIGHT_LIMIT,
    DEFAULT_BLOCKS_PER_DAY,
    DEFAULT_CONVERSION_SHARES,
    DEFAULT_FEE_RATES,
    DEFAULT_INPUT,
    block_capacity_scenarios,
    fee_scenarios,
    load_rows,
    save_csv,
)

ROOT = Path(__file__).resolve().parent
FEE_CSV = ROOT / "results" / "tables" / "bitcoin_pqc_fee_scenarios.csv"
BLOCK_CSV = ROOT / "results" / "tables" / "bitcoin_pqc_block_capacity.csv"
STORAGE_CSV = ROOT / "results" / "tables" / "bitcoin_pqc_node_storage.csv"
FEE_PNG = ROOT / "results" / "figures" / "bitcoin_pqc_fee_scenarios.png"
BLOCK_PNG = ROOT / "results" / "figures" / "bitcoin_pqc_block_capacity.png"
STORAGE_PNG = ROOT / "results" / "figures" / "bitcoin_pqc_node_storage.png"


st.set_page_config(page_title="Bitcoin PQC Lab", page_icon="₿", layout="wide")
st.title("Bitcoin PQC Lab")
st.caption("Комиссии · вес транзакций и блоков · хранение данных узлов")
st.warning(
    "Это сценарная модель. Она не создаёт валидные Bitcoin-транзакции с ML-DSA, "
    "не меняет правила консенсуса и не предсказывает рыночные комиссии."
)

with st.sidebar:
    st.header("Параметры эксперимента")
    uploaded = st.file_uploader("CSV с результатами анализа транзакций", type=["csv"])
    input_path = st.text_input("Или путь к CSV", value=str(DEFAULT_INPUT))
    fee_rates = st.multiselect(
        "Ставки комиссии (sat/vB)",
        options=[1, 2, 5, 10, 25, 50, 100, 200],
        default=list(DEFAULT_FEE_RATES),
    )
    shares = st.multiselect(
        "Доля транзакций с увеличенными подписями (%)",
        options=[0, 10, 25, 50, 75, 90, 100],
        default=list(DEFAULT_CONVERSION_SHARES),
    )
    block_weight_limit = st.number_input(
        "Лимит веса блока (WU)",
        min_value=100_000,
        max_value=4_000_000,
        value=DEFAULT_BLOCK_WEIGHT_LIMIT,
        step=100_000,
    )
    blocks_per_day = st.number_input(
        "Блоков в сутки (сценарное допущение)",
        min_value=1,
        max_value=300,
        value=DEFAULT_BLOCKS_PER_DAY,
        step=1,
    )
    run_button = st.button("Рассчитать и сохранить", type="primary", use_container_width=True)
    test_button = st.button("Запустить тесты модели", use_container_width=True)


def get_rows():
    if uploaded is not None:
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as temp_file:
            temp_file.write(uploaded.getvalue())
            temp_path = Path(temp_file.name)
        try:
            return load_rows(temp_path), Path(uploaded.name)
        finally:
            temp_path.unlink(missing_ok=True)
    path = Path(input_path).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return load_rows(path), path


if test_button:
    with st.spinner("Запускаю автоматические тесты..."):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/test_bitcoin_pqc_network_impact.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
    if result.returncode == 0:
        st.success("Тесты завершились успешно.")
    else:
        st.error("Тесты завершились с ошибкой.")
    st.code((result.stdout + "\n" + result.stderr).strip() or "Нет вывода")

if run_button:
    if not fee_rates:
        st.error("Выбери хотя бы одну ставку комиссии.")
    elif not shares:
        st.error("Выбери хотя бы одну долю перехода.")
    else:
        try:
            rows, source_path = get_rows()
            fees = fee_scenarios(rows, rates=tuple(sorted(fee_rates)))
            blocks = block_capacity_scenarios(
                rows,
                block_weight_limit=int(block_weight_limit),
                shares=tuple(sorted(shares)),
                blocks_per_day=int(blocks_per_day),
            )
            fee_df = pd.DataFrame(fees)
            block_df = pd.DataFrame(blocks)
            storage_cols = [
                "modeled_transaction_share_percent",
                "estimated_transaction_payload_per_full_block_mb",
                "assumed_full_blocks_per_day",
                "estimated_transaction_payload_per_day_gb",
                "estimated_transaction_payload_per_year_gb",
                "estimated_transaction_payload_per_year_tib",
            ]
            storage_df = block_df[storage_cols].copy()

            save_csv(fees, FEE_CSV)
            save_csv(blocks, BLOCK_CSV)
            save_csv(storage_df.to_dict(orient="records"), STORAGE_CSV)

            for path in (FEE_PNG, BLOCK_PNG, STORAGE_PNG):
                path.parent.mkdir(parents=True, exist_ok=True)

            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.plot(fee_df["fee_rate_sat_vB"], fee_df["median_fee_original_sat"], marker="o", label="Исходная")
            ax.plot(fee_df["fee_rate_sat_vB"], fee_df["median_fee_modeled_sat"], marker="o", label="Модель ML-DSA-65")
            ax.set(xlabel="Ставка комиссии (sat/vB)", ylabel="Медианная комиссия (sat)", title="Комиссия при фиксированной ставке")
            ax.grid(True, alpha=0.25)
            ax.legend()
            fig.tight_layout()
            fig.savefig(FEE_PNG, dpi=160)
            st.session_state["fee_png"] = FEE_PNG.read_bytes()
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.plot(block_df["modeled_transaction_share_percent"], block_df["estimated_transactions_per_full_block_upper_bound"], marker="o")
            ax.set(xlabel="Доля мигрировавших транзакций (%)", ylabel="Транзакций на блок (верхняя оценка)", title="Оценка вместимости блока")
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            fig.savefig(BLOCK_PNG, dpi=160)
            st.session_state["block_png"] = BLOCK_PNG.read_bytes()
            plt.close(fig)

            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.plot(block_df["modeled_transaction_share_percent"], block_df["estimated_transaction_payload_per_year_gb"], marker="o")
            ax.set(xlabel="Доля мигрировавших транзакций (%)", ylabel="Данные транзакций за год (GB)", title="Сценарий объёма данных узла")
            ax.grid(True, alpha=0.25)
            fig.tight_layout()
            fig.savefig(STORAGE_PNG, dpi=160)
            st.session_state["storage_png"] = STORAGE_PNG.read_bytes()
            plt.close(fig)

            st.session_state["fees"] = fee_df
            st.session_state["blocks"] = block_df
            st.session_state["storage"] = storage_df
            st.session_state["source"] = str(source_path)
            st.session_state["sample_count"] = len(rows)
            st.success(f"Расчёт завершён: обработано {len(rows)} транзакций. CSV и PNG сохранены в репозитории.")
        except Exception as exc:
            st.error(f"Не удалось выполнить расчёт: {exc}")

if "fees" in st.session_state:
    st.caption(f"Источник: {st.session_state['source']} · транзакций: {st.session_state['sample_count']}")
    tab_fees, tab_blocks, tab_storage, tab_exports = st.tabs(
        ["Комиссии", "Вес и вместимость блоков", "Хранение узла", "Экспорт"]
    )
    with tab_fees:
        st.subheader("Сценарии комиссий")
        st.dataframe(st.session_state["fees"], use_container_width=True, hide_index=True)
        st.image(st.session_state["fee_png"], caption="Медианная комиссия при фиксированных ставках")
    with tab_blocks:
        st.subheader("Вес и вместимость блоков")
        st.dataframe(st.session_state["blocks"], use_container_width=True, hide_index=True)
        st.image(st.session_state["block_png"], caption="Верхняя оценка числа транзакций на блок")
    with tab_storage:
        st.subheader("Сценарный объём данных транзакций")
        st.dataframe(st.session_state["storage"], use_container_width=True, hide_index=True)
        st.image(st.session_state["storage_png"], caption="Объём сериализованных данных транзакций за год")
    with tab_exports:
        for label, key, filename in [
            ("График комиссий PNG", "fee_png", "bitcoin_pqc_fee_scenarios.png"),
            ("График вместимости блоков PNG", "block_png", "bitcoin_pqc_block_capacity.png"),
            ("График хранения PNG", "storage_png", "bitcoin_pqc_node_storage.png"),
        ]:
            st.download_button(label, st.session_state[key], file_name=filename, mime="image/png")
        for label, key, filename in [
            ("Таблица комиссий CSV", "fees", "bitcoin_pqc_fee_scenarios.csv"),
            ("Таблица блоков CSV", "blocks", "bitcoin_pqc_block_capacity.csv"),
            ("Таблица хранения CSV", "storage", "bitcoin_pqc_node_storage.csv"),
        ]:
            csv_bytes = st.session_state[key].to_csv(index=False).encode("utf-8")
            st.download_button(label, csv_bytes, file_name=filename, mime="text/csv")
else:
    st.info("Настрой параметры слева и нажми «Рассчитать и сохранить».")

st.divider()
st.markdown(
    "**Интерпретация:** комиссия здесь рассчитывается при заданной ставке sat/vB. "
    "Модель вместимости блока использует средний вес выборки и не учитывает все накладные данные блока; "
    "годовое хранение предполагает полностью заполненные блоки, заданное число блоков в сутки и отсутствие pruning."
)
