#!/usr/bin/env python3
"""Validate the dashboard snapshot and publish it to the static site.

``scripts/run_backtest.py`` writes the full payload (equity, stats, holdings,
factor ranks, ticker names) to ``dashboard/dash_data.json`` and copies it to
``web/data/dash_data.json``. This script checks that file, fills company name
and exchange from ``data/raw/TICKERS.csv`` when those columns exist, and
writes both paths again so a hand-edited snapshot still reaches GitHub Pages.

``reports/equity_curve.csv`` has no holdings, so this script does not rebuild
the snapshot from the equity curve. Refresh the numbers with::

    python scripts/run_backtest.py
    python scripts/export_dashboard_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

from mf.dashboard_data import (  # noqa: E402
    enrich_tickers,
    ensure_risk,
    validate_payload,
    write_snapshots,
)

SRC = ROOT / "dashboard" / "dash_data.json"
TICKERS = ROOT / "data" / "raw" / "TICKERS.csv"


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing snapshot: {SRC}")
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text(encoding="utf-8"))
    ensure_risk(
        payload,
        ROOT / "reports" / "equity_curve.csv",
        max_name_weight=cfg["portfolio"]["max_name_weight"],
        drawdown_halt=cfg["risk"].get("drawdown_halt"),
    )
    validate_payload(payload)
    enrich_tickers(payload, TICKERS)
    written = write_snapshots(payload, ROOT)
    for path in written:
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
