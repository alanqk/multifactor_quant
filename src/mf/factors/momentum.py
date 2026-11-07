"""Classic 12-1 price momentum."""

from __future__ import annotations

import pandas as pd

from mf.factors.utils import cs_rank


def momentum_12_1(close: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Cumulative return over lookback, excluding most recent `skip` days; higher = better."""
    # r = P_{t-skip} / P_{t-lookback} - 1
    num = close.shift(skip)
    den = close.shift(lookback)
    raw = num / den - 1.0
    return cs_rank(raw, ascending=True)  # higher return → higher rank
