"""Hard universe filters applied before ranking / weighting."""

from __future__ import annotations

import pandas as pd


def liquidity_price_mask(
    close: pd.DataFrame,
    volume: pd.DataFrame,
    *,
    min_price: float = 5.0,
    min_adv_usd: float = 1_000_000,
    adv_window: int = 20,
    min_history_days: int = 252,
) -> pd.DataFrame:
    """Boolean mask: True = tradable."""
    adv = (close * volume).rolling(adv_window, min_periods=max(5, adv_window // 2)).mean()
    hist = close.expanding().count()
    return (
        close.ge(min_price)
        & adv.ge(min_adv_usd)
        & hist.ge(min_history_days)
        & close.notna()
    )
