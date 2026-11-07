#!/usr/bin/env python3
"""Build factors, run backtest, write reports."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mf.backtest.engine import run_backtest  # noqa: E402
from mf.data.loader import load_sharadar  # noqa: E402
from mf.factors.combine import combine_factors  # noqa: E402
from mf.factors.low_vol import low_vol_factor  # noqa: E402
from mf.factors.momentum import momentum_12_1  # noqa: E402
from mf.factors.quality import quality_factor  # noqa: E402
from mf.factors.value import value_factor  # noqa: E402
from mf.risk.filters import liquidity_price_mask  # noqa: E402


def main() -> None:
    cfg = yaml.safe_load((ROOT / "config" / "default.yaml").read_text())
    raw = ROOT / cfg["data"]["raw_dir"]
    reports = ROOT / cfg["backtest"]["reports_dir"]
    reports.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    md = load_sharadar(raw)
    print(f"Prices: {md.close.shape[0]} days x {md.close.shape[1]} names")
    print(f"Fundamentals rows: {len(md.fundamentals)}; sector available: {md.sector is not None}")

    fcfg = cfg["factors"]
    print("Building momentum...")
    mom = momentum_12_1(
        md.close,
        lookback=fcfg["momentum"]["lookback_days"],
        skip=fcfg["momentum"]["skip_days"],
    )
    print("Building low vol...")
    lvol = low_vol_factor(
        md.returns,
        lookback=fcfg["low_vol"]["lookback_days"],
        zombie_zero_frac=cfg["universe"]["zombie_zero_ret_frac"],
        sector=md.sector,
        industry_neutral=fcfg["low_vol"]["industry_neutral"] and md.sector is not None,
    )
    print("Building value (PIT)...")
    val = value_factor(md.close, md.fundamentals, dimension="ART")
    print("Building quality...")
    qual = quality_factor(
        md.close,
        md.fundamentals,
        dimension="ART",
        target_cagr_years=fcfg["quality"]["target_cagr_years"],
        min_years=fcfg["quality"]["min_years_for_cagr"],
    )

    factors = {"momentum": mom, "low_vol": lvol, "value": val, "quality": qual}
    score = combine_factors(factors, fcfg["combine"]["weights"])

    # persist factor panels (month-end sample) for inspection
    processed = ROOT / cfg["data"]["processed_dir"]
    processed.mkdir(parents=True, exist_ok=True)
    for name, panel in {**factors, "combined": score}.items():
        panel.to_parquet(processed / f"{name}.parquet")

    tradable = liquidity_price_mask(
        md.close,
        md.volume,
        min_price=cfg["universe"]["min_price"],
        min_adv_usd=cfg["universe"]["min_adv_usd"],
        min_history_days=cfg["universe"]["min_history_days"],
    )

    print("Running backtest...")
    pcfg = cfg["portfolio"]
    rcfg = cfg["risk"]
    result = run_backtest(
        score,
        md.returns,
        tradable,
        sector=md.sector,
        long_pct=pcfg["long_pct"],
        weighting=pcfg["weighting"],
        max_name_weight=pcfg["max_name_weight"],
        max_sector_weight=pcfg["max_sector_weight"],
        min_names=pcfg["min_names"],
        cost_bps_one_way=rcfg["cost_bps_one_way"],
        vol_target=rcfg.get("vol_target"),
        drawdown_halt=rcfg.get("drawdown_halt"),
        initial_capital=cfg["backtest"]["initial_capital"],
    )

    # outputs
    eq = pd.DataFrame(
        {
            "strategy": result.equity,
            "benchmark_ew": result.benchmark,
            "strategy_ret": result.returns,
        }
    )
    eq_path = reports / "equity_curve.csv"
    eq.to_csv(eq_path)

    stats_path = reports / "stats.json"
    stats_path.write_text(json.dumps(result.stats, indent=2))

    # plot
    fig, ax = plt.subplots(figsize=(10, 5))
    (result.equity / result.equity.iloc[0]).plot(ax=ax, label="Multifactor")
    (result.benchmark / result.benchmark.iloc[0]).plot(ax=ax, label="EW Universe", alpha=0.8)
    ax.set_title("Multifactor vs Equal-Weight DJIA Sample")
    ax.set_ylabel("Growth of $1")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(reports / "equity_curve.png", dpi=120)
    plt.close(fig)

    # summary markdown
    s = result.stats
    caveats = []
    if md.close.shape[1] <= 30:
        caveats.append(
            "Universe is Sharadar free DJIA-30 sample (~30 mega-caps). Cross-sectional "
            "dispersion is limited; factor premia estimates are illustrative only."
        )
    if md.fundamentals.empty:
        caveats.append("No fundamentals file — value/quality factors empty.")
    else:
        # check quality growth coverage
        caveats.append(
            "Quality 5y CAGR of GP/Assets falls back to 3y when history is short "
            "(free sample ≈ 5 years of fundamentals)."
        )
    if md.sector is None:
        caveats.append("No sector metadata — low-vol industry neutralization skipped.")
    else:
        caveats.append(
            "Sector available from TICKERS; low-vol industry neutralization enabled. "
            "Sample has no delisted names (survivorship within DJIA constituents)."
        )
    caveats.append(
        "Risk defaults: min price $5, 20d ADV filter, max name 10%, max sector 35%, "
        "10 bps one-way costs, -20% drawdown circuit breaker. Vol targeting off "
        "(concentrated mega-cap book)."
    )

    lines = [
        "# Multifactor Backtest Summary",
        "",
        "## Headline metrics",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Period | {s.get('start')} → {s.get('end')} ({s.get('years')}y) |",
        f"| Total return | {s.get('total_return')} |",
        f"| CAGR | {s.get('cagr')} |",
        f"| Ann. volatility | {s.get('ann_vol')} |",
        f"| Sharpe | {s.get('sharpe')} |",
        f"| Sortino | {s.get('sortino')} |",
        f"| Max drawdown | {s.get('max_drawdown')} |",
        f"| Calmar | {s.get('calmar')} |",
        f"| Hit rate | {s.get('hit_rate')} |",
        f"| Avg one-way turnover | {s.get('avg_turnover_one_way')} |",
        f"| Information ratio vs EW | {s.get('information_ratio')} |",
        f"| IC mean (monthly) | {s.get('ic_mean')} |",
        f"| IC IR | {s.get('ic_ir')} |",
        f"| Final equity (start 1e6) | {s.get('final_equity')} |",
        "",
        "## Artifacts",
        "",
        f"- Equity curve CSV: `{eq_path.relative_to(ROOT)}`",
        f"- Equity curve PNG: `reports/equity_curve.png`",
        f"- Stats JSON: `reports/stats.json`",
        f"- Factor panels: `data/processed/*.parquet`",
        "",
        "## Caveats",
        "",
    ]
    for c in caveats:
        lines.append(f"- {c}")
    lines.append("")
    (reports / "summary.md").write_text("\n".join(lines))

    print(json.dumps(result.stats, indent=2))
    print(f"Wrote {reports / 'summary.md'}")


if __name__ == "__main__":
    main()
