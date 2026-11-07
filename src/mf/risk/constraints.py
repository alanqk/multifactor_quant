"""Portfolio risk overlays: name/sector caps, costs, drawdown halt, optional vol target."""

from __future__ import annotations

import numpy as np
import pandas as pd


def apply_name_cap(weights: pd.Series, max_w: float) -> pd.Series:
    w = weights.clip(upper=max_w)
    s = w.sum()
    return w / s if s > 0 else w


def apply_sector_cap(weights: pd.Series, sector: pd.Series | None, max_sector: float) -> pd.Series:
    if sector is None or weights.empty:
        return weights
    w = weights.copy()
    sec = sector.reindex(w.index)
    for _ in range(5):  # iterative squash
        over = False
        for name, grp in w.groupby(sec):
            tot = grp.sum()
            if tot > max_sector + 1e-12:
                over = True
                w.loc[grp.index] = grp * (max_sector / tot)
        s = w.sum()
        if s > 0:
            w = w / s
        if not over:
            break
    return w


def apply_costs(turnover: pd.Series, cost_bps_one_way: float) -> pd.Series:
    """turnover is one-way sum |Δw|; cost = turnover * bps/1e4."""
    return turnover * (cost_bps_one_way / 1e4)


def vol_target_scaler(
    port_ret: pd.Series,
    target: float,
    lookback: int = 63,
    max_leverage: float = 2.0,
) -> pd.Series:
    realized = port_ret.rolling(lookback, min_periods=21).std() * np.sqrt(252)
    scale = (target / realized).clip(upper=max_leverage)
    return scale.fillna(1.0)


def drawdown_halt_mask(equity: pd.Series, halt: float = -0.20) -> pd.Series:
    """True = invest; False = flattened due to drawdown."""
    peak = equity.cummax()
    dd = equity / peak - 1.0
    # once halted, stay flat until new high (simple circuit breaker)
    halted = False
    flags = []
    for d in dd:
        if halted:
            if d >= -1e-12:  # recovered to peak
                halted = False
            flags.append(not halted)
        else:
            if d <= halt:
                halted = True
                flags.append(False)
            else:
                flags.append(True)
    return pd.Series(flags, index=equity.index)
