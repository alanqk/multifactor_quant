"""Low-volatility factor with zombie filter and optional industry neutralization."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mf.factors.utils import cs_rank, industry_neutralize


def low_vol_factor(
    returns: pd.DataFrame,
    *,
    lookback: int = 250,
    zombie_zero_frac: float = 0.50,
    sector: pd.Series | None = None,
    industry_neutral: bool = True,
) -> pd.DataFrame:
    """Lower realized vol = more attractive after industry neutralization."""
    vol = returns.rolling(lookback, min_periods=max(60, lookback // 2)).std()
    zero_frac = (
        returns.eq(0)
        .rolling(lookback, min_periods=max(60, lookback // 2))
        .mean()
    )
    vol = vol.where(zero_frac <= zombie_zero_frac)

    if industry_neutral and sector is not None:
        vol_n = industry_neutralize(vol, sector)
    else:
        vol_n = vol

    # lower vol → higher score
    return cs_rank(vol_n, ascending=False)
