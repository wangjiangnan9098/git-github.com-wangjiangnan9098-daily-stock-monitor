---
name: daily-stock-monitor
description: Use daily-stock-monitor to analyze US stock watchlists, fetch daily candle and quote data with yfinance first and Alpha Vantage as fallback, compute EMA and MA trend signals, RSI state, volume expansion, and golden or death cross signals, and modify or explain the stock-analysis workflow in the daily-stock-monitor workspace. Use when the request mentions US stocks, stock_list files, external ticker inputs, daily K data, Alpha Vantage, yfinance, RSI, EMA or MA signals, or this repository's stock analysis scripts.
---

# Daily Stock Monitor

## Overview

Use the daily-stock-monitor workspace implementation to analyze US stock watchlists and report technical signals in a consistent format. Prefer the existing CLI and tests before writing one-off code.

## Run The Existing Workflow

1. Accept ticker input from either direct symbols or a stock list file.
2. Prefer external symbol input first:

```bash
python3 /Users/jiangnanwang/Project/daily-stock-monitor/scripts/analyze_us_stocks.py \
  --symbols AAPL MSFT NVDA \
  --output markdown
```

3. Support comma-separated direct symbol input too:

```bash
python3 /Users/jiangnanwang/Project/daily-stock-monitor/scripts/analyze_us_stocks.py \
  --symbols AAPL,MSFT,NVDA \
  --output markdown
```

4. If direct symbols are not provided, read from an external stock list file path:

```bash
python3 /Users/jiangnanwang/Project/daily-stock-monitor/scripts/analyze_us_stocks.py \
  --stock-list /Users/jiangnanwang/Project/daily-stock-monitor/stock_list.txt \
  --output markdown
```

5. If neither `--symbols` nor `--stock-list` is provided, fall back to `./stock_list.txt` in the current working directory.
6. Prefer `yfinance` first when fetching daily candles and latest price data, and use Alpha Vantage only when `yfinance` fails or is unavailable.
7. Run the analyzer first when the user asks for results instead of code changes:

```bash
python3 /Users/jiangnanwang/Project/daily-stock-monitor/scripts/analyze_us_stocks.py \
  --output markdown
```

8. Use `--as-of YYYY-MM-DD` for backtesting or reproducible snapshots.
9. Use `--output table` for terminal inspection and `--output markdown` for saved reports.
10. When saving a report for the user, write it under `/Users/jiangnanwang/Project/daily-stock-monitor/reports/` with a dated filename.
11. After saving a report, also surface the result in the conversation: at minimum provide the saved file path plus a concise summary, and when the user asks to see the output, quote or summarize the report contents directly instead of only saying it was saved.
12. Install dependencies from `requirements.txt` before relying on `yfinance`, and keep Alpha Vantage only as the fallback provider.

## Interpret The Signals

- Treat the trend as `bullish` only when `ema7 > ema14 > ema21`.
- Treat the trend as `bearish` only when `ema7 < ema14 < ema21`.
- Treat all other EMA layouts as `sideways`.
- Treat volume as expanded only when the latest volume is above the 5-day average volume.
- Treat RSI as `overbought` at `>= 70` and `oversold` at `<= 30`.
- Treat a signal as `golden_cross` when either `ma5` crosses above `ma10` or `ema7` crosses above `ema14`.
- Treat a signal as `death_cross` when either `ma5` crosses below `ma10` or `ema7` crosses below `ema14`.

## Modify The Workflow

- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/provider.py` for data-source priority, stock list parsing, dotenv loading, and Alpha Vantage access.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/analysis.py` for indicators and signal rules.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/src/us_stock_analysis/cli.py` for direct symbol input, stock list fallback rules, output format, or command-line arguments.
- Edit `/Users/jiangnanwang/Project/daily-stock-monitor/tests/test_analysis.py` when changing signal definitions, input precedence, or CLI behavior.

## Validate Before Reporting

- Run `pytest -q` after modifying signal logic or input behavior.
- Run `python3 -m compileall src scripts tests` after structural changes.
- If live quote or candle fetching is unavailable, rely on unit tests and explain that network or API access blocked live verification.
