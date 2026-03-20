---
name: us-stock-analysis
description: Analyze US stock watchlists, fetch daily candle and quote data with ALPHA_VANTAGE_API_KEY, fall back to yfinance when needed, compute EMA and MA trend signals, RSI state, volume expansion, and golden or death cross signals, and modify or explain the stock-analysis workflow in the daily-stock-monitor workspace. Use when the request mentions US stocks, stock_list files, daily K data, Alpha Vantage, yfinance, RSI, EMA or MA signals, or this repository's stock analysis scripts.
---

# Us Stock Analysis

## Overview

Use the workspace implementation to analyze US stock watchlists and report technical signals in a consistent format. Prefer the existing CLI and tests before writing one-off code.

## Run The Existing Workflow

1. Read tickers from `stock_list.txt` or from the file path the user provides.
2. Prefer Alpha Vantage first when `ALPHA_VANTAGE_API_KEY` is available, and let `yfinance` act as the fallback provider when Alpha Vantage fails or is unavailable.
3. Run the analyzer first when the user asks for results instead of code changes:

```bash
python3 /Users/jiangnanwang/Project/daily-stock-monitor/scripts/analyze_us_stocks.py \
  --stock-list /Users/jiangnanwang/Project/daily-stock-monitor/stock_list.txt \
  --output json
```

4. Use `--as-of YYYY-MM-DD` for backtesting or reproducible snapshots.
5. Use `--output table` for terminal inspection, `--output json` for machine-readable output, and `--output markdown` for report templates.
6. Install dependencies from `requirements.txt` before relying on `yfinance` fallback in a fresh environment.

## Interpret The Signals

- Treat the trend as `bullish` only when `ema7 > ema14 > ema21`.
- Treat the trend as `bearish` only when `ema7 < ema14 < ema21`.
- Treat all other EMA layouts as `sideways`.
- Treat volume as expanded only when the latest volume is above the 5-day average volume.
- Treat RSI as `overbought` at `>= 70` and `oversold` at `<= 30`.
- Treat a signal as `golden_cross` when either `ma5` crosses above `ma10` or `ema7` crosses above `ema14`.
- Treat a signal as `death_cross` when either `ma5` crosses below `ma10` or `ema7` crosses below `ema14`.

## Modify The Workflow

- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/provider.py` for stock list parsing, dotenv loading, and Alpha Vantage data access.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/analysis.py` for indicators and signal rules.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/cli.py` for output format or command-line arguments.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/tests/test_analysis.py` when changing signal definitions or thresholds.

## Validate Before Reporting

- Run `pytest -q` after modifying signal logic.
- Run `python3 -m compileall src scripts tests` after structural changes.
- If live quote or candle fetching is unavailable, rely on unit tests and explain that network or API access blocked live verification.
