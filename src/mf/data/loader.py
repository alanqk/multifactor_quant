"""Load and align Sharadar sample tables into research panels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class MarketData:
    prices: pd.DataFrame          # long: date, ticker, open, high, low, close, volume, closeadj, ...
    fundamentals: pd.DataFrame    # long SF1 ART/ARQ
    tickers: pd.DataFrame         # reference
    close: pd.DataFrame           # wide closeadj (or close)
    volume: pd.DataFrame
    returns: pd.DataFrame
    sector: pd.Series | None      # ticker -> sector


def _read_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in ("date", "calendardate", "reportperiod", "lastupdated", "firstpricedate", "lastpricedate"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def load_sharadar(raw_dir: str | Path) -> MarketData:
    raw = Path(raw_dir)
    sep_path = raw / "SEP.csv"
    sf1_path = raw / "SF1.csv"
    tick_path = raw / "TICKERS.csv"

    if not sep_path.exists():
        raise FileNotFoundError(f"Missing {sep_path}; run scripts/download_sharadar_sample.py")

    prices = _read_csv(sep_path)
    # Prefer total-return style closeadj for factor returns
    px_col = "closeadj" if "closeadj" in prices.columns and prices["closeadj"].notna().any() else "close"
    prices = prices.sort_values(["ticker", "date"])
    close = prices.pivot(index="date", columns="ticker", values=px_col).sort_index()
    volume = prices.pivot(index="date", columns="ticker", values="volume").sort_index()
    returns = close.pct_change()

    fundamentals = _read_csv(sf1_path) if sf1_path.exists() else pd.DataFrame()
    tickers = _read_csv(tick_path) if tick_path.exists() else pd.DataFrame()

    sector = None
    if not tickers.empty:
        # Prefer GICS-like sector; fall back to sicsector / famaindustry
        for col in ("sector", "sicsector", "famaindustry", "industry"):
            if col in tickers.columns and tickers[col].notna().any():
                sector = tickers.drop_duplicates("ticker").set_index("ticker")[col]
                break

    return MarketData(
        prices=prices,
        fundamentals=fundamentals,
        tickers=tickers,
        close=close,
        volume=volume,
        returns=returns,
        sector=sector,
    )


def asof_fundamental_panel(
    fundamentals: pd.DataFrame,
    dates: pd.DatetimeIndex,
    tickers: list[str],
    fields: list[str],
    dimension: str = "ART",
) -> dict[str, pd.DataFrame]:
    """Point-in-time merge: on each date use latest fundamental with fund.date <= date.

    Sharadar SF1 `date` is the availability / filing date — use it for PIT, not calendardate.
    """
    if fundamentals.empty:
        empty = {f: pd.DataFrame(index=dates, columns=tickers, dtype=float) for f in fields}
        return empty

    f = fundamentals.copy()
    if "dimension" in f.columns:
        f = f[f["dimension"] == dimension]
    f = f[f["ticker"].isin(tickers)].dropna(subset=["date"])
    f = f.sort_values(["ticker", "date"])

    out: dict[str, pd.DataFrame] = {}
    for field in fields:
        if field not in f.columns:
            out[field] = pd.DataFrame(index=dates, columns=tickers, dtype=float)
            continue
        wide_rows = []
        # vectorized asof per ticker
        panel = {}
        for t, g in f.groupby("ticker"):
            s = g.set_index("date")[field].sort_index()
            # reindex asof onto research dates
            aligned = s.reindex(dates, method="ffill")
            # only forward-fill values whose fund date <= research date (reindex ffill does this
            # when index is fund dates subset; ensure no future leak by masking)
            # reindex(method='ffill') on dates only ffills from past fund dates — correct PIT
            panel[t] = aligned
        df = pd.DataFrame(panel, index=dates)
        # ensure all tickers present
        for t in tickers:
            if t not in df.columns:
                df[t] = np.nan
        out[field] = df[tickers]
    return out
