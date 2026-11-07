# Multifactor Backtest Summary

## Headline metrics

| Metric | Value |
|---|---|
| Period | 2021-11-08 → 2026-11-06 (4.99y) |
| Total return | 0.5589 |
| CAGR | 0.093 |
| Ann. volatility | 0.1242 |
| Sharpe | 0.78 |
| Sortino | 1.244 |
| Max drawdown | -0.1948 |
| Calmar | 0.497 |
| Hit rate | 0.433 |
| Avg one-way turnover | 0.224 |
| Information ratio vs EW | -0.944 |
| IC mean (monthly) | 0.0002 |
| IC IR | 0.001 |
| Final equity (start 1e6) | 1558866.66 |

## Artifacts

- Equity curve CSV: `reports/equity_curve.csv`
- Equity curve PNG: `reports/equity_curve.png`
- Stats JSON: `reports/stats.json`
- Factor panels: `data/processed/*.parquet`

## Caveats

- Universe is Sharadar free DJIA-30 sample (~30 mega-caps). Cross-sectional dispersion is limited; factor premia estimates are illustrative only.
- Quality 5y CAGR of GP/Assets falls back to 3y when history is short (free sample ≈ 5 years of fundamentals).
- Sector available from TICKERS; low-vol industry neutralization enabled. Sample has no delisted names (survivorship within DJIA constituents).
- Risk defaults: min price $5, 20d ADV filter, max name 10%, max sector 35%, 10 bps one-way costs, -20% drawdown circuit breaker. Vol targeting off (concentrated mega-cap book).
