"""US market risk regime, L1–L6.

The proxy is the equal-weight DJIA-30 sample (Sharadar ``closeadj``), not a
live SPY feed, so GitHub Actions can rebuild the snapshot without a paid
data key. VIX is the committed CBOE daily close in ``data/market/VIX.csv``.
If that file is missing, the VIX slot falls back to a 5-day / 60-day
realized-vol spike on the same proxy. That spike is not the same series as
the 20-day vol percentile.

Weights (sum to 1). Core stress is heavier than oscillators, so RSI and
乖离度 cannot by themselves reach L5 (enter 0.62) or L6 (enter 0.76):

- drawdown from the 252-day trailing peak: 0.28
- 20-day realized vol, percentile vs its trailing year: 0.18
- VIX level blended with its trailing percentile, or the vol-spike proxy: 0.18
- trend, price versus the 200-day and 50-day averages: 0.14
- RSI(14): oversold is stress, overbought is capped caution: 0.08
- 乖离度, distance to the 20/60/200-day averages: 0.08
- breadth, share of sample names under their own 50-day average: 0.06

A worse level is adopted only after it has been signaled on two consecutive
sessions. Leaving a level also requires the score to fall 0.06 below the
threshold that was used to enter it, so one noisy day does not flip the badge.
``exposure_cap`` is stored for a later scaler. This module does not change
the backtest weights.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# Enter a level when the composite score reaches the threshold. Exit back
# through the next-lower level only after the score is EXIT_GAP below that
# threshold. See the module docstring for the two-day dwell.
ENTER = {2: 0.18, 3: 0.34, 4: 0.48, 5: 0.62, 6: 0.76}
EXIT_GAP = 0.06
DWELL_DAYS = 2

WEIGHTS = {
    "drawdown": 0.28,
    "realized_vol": 0.18,
    "vix": 0.18,
    "trend": 0.14,
    "rsi": 0.08,
    "bias": 0.08,
    "breadth": 0.06,
}

LEVELS = {
    1: {"label": "低风险", "exposure_cap": 1.00, "note": "按原规则满仓"},
    2: {"label": "正常", "exposure_cap": 0.90, "note": "正常暴露"},
    3: {"label": "偏紧", "exposure_cap": 0.75, "note": "暴露约 70%–80%"},
    4: {"label": "压力", "exposure_cap": 0.55, "note": "暴露约 50%–60%，不加激进仓"},
    5: {"label": "高风险", "exposure_cap": 0.25, "note": "暴露约 20%–30%，偏防守"},
    6: {"label": "极端", "exposure_cap": 0.00, "note": "近乎空仓"},
}

if abs(sum(WEIGHTS.values()) - 1.0) > 1e-9:
    raise RuntimeError("regime weights must sum to 1")


def attach_market_regime(payload: dict, sep_csv: Path, vix_csv: Path | None = None) -> dict:
    """Write ``market_regime`` from the sample prices and optional VIX file."""
    if not sep_csv.is_file():
        raise SystemExit(f"missing prices for market regime: {sep_csv}")
    prices = pd.read_csv(sep_csv, usecols=["ticker", "date", "closeadj"])
    prices["date"] = pd.to_datetime(prices["date"])
    wide = prices.pivot(index="date", columns="ticker", values="closeadj").sort_index()
    wide = wide.apply(pd.to_numeric, errors="coerce")
    rets = wide.pct_change(fill_method=None)
    index = (1.0 + rets.mean(axis=1, skipna=True).fillna(0.0)).cumprod()
    index.iloc[0] = 1.0

    vix = _load_vix(vix_csv) if vix_csv is not None else None
    vix_mode = "cboe" if vix is not None and not vix.dropna().empty else "realized_vol_spike_proxy"
    regime = build_regime(index, wide, vix if vix_mode == "cboe" else None, vix_mode)
    payload["market_regime"] = regime
    return payload


def build_regime(
    index: pd.Series,
    wide: pd.DataFrame,
    vix: pd.Series | None,
    vix_mode: str,
) -> dict:
    index = pd.to_numeric(index, errors="coerce").dropna().astype(float).sort_index()
    rets = index.pct_change()
    ma20 = index.rolling(20, min_periods=20).mean()
    ma50 = index.rolling(50, min_periods=50).mean()
    ma60 = index.rolling(60, min_periods=60).mean()
    ma200 = index.rolling(200, min_periods=200).mean()
    peak = index.rolling(252, min_periods=60).max()
    drawdown = index / peak - 1.0
    rv20 = rets.rolling(20, min_periods=20).std() * np.sqrt(252)
    rv5 = rets.rolling(5, min_periods=5).std() * np.sqrt(252)
    rv60 = rets.rolling(60, min_periods=60).std() * np.sqrt(252)
    rv_pct = _rolling_last_percentile(rv20, 252, 60)
    rsi = _rsi(index, 14)
    breadth = _breadth_below_ma(wide, 50)

    if vix is not None:
        vix_aligned = vix.reindex(index.index).ffill(limit=5)
        vix_pct = _rolling_last_percentile(vix_aligned, 252, 60)
    else:
        vix_aligned = None
        vix_pct = None

    rows = []
    for dt in index.index:
        if pd.isna(ma200.loc[dt]) or pd.isna(rsi.loc[dt]) or pd.isna(rv_pct.loc[dt]):
            continue
        drivers = _drivers_on(
            dt,
            drawdown=float(drawdown.loc[dt]),
            rv_pct=float(rv_pct.loc[dt]),
            rv5=float(rv5.loc[dt]) if pd.notna(rv5.loc[dt]) else None,
            rv60=float(rv60.loc[dt]) if pd.notna(rv60.loc[dt]) else None,
            price=float(index.loc[dt]),
            ma50=float(ma50.loc[dt]) if pd.notna(ma50.loc[dt]) else None,
            ma20=float(ma20.loc[dt]) if pd.notna(ma20.loc[dt]) else None,
            ma60=float(ma60.loc[dt]) if pd.notna(ma60.loc[dt]) else None,
            ma200=float(ma200.loc[dt]),
            rsi=float(rsi.loc[dt]),
            breadth=float(breadth.loc[dt]) if dt in breadth.index and pd.notna(breadth.loc[dt]) else None,
            vix=None if vix_aligned is None or pd.isna(vix_aligned.loc[dt]) else float(vix_aligned.loc[dt]),
            vix_pct=None if vix_pct is None or pd.isna(vix_pct.loc[dt]) else float(vix_pct.loc[dt]),
            vix_mode=vix_mode,
        )
        score = sum(item["contribution"] for item in drivers)
        rows.append((pd.Timestamp(dt), score, drivers))

    history, latest_drivers = _apply_hysteresis(rows)
    if not history:
        raise SystemExit("market regime produced no observations")
    latest = history[-1]
    level = int(latest["level"])
    spec = LEVELS[level]
    return {
        "as_of": latest["date"],
        "level": level,
        "label": spec["label"],
        "score": latest["score"],
        "exposure_cap": spec["exposure_cap"],
        "proxy": "DJIA-30 等权 closeadj",
        "vix_source": vix_mode,
        "dwell_days": DWELL_DAYS,
        "exit_gap": EXIT_GAP,
        "weights": WEIGHTS,
        "levels": [
            {"level": key, "label": value["label"], "exposure_cap": value["exposure_cap"], "note": value["note"]}
            for key, value in LEVELS.items()
        ],
        "drivers": latest_drivers,
        "flags": _flags(latest_drivers),
        "history": history,
        "note": (
            "全市场风险档，不是个股打分。exposure_cap 留给以后把目标仓位按档缩放；"
            "这次不改已经算好的回测净值。升档需要连续 2 个交易日，降档还要分数退出 0.06。"
        ),
    }


def _drivers_on(
    dt,
    *,
    drawdown,
    rv_pct,
    rv5,
    rv60,
    price,
    ma50,
    ma20,
    ma60,
    ma200,
    rsi,
    breadth,
    vix,
    vix_pct,
    vix_mode,
) -> list[dict]:
    del dt
    dd_risk = _interp(drawdown, [(-0.25, 1.0), (-0.18, 0.90), (-0.12, 0.70), (-0.08, 0.45), (-0.03, 0.15), (0.0, 0.0)])
    vol_risk = _clip01(rv_pct)
    if vix_mode == "cboe" and vix is not None and vix_pct is not None:
        vix_level_risk = _interp(vix, [(12, 0.0), (16, 0.15), (20, 0.35), (25, 0.55), (30, 0.75), (40, 1.0)])
        vix_risk = 0.6 * vix_level_risk + 0.4 * _clip01(vix_pct)
        vix_label = f"{vix:.1f} · 一年分位 {_clip01(vix_pct):.0%}"
        vix_name = "VIX"
    else:
        ratio = (rv5 / rv60) if rv5 and rv60 and rv60 > 0 else 1.0
        vix_risk = _interp(ratio, [(0.8, 0.0), (1.0, 0.20), (1.5, 0.60), (2.0, 1.0)])
        vix_label = f"5日/60日波动 {ratio:.2f}（无 VIX 文件）"
        vix_name = "波动尖峰"
    trend_risk, trend_label = _trend_risk(price, ma50, ma200)
    rsi_risk = _rsi_risk(rsi)
    bias_risk, bias_label, bias_value = _bias_risk(price, ma20, ma60, ma200)
    breadth_risk = 0.5 if breadth is None else _clip01(breadth)
    raw = {
        "drawdown": (dd_risk, "距高点回撤", _pct(drawdown) + "（252日高点）", drawdown),
        "realized_vol": (vol_risk, "20日实现波动", f"一年分位 {vol_risk:.0%}", rv_pct),
        "vix": (vix_risk, vix_name, vix_label, vix if vix is not None else None),
        "trend": (trend_risk, "均线趋势", trend_label, None),
        "rsi": (rsi_risk, "RSI(14)", f"{rsi:.1f}", rsi),
        "bias": (bias_risk, "乖离度", bias_label, bias_value),
        "breadth": (
            breadth_risk,
            "样本广度",
            "—" if breadth is None else f"{breadth:.0%} 的成分低于自身 50 日均线",
            breadth,
        ),
    }
    drivers = []
    for key, weight in WEIGHTS.items():
        risk, name, label, value = raw[key]
        risk = _clip01(risk)
        drivers.append(
            {
                "id": key,
                "name": name,
                "value": None if value is None else round(float(value), 4),
                "value_label": label,
                "risk": round(risk, 4),
                "weight": weight,
                "contribution": round(weight * risk, 4),
            }
        )
    return drivers


def _trend_risk(price: float, ma50: float | None, ma200: float) -> tuple[float, str]:
    gap200 = price / ma200 - 1.0
    risk200 = _interp(gap200, [(-0.12, 1.0), (-0.05, 0.70), (0.0, 0.35), (0.03, 0.10), (0.08, 0.0)])
    if ma50 is None or ma50 == 0:
        return risk200, f"相对 200 日 {_pct(gap200)}"
    gap50 = price / ma50 - 1.0
    risk50 = _interp(gap50, [(-0.08, 1.0), (-0.03, 0.60), (0.0, 0.25), (0.04, 0.0)])
    risk = 0.65 * risk200 + 0.35 * risk50
    return risk, f"200 日 {_pct(gap200)} · 50 日 {_pct(gap50)}"


def _rsi_risk(rsi: float) -> float:
    """Oversold adds stress. Overbought is mild caution and is capped at 0.35.

    The driver weight is 0.08, so even a risk of 1.0 adds only 0.08 to the
    composite. L5 starts at 0.62, so RSI cannot promote the book by itself.
    """
    if rsi <= 30:
        return _interp(rsi, [(10, 1.0), (20, 0.80), (30, 0.45)])
    if rsi >= 70:
        return _interp(rsi, [(70, 0.12), (80, 0.28), (90, 0.35)])
    return 0.0


def _bias_risk(price, ma20, ma60, ma200) -> tuple[float, str, float | None]:
    def gap(ma):
        if ma is None or ma == 0:
            return None
        return price / ma - 1.0

    b20, b60, b200 = gap(ma20), gap(ma60), gap(ma200)
    neg = 0.0
    parts = []
    if b20 is not None:
        neg += 0.45 * _clip01(-b20 / 0.06)
        parts.append(f"20日 {_pct(b20)}")
    if b60 is not None:
        neg += 0.35 * _clip01(-b60 / 0.08)
        parts.append(f"60日 {_pct(b60)}")
    if b200 is not None:
        neg += 0.20 * _clip01(-b200 / 0.10)
        parts.append(f"200日 {_pct(b200)}")
    pos = 0.0
    if b20 is not None:
        pos += 0.6 * _clip01(b20 / 0.08)
    if b60 is not None:
        pos += 0.4 * _clip01(b60 / 0.10)
    # Negative distance is the stress. Positive distance is only a light euphoria penalty.
    risk = 0.85 * _clip01(neg) + 0.15 * _clip01(pos)
    return risk, " · ".join(parts) if parts else "—", b60


def _flags(drivers: list[dict]) -> dict:
    by_id = {item["id"]: item for item in drivers}
    rsi = by_id.get("rsi", {}).get("value")
    bias = by_id.get("bias", {}).get("value")
    return {
        "rsi_oversold": bool(rsi is not None and rsi <= 30),
        "euphoria": bool(bias is not None and bias >= 0.08),
    }


def _apply_hysteresis(rows: list[tuple]) -> tuple[list[dict], list[dict]]:
    level = None
    pending = None
    streak = 0
    history = []
    latest_drivers: list[dict] = []
    for dt, score, drivers in rows:
        score = float(score)
        if level is None:
            level = _desired_level(1, score)
        else:
            want = _desired_level(level, score)
            if want == level:
                pending = None
                streak = 0
            elif want == pending:
                streak += 1
                if streak >= DWELL_DAYS:
                    level = want
                    pending = None
                    streak = 0
            else:
                pending = want
                streak = 1
        history.append(
            {
                "date": pd.Timestamp(dt).strftime("%Y-%m-%d"),
                "level": int(level),
                "score": round(score, 4),
            }
        )
        latest_drivers = drivers
    return history, latest_drivers


def _desired_level(current: int, score: float) -> int:
    level = current
    while level < 6 and score >= ENTER[level + 1]:
        level += 1
    while level > 1 and score < ENTER[level] - EXIT_GAP:
        level -= 1
    return level


def _breadth_below_ma(wide: pd.DataFrame, window: int) -> pd.Series:
    average = wide.rolling(window, min_periods=window).mean()
    valid = wide.notna() & average.notna()
    below = (wide < average) & valid
    denom = valid.sum(axis=1).replace(0, np.nan)
    return below.sum(axis=1) / denom


def _rsi(price: pd.Series, period: int = 14) -> pd.Series:
    delta = price.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _rolling_last_percentile(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    values = series.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    for i, value in enumerate(values):
        if not np.isfinite(value):
            continue
        start = max(0, i - window + 1)
        window_values = values[start : i + 1]
        window_values = window_values[np.isfinite(window_values)]
        if len(window_values) < min_periods:
            continue
        out[i] = float(np.mean(window_values <= value))
    return pd.Series(out, index=series.index)


def _load_vix(path: Path) -> pd.Series | None:
    if path is None or not path.is_file():
        return None
    frame = pd.read_csv(path, parse_dates=["date"])
    series = pd.to_numeric(frame["close"], errors="coerce")
    series.index = pd.to_datetime(frame["date"])
    return series.sort_index().dropna()


def _interp(value: float, knots: list[tuple[float, float]]) -> float:
    points = sorted(knots, key=lambda item: item[0])
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= value <= right_x:
            span = right_x - left_x
            weight = 0 if span == 0 else (value - left_x) / span
            return left_y + weight * (right_y - left_y)
    return points[-1][1]


def _clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def _pct(value: float) -> str:
    return f"{value * 100:+.1f}%"
