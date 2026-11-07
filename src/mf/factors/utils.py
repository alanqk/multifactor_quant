"""Cross-sectional ranking helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


def cs_rank(df: pd.DataFrame, ascending: bool = True) -> pd.DataFrame:
    """Percentile rank in [0, 1] across columns (tickers) for each row (date)."""
    return df.rank(axis=1, pct=True, ascending=ascending, method="average")


def cs_zscore(df: pd.DataFrame) -> pd.DataFrame:
    mu = df.mean(axis=1)
    sd = df.std(axis=1).replace(0, np.nan)
    return df.sub(mu, axis=0).div(sd, axis=0)


def industry_neutralize(raw: pd.DataFrame, sector: pd.Series | None) -> pd.DataFrame:
    """Subtract cross-sectional sector mean (within date). If no sector, return raw."""
    if sector is None:
        return raw
    out = raw.copy()
    # map columns to sector
    sec = sector.reindex(raw.columns)
    for dt, row in raw.iterrows():
        s = row.copy()
        for name, grp in s.groupby(sec):
            if name is None or (isinstance(name, float) and np.isnan(name)):
                continue
            s.loc[grp.index] = grp - grp.mean()
        out.loc[dt] = s
    return out


def safe_div(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return a.div(b.replace(0, np.nan))
