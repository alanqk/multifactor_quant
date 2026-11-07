"""Simplified QMJ: profitability, growth, safety."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mf.data.loader import asof_fundamental_panel
from mf.factors.utils import cs_rank, safe_div


def _cagr_from_level(level: pd.DataFrame, years: int, min_years: int) -> pd.DataFrame:
    """Approximate N-year CAGR of a quarterly/TTM fundamental level panel.

    Uses shift by ~252 * years trading days on the daily PIT panel.
    """
    # trading-day approximation
    lag = int(252 * years)
    min_lag = int(252 * min_years)
    past = level.shift(lag)
    # if 5y mostly empty (short sample), try min_years
    ratio = level / past.replace(0, np.nan)
    cagr = ratio.pow(1.0 / years) - 1.0
    # fallback shorter window where 5y unavailable
    past_min = level.shift(min_lag)
    ratio_min = level / past_min.replace(0, np.nan)
    cagr_min = ratio_min.pow(1.0 / min_years) - 1.0
    return cagr.fillna(cagr_min)


def quality_factor(
    close: pd.DataFrame,
    fundamentals: pd.DataFrame,
    *,
    dimension: str = "ART",
    target_cagr_years: int = 5,
    min_years: int = 3,
) -> pd.DataFrame:
    tickers = list(close.columns)
    dates = close.index
    fields = ["gp", "assets", "ebit", "intexp", "interestcoverage"]
    panel = asof_fundamental_panel(fundamentals, dates, tickers, fields, dimension=dimension)

    gpa = safe_div(panel["gp"], panel["assets"])  # gross profits / assets
    growth = _cagr_from_level(gpa, years=target_cagr_years, min_years=min_years)

    # safety: interest coverage; compute if needed
    coverage = panel["interestcoverage"]
    if coverage.isna().all().all():
        coverage = safe_div(panel["ebit"], panel["intexp"].abs())
    # cap extremes
    coverage = coverage.clip(lower=-10, upper=100)

    ranks = [
        cs_rank(gpa, ascending=True),
        cs_rank(growth, ascending=True),
        cs_rank(coverage, ascending=True),
    ]
    stacked = pd.concat(ranks, axis=0, keys=range(len(ranks)))
    return stacked.groupby(level=1).mean()
