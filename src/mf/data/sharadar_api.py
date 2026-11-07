"""Sharadar REST helpers (free test-api-key = DJIA sample)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

DEFAULT_BASE = "https://api.sharadar.com/v1.0/data"


class SharadarClient:
    def __init__(self, api_key: str = "test-api-key", base: str = DEFAULT_BASE, pause: float = 0.15):
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.pause = pause
        self.session = requests.Session()

    def _get(self, table: str, params: dict) -> pd.DataFrame:
        params = {"api_key": self.api_key, "format": "csv", **params}
        url = f"{self.base}/{table}"
        r = self.session.get(url, params=params, timeout=120)
        if r.status_code == 403:
            raise PermissionError(f"Free tier rejected {params.get('ticker')}: {r.text[:200]}")
        r.raise_for_status()
        if not r.text.strip() or r.text.startswith("{") or r.text.startswith("<"):
            raise RuntimeError(f"Unexpected response for {table}: {r.text[:300]}")
        from io import StringIO

        df = pd.read_csv(StringIO(r.text))
        time.sleep(self.pause)
        return df

    def fetch_paged(
        self,
        table: str,
        *,
        ticker: str,
        page_size: int = 10000,
        extra: dict | None = None,
    ) -> pd.DataFrame:
        """Page through results with skip/limit (API default limit=10000)."""
        frames: list[pd.DataFrame] = []
        skip = 0
        extra = extra or {}
        while True:
            df = self._get(
                table,
                {"ticker": ticker, "limit": page_size, "skip": skip, **extra},
            )
            if df.empty:
                break
            frames.append(df)
            if len(df) < page_size:
                break
            skip += page_size
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def download_sample(
    out_dir: Path,
    tickers: Iterable[str],
    *,
    api_key: str = "test-api-key",
    price_from: str = "2018-01-01",
    fund_dimensions: Iterable[str] = ("ART", "ARQ"),
) -> dict[str, Path]:
    """Download SEP prices, SF1 fundamentals, and TICKERS for the free DJIA sample."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    client = SharadarClient(api_key=api_key)

    tickers = list(tickers)
    prices: list[pd.DataFrame] = []
    funds: list[pd.DataFrame] = []
    metas: list[pd.DataFrame] = []
    failed: list[str] = []

    for t in tickers:
        try:
            p = client.fetch_paged(
                "stocks",
                ticker=t,
                extra={"from": price_from, "sort": "date.asc"},
            )
            if not p.empty:
                prices.append(p)

            # fundamentals: pull ART+ARQ without date filter (free key scopes history)
            f = client.fetch_paged(
                "fundamentals",
                ticker=t,
                extra={"sort": "date.asc"},
            )
            if not f.empty and "dimension" in f.columns:
                f = f[f["dimension"].isin(list(fund_dimensions))]
            if not f.empty:
                funds.append(f)

            m = client._get("tickers", {"ticker": t})
            if not m.empty:
                # keep stocks row if present, else first
                if "table" in m.columns:
                    stocks_rows = m[m["table"] == "stocks"]
                    m = stocks_rows if not stocks_rows.empty else m.iloc[[0]]
                metas.append(m)
            print(f"[ok] {t}: prices={len(p)} funds={0 if f is None or f.empty else len(f)}")
        except Exception as e:  # noqa: BLE001
            failed.append(t)
            print(f"[fail] {t}: {e}")

    paths: dict[str, Path] = {}
    if prices:
        sep = pd.concat(prices, ignore_index=True)
        sep = sep.drop_duplicates(subset=["ticker", "date"]).sort_values(["ticker", "date"])
        p = out_dir / "SEP.csv"
        sep.to_csv(p, index=False)
        paths["SEP"] = p
        print(f"Wrote {p} ({len(sep):,} rows)")
    if funds:
        sf1 = pd.concat(funds, ignore_index=True)
        sf1 = sf1.drop_duplicates(subset=["ticker", "dimension", "date", "calendardate"], keep="last")
        p = out_dir / "SF1.csv"
        sf1.to_csv(p, index=False)
        paths["SF1"] = p
        print(f"Wrote {p} ({len(sf1):,} rows)")
    if metas:
        tick = pd.concat(metas, ignore_index=True).drop_duplicates(subset=["ticker"], keep="first")
        p = out_dir / "TICKERS.csv"
        tick.to_csv(p, index=False)
        paths["TICKERS"] = p
        print(f"Wrote {p} ({len(tick):,} rows)")

    if failed:
        print(f"Failed tickers ({len(failed)}): {failed}")
    return paths
