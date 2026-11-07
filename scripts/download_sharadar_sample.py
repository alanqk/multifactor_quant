#!/usr/bin/env python3
"""Download Sharadar free DJIA sample via test-api-key (per-ticker REST)."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mf.data.sharadar_api import download_sample  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text())
    data_cfg = cfg["data"]
    out = ROOT / data_cfg["raw_dir"]
    paths = download_sample(
        out,
        data_cfg["sample_tickers"],
        api_key=data_cfg.get("api_key", "test-api-key"),
        price_from=data_cfg.get("price_from", "2018-01-01"),
        fund_dimensions=data_cfg.get("fund_dimensions", ["ART", "ARQ"]),
    )
    if "SEP" not in paths:
        raise SystemExit("Download failed: no SEP prices written")
    print("Done:", {k: str(v) for k, v in paths.items()})


if __name__ == "__main__":
    main()
