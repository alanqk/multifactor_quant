"""Multi-metric value factor with PIT fundamentals."""

from __future__ import annotations

import numpy as np
import pandas as pd

from mf.data.loader import asof_fundamental_panel
from mf.factors.utils import cs_rank, safe_div


def value_factor(
    close: pd.DataFrame,
    fundamentals: pd.DataFrame,
    *,
    dimension: str = "ART",
) -> pd.DataFrame:
    """Equal-weight CS ranks of E/P, B/P, S/P, EBITDA/EV (higher cheapness = better)."""
    tickers = list(close.columns)
    dates = close.index
    fields = [
        "netinc",
        "equity",
        "revenue",
        "ebitda",
        "ev",
        "marketcap",
        "pe",
        "pb",
        "ps",
        "evebitda",
    ]
    panel = asof_fundamental_panel(fundamentals, dates, tickers, fields, dimension=dimension)

    # Prefer computing from statements + marketcap/ev (PIT via asof date).
    # Fallback to inverted valuation multiples if components missing.
    ep = safe_div(panel["netinc"], panel["marketcap"])
    if ep.isna().all().all() and not panel["pe"].isna().all().all():
        ep = 1.0 / panel["pe"].replace(0, np.nan)

    bp = safe_div(panel["equity"], panel["marketcap"])
    if bp.isna().all().all() and not panel["pb"].isna().all().all():
        bp = 1.0 / panel["pb"].replace(0, np.nan)

    sp = safe_div(panel["revenue"], panel["marketcap"])
    if sp.isna().all().all() and not panel["ps"].isna().all().all():
        sp = 1.0 / panel["ps"].replace(0, np.nan)

    ebitda_ev = safe_div(panel["ebitda"], panel["ev"])
    if ebitda_ev.isna().all().all() and not panel["evebitda"].isna().all().all():
        ebitda_ev = 1.0 / panel["evebitda"].replace(0, np.nan)

    ranks = [
        cs_rank(ep, ascending=True),
        cs_rank(bp, ascending=True),
        cs_rank(sp, ascending=True),
        cs_rank(ebitda_ev, ascending=True),
    ]
    stacked = pd.concat(ranks, axis=0, keys=range(len(ranks)))
    return stacked.groupby(level=1).mean()
