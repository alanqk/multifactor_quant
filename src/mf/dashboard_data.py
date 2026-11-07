"""Build and write the static dashboard snapshot.

The Pages site reads ``web/data/dash_data.json``. That file is a copy of
``dashboard/dash_data.json``. ``reports/equity_curve.csv`` and
``reports/stats.json`` do not contain holdings or factor ranks, so the full
snapshot is assembled here from the in-memory backtest (weights, factor
panels, and reference tickers) and then copied for GitHub Pages.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

REQUIRED = (
    "meta",
    "stats",
    "equity",
    "months",
    "holdings",
    "factor_ranks",
    "tickers",
    "calendar",
    "risk",
    "drawdown",
)

FACTOR_KEYS = ("momentum", "low_vol", "value", "quality")
RANK_KEYS = ("combined",) + FACTOR_KEYS

DASHBOARD_PATH = Path("dashboard") / "dash_data.json"
WEB_PATH = Path("web") / "data" / "dash_data.json"


def validate_payload(payload: dict) -> None:
    if not isinstance(payload, dict):
        raise SystemExit("dashboard payload is not a JSON object")
    missing = [key for key in REQUIRED if key not in payload]
    if missing:
        raise SystemExit("dashboard payload missing keys: " + ", ".join(missing))
    if not payload["equity"]:
        raise SystemExit("dashboard payload has an empty equity series")


def dump_payload(payload: dict) -> str:
    validate_payload(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_snapshots(payload: dict, root: Path) -> list[Path]:
    text = dump_payload(payload)
    written: list[Path] = []
    for rel in (DASHBOARD_PATH, WEB_PATH):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def pretty_name(raw: str) -> str:
    text = " ".join(str(raw).split())
    if not text or text != text.upper():
        return text
    return text.title()


def enrich_tickers(payload: dict, tickers_csv: Path) -> dict:
    """Fill company name, exchange, and full sector from TICKERS.csv.

    Existing snapshots stored sector strings (sometimes truncated) and no
    company name. The chart panel reads ``tickers[symbol].name`` / ``.exch``
    when those fields are present, and still accepts a plain sector string.
    """
    if not tickers_csv.is_file():
        return payload
    ref: dict[str, dict[str, str]] = {}
    with tickers_csv.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("ticker") or "").strip()
            if symbol:
                ref[symbol] = row

    tickers = payload.setdefault("tickers", {})
    symbols = set(tickers) | set(ref)
    for symbol in symbols:
        info = tickers.get(symbol)
        if isinstance(info, str):
            info = {"sec": info}
        elif not isinstance(info, dict):
            info = {}
        src = ref.get(symbol, {})
        name = (src.get("name") or "").strip()
        exch = (src.get("exchange") or "").strip()
        sec = (src.get("sector") or "").strip() or (info.get("sec") or "")
        if name:
            info["name"] = pretty_name(name)
        if exch:
            info["exch"] = exch.upper()
        if sec:
            info["sec"] = sec
        tickers[symbol] = info
    return payload


def _trade_stats(values: list[float]) -> dict:
    """Win rate, profit factor, and payoff from a list of period returns."""
    clean = [float(value) for value in values if value is not None]
    wins = [value for value in clean if value > 0]
    losses = [value for value in clean if value < 0]
    win_rate = round(len(wins) / len(clean), 4) if clean else None
    gross_loss = abs(sum(losses))
    profit_factor = round(sum(wins) / gross_loss, 3) if gross_loss > 0 else None
    payoff = None
    if wins and losses:
        payoff = round((sum(wins) / len(wins)) / (abs(sum(losses)) / len(losses)), 3)
    return {
        "n": len(clean),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "payoff_ratio": payoff,
    }


def portfolio_risk(
    equity: pd.Series,
    returns: pd.Series | None,
    turnover: pd.Series | None,
    monthly_returns: list[float],
    stats: dict | None = None,
    max_name_weight: float | None = None,
    drawdown_halt: float | None = None,
) -> tuple[dict, list[dict]]:
    """Risk block and month-end drawdown from the backtest equity curve.

    Drawdown uses the daily running peak, then keeps the last session of each
    month so the chart lines up with the monthly equity series. Headline
    ratios already stored on ``stats`` are reused so the page does not show
    two different roundings of the same number.
    """
    stats = stats or {}
    eq = pd.to_numeric(equity, errors="coerce").dropna().astype(float).sort_index()
    if eq.empty:
        raise ValueError("equity series is empty")
    peak = eq.cummax()
    drawdown = eq / peak - 1.0
    max_dt = drawdown.idxmin()
    max_dd = float(drawdown.loc[max_dt])
    current = float(drawdown.iloc[-1])
    final_peak = float(peak.iloc[-1])
    at_peak = eq[eq >= final_peak - 1e-8]
    peak_dt = at_peak.index[-1]

    rets = pd.to_numeric(returns, errors="coerce").dropna().astype(float) if returns is not None else None
    if rets is None or rets.empty:
        rets = eq.pct_change().dropna()
    ann = 252.0
    mu = float(rets.mean() * ann) if len(rets) else float("nan")
    vol = float(rets.std() * (ann ** 0.5)) if len(rets) else float("nan")
    downside = float(rets.clip(upper=0).std() * (ann ** 0.5)) if len(rets) else float("nan")
    sharpe = mu / vol if vol == vol and vol > 0 else float("nan")
    sortino = mu / downside if downside == downside and downside > 0 else float("nan")
    calmar = mu / abs(max_dd) if max_dd < 0 else float("nan")
    daily_win = float((rets > 0).mean()) if len(rets) else float("nan")

    months = _trade_stats(monthly_returns)
    avg_to = None
    if turnover is not None:
        turned = pd.to_numeric(turnover, errors="coerce").dropna()
        if len(turned):
            positive = turned[turned > 0]
            avg_to = float(positive.mean()) if len(positive) else 0.0

    def prefer(key: str, computed: float, digits: int):
        if stats.get(key) is not None:
            return stats[key]
        return _num(computed, digits)

    halt_hit = None
    if drawdown_halt is not None and drawdown_halt == drawdown_halt:
        halt_hit = bool(max_dd <= float(drawdown_halt) + 1e-12)

    risk = {
        "max_drawdown": prefer("max_drawdown", max_dd, 4),
        "max_drawdown_date": _date_str(pd.Timestamp(max_dt)),
        "current_drawdown": _num(current, 4),
        "peak_date": _date_str(pd.Timestamp(peak_dt)),
        "ann_vol": prefer("ann_vol", vol, 4),
        "downside_vol": _num(downside, 4),
        "sharpe": prefer("sharpe", sharpe, 3),
        "sortino": prefer("sortino", sortino, 3),
        "calmar": prefer("calmar", calmar, 3),
        "daily_win_rate": prefer("hit_rate", daily_win, 3),
        "monthly_win_rate": months["win_rate"],
        "profit_factor": months["profit_factor"],
        "payoff_ratio": months["payoff_ratio"],
        "avg_turnover_one_way": prefer("avg_turnover_one_way", avg_to if avg_to is not None else float("nan"), 3),
        "max_name_weight": None if max_name_weight is None else float(max_name_weight),
        "drawdown_halt": None if drawdown_halt is None else float(drawdown_halt),
        "drawdown_halt_hit": halt_hit,
        "monthly_n": months["n"],
        "rf": 0,
    }
    sampled = drawdown.groupby(drawdown.index.to_period("M")).tail(1)
    series = []
    for dt, value in sampled.items():
        if isinstance(value, pd.Series):
            value = value.iloc[-1]
        series.append(
            {
                "label": pd.Timestamp(dt).strftime("%Y-%m"),
                "drawdown": _num(float(value), 4),
            }
        )
    return risk, series


def ensure_risk(
    payload: dict,
    equity_csv: Path,
    *,
    max_name_weight: float | None = None,
    drawdown_halt: float | None = None,
) -> dict:
    """Fill ``risk`` and ``drawdown`` from the equity curve when missing."""
    if payload.get("risk") and payload.get("drawdown"):
        return payload
    if not equity_csv.is_file():
        return payload
    frame = pd.read_csv(equity_csv, parse_dates=["date"]).set_index("date").sort_index()
    monthly = [row.get("month_return") for row in payload.get("months") or []]
    if monthly:
        monthly = monthly[:-1]
    risk, series = portfolio_risk(
        frame["strategy"],
        frame["strategy_ret"] if "strategy_ret" in frame.columns else None,
        None,
        monthly,
        payload.get("stats"),
        max_name_weight if max_name_weight is not None else (payload.get("risk") or {}).get("max_name_weight"),
        drawdown_halt if drawdown_halt is not None else (payload.get("risk") or {}).get("drawdown_halt"),
    )
    payload["risk"] = risk
    payload["drawdown"] = series
    return payload


def build_dashboard_payload(
    *,
    result,
    factors: dict[str, pd.DataFrame],
    score: pd.DataFrame,
    prices: pd.DataFrame,
    tickers: pd.DataFrame | None,
    sector: pd.Series | None,
    universe: str,
    rebalance: str,
    long_pct: float,
    weighting: str,
    max_name_weight: float | None = None,
    drawdown_halt: float | None = None,
) -> dict:
    """Full Pages snapshot: equity, stats, holdings, factor ranks, tickers."""
    names, exchanges, sectors = _reference_maps(tickers, sector)
    rebalance_days = _invested_month_ends(result.weights)
    panels = {"combined": score, **{key: factors[key] for key in FACTOR_KEYS if key in factors}}

    equity_rows = _equity_curve(result)
    month_rows = []
    holdings: dict[str, list] = {}
    factor_ranks = {key: {} for key in RANK_KEYS}
    calendar = []

    level_s = result.equity
    level_b = result.benchmark
    for i, dt in enumerate(rebalance_days):
        nxt = rebalance_days[i + 1] if i + 1 < len(rebalance_days) else None
        cur_s = float(_at(level_s, dt))
        cur_b = float(_at(level_b, dt))
        nxt_s = float(_at(level_s, nxt)) if nxt is not None else None
        nxt_b = float(_at(level_b, nxt)) if nxt is not None else None
        month_return = _forward_return(cur_s, nxt_s)
        bench_return = _forward_return(cur_b, nxt_b)
        active = None
        if month_return is not None and bench_return is not None:
            active = round(month_return - bench_return, 4)

        held = _weights_on(result.weights, dt)
        date = _date_str(dt)
        hold_rows = _holding_rows(dt, held, panels, prices, sectors)
        holdings[date] = hold_rows
        for key in RANK_KEYS:
            factor_ranks[key][date] = _rank_rows(dt, panels.get(key), held, sectors)

        ic_val = _num(_at(result.ic, dt), 4) if result.ic is not None else None
        turnover = _num(_at(result.turnover, dt), 4)
        month_rows.append(
            {
                "date": date,
                "month": dt.strftime("%Y-%m"),
                "n_hold": len(hold_rows),
                "turnover": 0.0 if turnover is None else turnover,
                "month_return": month_return,
                "bench_return": bench_return,
                "active": active,
                "equity": _num(cur_s, 2),
                "ic": ic_val,
            }
        )
        calendar.append(
            {
                "date": date,
                "value": None if month_return is None else round(month_return * 100, 2),
            }
        )

    stats = _plain(result.stats or {})
    end = stats.get("end") or (rebalance_days[-1].strftime("%Y-%m-%d") if rebalance_days else None)
    start = stats.get("start")
    meta = {
        "universe": universe,
        "rebalance": _rebalance_label(rebalance),
        "long_pct": float(long_pct),
        "weighting": weighting,
        "start": start,
        "end": end,
        "as_of": end,
        "note": (
            "由 scripts/run_backtest.py 根据 data/raw 样本生成。"
            "网页「执行回测」会在 GitHub Actions 中重跑并更新这份快照；浏览器不会执行 Python。"
        ),
    }
    payload = {
        "meta": meta,
        "stats": stats,
        "equity": equity_rows,
        "months": month_rows,
        "holdings": holdings,
        "factor_ranks": factor_ranks,
        "tickers": _ticker_objects(prices, names, exchanges, sectors),
        "calendar": calendar,
    }
    monthly_returns = [row["month_return"] for row in month_rows[:-1]]
    risk, drawdown = portfolio_risk(
        result.equity,
        result.returns,
        result.turnover,
        monthly_returns,
        stats,
        max_name_weight,
        drawdown_halt,
    )
    payload["risk"] = risk
    payload["drawdown"] = drawdown
    return _plain(payload)


def _rebalance_label(value: str) -> str:
    mapping = {"M": "month-end", "month-end": "month-end"}
    return mapping.get(str(value), str(value))


def _reference_maps(tickers: pd.DataFrame | None, sector: pd.Series | None):
    names: dict[str, str] = {}
    exchanges: dict[str, str] = {}
    sectors: dict[str, str] = {}
    if tickers is not None and not tickers.empty and "ticker" in tickers.columns:
        frame = tickers.drop_duplicates("ticker")
        for _, row in frame.iterrows():
            symbol = str(row["ticker"]).strip()
            if not symbol or symbol.lower() == "nan":
                continue
            raw_name = row["name"] if "name" in frame.columns else None
            raw_exch = row["exchange"] if "exchange" in frame.columns else None
            raw_sec = row["sector"] if "sector" in frame.columns else None
            if isinstance(raw_name, str) and raw_name.strip():
                names[symbol] = pretty_name(raw_name)
            if isinstance(raw_exch, str) and raw_exch.strip():
                exchanges[symbol] = raw_exch.strip().upper()
            if isinstance(raw_sec, str) and raw_sec.strip():
                sectors[symbol] = raw_sec.strip()
    if sector is not None:
        for symbol, value in sector.items():
            key = str(symbol)
            if key not in sectors and isinstance(value, str) and value.strip():
                sectors[key] = value.strip()
    return names, exchanges, sectors


def _ticker_objects(prices, names, exchanges, sectors) -> dict:
    symbols = set(names) | set(exchanges) | set(sectors)
    if prices is not None:
        symbols.update(str(col) for col in prices.columns)
    out = {}
    for symbol in sorted(symbols):
        if not symbol or symbol.lower() == "nan":
            continue
        info = {
            "name": names.get(symbol) or symbol,
            "sec": sectors.get(symbol),
            "exch": exchanges.get(symbol),
            "px": _last_price(prices, symbol),
        }
        out[symbol] = {key: value for key, value in info.items() if value is not None}
    return out


def _invested_month_ends(weights: pd.DataFrame) -> list[pd.Timestamp]:
    index = weights.index
    if not isinstance(index, pd.DatetimeIndex):
        index = pd.DatetimeIndex(index)
    if index.empty:
        return []
    ends = pd.Series(index, index=index).groupby(index.to_period("M")).max()
    dates = []
    for value in ends.tolist():
        dt = pd.Timestamp(value)
        held = _weights_on(weights, dt)
        if held:
            dates.append(dt)
    return dates


def _equity_curve(result) -> list[dict]:
    equity = result.equity.dropna()
    if equity.empty:
        return []
    bench = result.benchmark.reindex(equity.index)
    base_s = float(equity.iloc[0]) or 1.0
    base_b = float(bench.iloc[0]) if pd.notna(bench.iloc[0]) else 1.0
    if not base_b:
        base_b = 1.0
    month_last = equity.groupby(equity.index.to_period("M")).tail(1)
    rows = []
    for dt, value in month_last.items():
        bval = bench.loc[dt]
        if isinstance(bval, pd.Series):
            bval = bval.iloc[-1]
        rows.append(
            {
                "label": pd.Timestamp(dt).strftime("%Y-%m"),
                "strategy": _num(float(value) / base_s, 4),
                "benchmark": _num(float(bval) / base_b, 4) if pd.notna(bval) else None,
            }
        )
    return rows


def _holding_rows(dt, held, panels, prices, sectors) -> list[dict]:
    combined = _row_at(panels.get("combined"), dt)
    rows = []
    for symbol, weight in held.items():
        rows.append(
            {
                "t": symbol,
                "w": _num(weight, 4),
                "c": _score(combined, symbol),
                "m": _score(_row_at(panels.get("momentum"), dt), symbol),
                "l": _score(_row_at(panels.get("low_vol"), dt), symbol),
                "v": _score(_row_at(panels.get("value"), dt), symbol),
                "q": _score(_row_at(panels.get("quality"), dt), symbol),
                "p": _price_on(prices, symbol, dt),
                "sec": sectors.get(symbol),
            }
        )
    rows.sort(key=lambda row: (-(row["c"] if row["c"] is not None else -1.0), row["t"]))
    return rows


def _rank_rows(dt, panel, held, sectors) -> list[dict]:
    series = _row_at(panel, dt)
    if series is None:
        return []
    series = series.dropna()
    if series.empty:
        return []
    ranks = series.rank(ascending=False, method="min")
    rows = []
    for symbol, score in series.sort_values(ascending=False).items():
        key = str(symbol)
        rows.append(
            {
                "t": key,
                "s": _num(score, 4),
                "r": int(ranks.loc[symbol]),
                "h": 1 if key in held else 0,
                "sec": sectors.get(key),
            }
        )
    rows.sort(key=lambda row: (row["r"], row["t"]))
    return rows


def _weights_on(weights: pd.DataFrame, dt: pd.Timestamp) -> dict[str, float]:
    try:
        row = weights.loc[dt]
    except KeyError:
        return {}
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    row = pd.to_numeric(row, errors="coerce").fillna(0.0)
    return {str(symbol): float(value) for symbol, value in row.items() if float(value) > 1e-8}


def _row_at(frame: pd.DataFrame | None, dt: pd.Timestamp):
    if frame is None or dt not in frame.index:
        return None
    row = frame.loc[dt]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[-1]
    return pd.to_numeric(row, errors="coerce")


def _score(series, symbol: str):
    if series is None or symbol not in series.index:
        return None
    return _num(series.loc[symbol], 4)


def _price_on(prices: pd.DataFrame | None, symbol: str, dt: pd.Timestamp):
    if prices is None or symbol not in prices.columns:
        return None
    series = prices[symbol]
    if dt in series.index and pd.notna(series.loc[dt]):
        value = series.loc[dt]
        if isinstance(value, pd.Series):
            value = value.dropna()
            if value.empty:
                return None
            value = value.iloc[-1]
        return _num(value, 2)
    prior = series.loc[:dt].dropna()
    if prior.empty:
        return None
    return _num(prior.iloc[-1], 2)


def _last_price(prices: pd.DataFrame | None, symbol: str):
    if prices is None or symbol not in prices.columns:
        return None
    series = prices[symbol].dropna()
    if series.empty:
        return None
    return _num(series.iloc[-1], 2)


def _forward_return(current: float, nxt: float | None):
    if nxt is None:
        return 0.0
    if current == 0:
        return None
    return round(nxt / current - 1.0, 4)


def _at(series, dt):
    if series is None or dt is None:
        return None
    try:
        value = series.loc[dt]
    except KeyError:
        return None
    if isinstance(value, pd.Series):
        value = value.dropna()
        if value.empty:
            return None
        value = value.iloc[-1]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _date_str(dt: pd.Timestamp) -> str:
    return pd.Timestamp(dt).strftime("%Y-%m-%d")


def _num(value, digits: int):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return round(number, digits)


def _plain(value):
    """Convert pandas / numpy scalars so json.dumps can write the payload."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return value
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            return _plain(value.item())
        except (ValueError, AttributeError):
            pass
    return value
