#!/usr/bin/env python3
"""Copy the dashboard snapshot into the static site.

``reports/stats.json`` and ``reports/equity_curve.csv`` do not include
holdings or factor ranks, so this script does not rebuild the snapshot from
those reports. The full payload lives in ``dashboard/dash_data.json``. After
that file is refreshed, run::

    python scripts/export_dashboard_data.py

It validates the required keys and copies the file to
``web/data/dash_data.json`` for GitHub Pages.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "dashboard" / "dash_data.json"
DEST = ROOT / "web" / "data" / "dash_data.json"

REQUIRED = (
    "meta",
    "stats",
    "equity",
    "months",
    "holdings",
    "factor_ranks",
    "tickers",
    "calendar",
)


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing snapshot: {SRC}")
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED if key not in payload]
    if missing:
        raise SystemExit(f"{SRC.name} missing keys: {', '.join(missing)}")
    if not payload["equity"]:
        raise SystemExit(f"{SRC.name} has an empty equity series")
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DEST)
    print(f"Copied {SRC.relative_to(ROOT)} -> {DEST.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
