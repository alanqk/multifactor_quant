"""Vectorized monthly-rebalance long-only backtest."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mf.portfolio.weights import scores_to_weights
from mf.risk.constraints import apply_costs, drawdown_halt_mask, vol_target_scaler


@dataclass
class BacktestResult:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    stats: dict
    benchmark: pd.Series
    ic: pd.Series | None


def _month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    # last available session in each calendar month
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).max().values)


def run_backtest(
    score: pd.DataFrame,
    returns: pd.DataFrame,
    tradable: pd.DataFrame,
    *,
    sector: pd.Series | None = None,
    long_pct: float = 0.30,
    weighting: str = "equal",
    max_name_weight: float = 0.10,
    max_sector_weight: float = 0.35,
    min_names: int = 5,
    cost_bps_one_way: float = 10.0,
    vol_target: float | None = None,
    drawdown_halt: float | None = -0.20,
    initial_capital: float = 1_000_000.0,
) -> BacktestResult:
    idx = returns.index.intersection(score.index).intersection(tradable.index)
    returns = returns.loc[idx]
    score = score.loc[idx]
    tradable = tradable.loc[idx]

    rebalance_days = _month_ends(idx)
    # need score available → start after first rebalance with enough factor history
    rebalance_days = rebalance_days[rebalance_days.isin(idx)]

    weight_hist = []
    prev_w = pd.Series(dtype=float)
    daily_w = pd.DataFrame(0.0, index=idx, columns=returns.columns)
    turnover = pd.Series(0.0, index=idx)

    for i, dt in enumerate(rebalance_days):
        w = scores_to_weights(
            score.loc[dt],
            tradable.loc[dt],
            long_pct=long_pct,
            weighting=weighting,
            max_name_weight=max_name_weight,
            max_sector_weight=max_sector_weight,
            min_names=min_names,
            sector=sector,
        )
        if w.empty:
            continue
        # turnover vs previous (aligned)
        aligned_prev = prev_w.reindex(w.index).fillna(0.0)
        aligned_new = w.reindex(prev_w.index.union(w.index)).fillna(0.0)
        aligned_prev = prev_w.reindex(aligned_new.index).fillna(0.0)
        to = (aligned_new - aligned_prev).abs().sum()
        # one-way turnover convention: 0.5 * L1
        to = 0.5 * to
        turnover.loc[dt] = to

        # hold until day before next rebalance
        if i + 1 < len(rebalance_days):
            nxt = rebalance_days[i + 1]
            hold_idx = idx[(idx >= dt) & (idx < nxt)]
        else:
            hold_idx = idx[idx >= dt]
        for c, val in w.items():
            if c in daily_w.columns:
                daily_w.loc[hold_idx, c] = val
        prev_w = w
        weight_hist.append(w.rename(dt))

    # portfolio returns: use previous close weights * next day return (no look-ahead)
    # weights set at dt close → earn return from dt→dt+1 onward; shift weights by 1
    w_lag = daily_w.shift(1).fillna(0.0)
    gross = (w_lag * returns.fillna(0.0)).sum(axis=1)
    costs = apply_costs(turnover, cost_bps_one_way)
    # apply cost on rebalance day (already on idx)
    net = gross - costs

    if vol_target is not None:
        scale = vol_target_scaler(net, vol_target)
        # lag scale by 1 to avoid look-ahead
        net = net * scale.shift(1).fillna(1.0)

    equity = (1.0 + net).cumprod() * initial_capital

    if drawdown_halt is not None:
        invest = drawdown_halt_mask(equity, drawdown_halt)
        # when not invest, zero out subsequent returns until recovery logic in mask
        net = net.where(invest.shift(1).fillna(True), 0.0)
        equity = (1.0 + net).cumprod() * initial_capital

    # equal-weight benchmark of universe
    n_avail = tradable.astype(float)
    n_avail = n_avail.where(n_avail > 0)
    ew = returns.where(tradable).mean(axis=1).fillna(0.0)
    bench_eq = (1.0 + ew).cumprod() * initial_capital

    # Rank IC: Spearman of score vs forward 21d return on rebalance days
    fwd = returns.rolling(21).sum().shift(-21)
    ics = []
    for dt in rebalance_days:
        if dt not in score.index:
            continue
        a = score.loc[dt]
        b = fwd.loc[dt] if dt in fwd.index else None
        if b is None:
            continue
        df = pd.concat([a, b], axis=1, keys=["s", "r"]).dropna()
        if len(df) < 5:
            continue
        ics.append((dt, df["s"].corr(df["r"], method="spearman")))
    ic = pd.Series({d: v for d, v in ics}) if ics else None

    stats = summarize_performance(net, equity, turnover, ic, ew)
    weights_df = daily_w
    return BacktestResult(
        returns=net,
        equity=equity,
        weights=weights_df,
        turnover=turnover,
        stats=stats,
        benchmark=bench_eq,
        ic=ic,
    )


def summarize_performance(
    ret: pd.Series,
    equity: pd.Series,
    turnover: pd.Series,
    ic: pd.Series | None,
    bench_ret: pd.Series,
) -> dict:
    ret = ret.dropna()
    if ret.empty:
        return {}
    ann = 252
    mu = ret.mean() * ann
    vol = ret.std() * np.sqrt(ann)
    sharpe = mu / vol if vol > 0 else np.nan
    downside = ret.clip(upper=0).std() * np.sqrt(ann)
    sortino = mu / downside if downside > 0 else np.nan
    peak = equity.cummax()
    dd = equity / peak - 1.0
    max_dd = dd.min()
    calmar = mu / abs(max_dd) if max_dd < 0 else np.nan
    total = equity.iloc[-1] / equity.iloc[0] - 1.0
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else np.nan
    avg_to = turnover[turnover > 0].mean() if (turnover > 0).any() else 0.0
    hit = (ret > 0).mean()

    active = ret - bench_ret.reindex(ret.index).fillna(0.0)
    te = active.std() * np.sqrt(ann)
    ir = (active.mean() * ann) / te if te > 0 else np.nan

    out = {
        "start": str(equity.index[0].date()),
        "end": str(equity.index[-1].date()),
        "years": round(years, 2),
        "total_return": round(float(total), 4),
        "cagr": round(float(cagr), 4),
        "ann_vol": round(float(vol), 4),
        "sharpe": round(float(sharpe), 3),
        "sortino": round(float(sortino), 3),
        "max_drawdown": round(float(max_dd), 4),
        "calmar": round(float(calmar), 3) if calmar == calmar else None,
        "hit_rate": round(float(hit), 3),
        "avg_turnover_one_way": round(float(avg_to), 3),
        "information_ratio": round(float(ir), 3) if ir == ir else None,
        "final_equity": round(float(equity.iloc[-1]), 2),
    }
    if ic is not None and len(ic):
        out["ic_mean"] = round(float(ic.mean()), 4)
        out["ic_ir"] = round(float(ic.mean() / ic.std()), 3) if ic.std() > 0 else None
        out["ic_n"] = int(ic.count())
    return out
