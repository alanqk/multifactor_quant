#!/usr/bin/env python3
"""Refresh the committed CBOE VIX daily close.

The dashboard does not call this in CI. ``data/market/VIX.csv`` is already
in the repo so a backtest export stays offline. Run this only to extend the
file, then commit the CSV. Source:

https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
"""

from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data" / "market" / "VIX.csv"
URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
START = "2020-01-01"


def main() -> None:
    with urlopen(URL, timeout=60) as response:
        text = response.read().decode("utf-8")
    rows = []
    for row in csv.DictReader(StringIO(text)):
        day = datetime.strptime(row["DATE"].strip(), "%m/%d/%Y").date()
        if day.isoformat() < START:
            continue
        rows.append((day.isoformat(), f"{float(row['CLOSE']):.4f}"))
    if not rows:
        raise SystemExit("CBOE file had no rows on or after " + START)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text("date,close\n" + "\n".join(f"{day},{close}" for day, close in rows) + "\n", encoding="utf-8")
    print(f"Wrote {DEST.relative_to(ROOT)} ({len(rows)} rows, {rows[0][0]} → {rows[-1][0]})")


if __name__ == "__main__":
    main()
