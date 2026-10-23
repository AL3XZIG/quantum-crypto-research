#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python -m pip install -r requirements-app.txt
exec python -m streamlit run app_bitcoin_pqc.py
