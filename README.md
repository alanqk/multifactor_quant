# 美股多因子量化研究系统（Multifactor）

面向研究的长线多因子框架：动量 / 低波动 / 价值 / 质量，月度再平衡，带默认风控。数据默认使用 Sharadar 免费 DJIA 30 样本（`test-api-key`）。

## 快速开始

```bash
git clone https://github.com/alanqk/multifactor_quant.git
cd multifactor_quant
python -m venv .venv && source .venv/bin/activate
pip install -e .
# data/raw/ 已含免费 DJIA-30 样本 SEP.csv / SF1.csv / TICKERS.csv，可直接回测
python scripts/run_backtest.py               # 因子 + 回测 + reports/
# 需要刷新样本时再运行：python scripts/download_sharadar_sample.py
```

报告输出：

- `reports/summary.md` — 中文摘要与 caveats
- `reports/equity_curve.csv` / `equity_curve.png`
- `reports/stats.json`
- `data/processed/*.parquet` — 因子面板

## 目录结构

```
multifactor_quant/
  config/default.yaml          # 宇宙、回看、再平衡、成本、风控
  src/mf/
    data/                      # Sharadar 下载与 PIT 对齐
    factors/                   # momentum / low_vol / value / quality / combine
    portfolio/                 # 分数 → 权重
    risk/                      # 流动性过滤、仓位约束、回撤熔断
    backtest/                  # 向量化月度引擎
  scripts/download_sharadar_sample.py
  scripts/run_backtest.py
  data/raw/                    # 已入库：SEP.csv SF1.csv TICKERS.csv
  reports/
```

## 因子定义

| 因子 | 构建 | 排序方向 |
|------|------|----------|
| 动量 | 经典 12-1：过去 252 日收益剔除最近 21 日 | 高收益更好 |
| 低波动 | 250 日波动率；剔除僵尸股（250 日零收益占比 > 50%）；行业中性 | 低波动更好 |
| 价值 | E/P、B/P、S/P、EBITDA/EV 截面分位等权；用 SF1 `date` 做 PIT asof | 便宜更好 |
| 质量 | 简化 QMJ：GP/Assets、其 5 年 CAGR（样本不足回退 3 年）、利息保障倍数 | 高更好 |
| 合成 | 四分位等权平均（可在 yaml 改权重） | — |

可选增强（未默认开启，见配置注释）：基本面动量、小盘倾斜。

## 风控默认（已实现）

1. **准入过滤**：股价 ≥ $5；20 日美元成交额 ≥ $1M；至少 252 个交易日历史。
2. **僵尸股**：在低波因子内剔除（零收益占比过高）。
3. **持仓约束**：多头取综合分前 30%；等权；单票上限 10%；行业上限 35%。
4. **成本**：单边 10 bps（佣金 + 冲击近似），按再平衡换手扣除。
5. **回撤熔断**：净值相对峰值回撤 ≤ -20% 时空仓，回到新高后恢复。
6. **波动目标**：配置项存在，DJIA 样本默认关闭（票池过窄，杠杆意义不大）。

## 数据说明

- 免费 DJIA-30 样本 CSV 已放在 `data/raw/`（`SEP.csv`、`SF1.csv`、`TICKERS.csv`），克隆后可直接回测。需要刷新时运行 `python scripts/download_sharadar_sample.py`。
- 免费密钥 `test-api-key` **不能** bulk `years=5`（401），脚本改为按 DJIA 30 逐票 REST 拉取。
- 覆盖约最近 5 年；**无退市股**（样本本身是现任 DJIA 成分），存在幸存者偏差。
- 价值/质量使用 ART（as-reported TTM）+ `date` 字段 asof，避免用 `calendardate` 造成前视。
- 质量 5 年 CAGR 在样本上历史偏短，自动回退到 ≥3 年窗口。

付费后可把 `config/default.yaml` 的 `api_key` 换成正式密钥，并扩展 `sample_tickers` / 改用 bulk 下载全市场。

## 配置入口

编辑 `config/default.yaml`：宇宙过滤、因子回看、再平衡（`M`）、成本、单票/行业上限、回撤阈值等。

## 注意

本仓库用于研究与教学回测，不是实盘下单系统。实盘需接入券商、执行、实时风控与更完整的数据（含退市与 point-in-time 公告）。


## 看板源码

- `dashboard/multifactor_dashboard.canvas.tsx` — Cursor / Grok Bot Page 源码（`grok/canvas`）
- `dashboard/dash_data.json` — 看板嵌入数据快照
- `reports/` — 最近一次样本回测摘要（`summary.md`、`stats.json`、`equity_curve.csv`）

免费 DJIA-30 样本已入库于 `data/raw/`。刷新数据用 `python scripts/download_sharadar_sample.py`，然后 `python scripts/run_backtest.py`。

仓库：[alanqk/multifactor_quant](https://github.com/alanqk/multifactor_quant)
