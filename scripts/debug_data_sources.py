#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_stock_analysis.provider import ALPHA_VANTAGE_BASE_URL, load_dotenv  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal debug script for Alpha Vantage and yfinance.")
    parser.add_argument("--symbol", default="AAPL", help="Ticker symbol to test.")
    parser.add_argument("--dotenv", default=".env", help="Dotenv path.")
    parser.add_argument("--history-days", type=int, default=30, help="History window.")
    parser.add_argument(
        "--alpha-delay-seconds",
        type=float,
        default=1.2,
        help="Delay between Alpha Vantage requests to stay below rate limits.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_dotenv(args.dotenv)

    print_header("Debug Context")
    print(f"symbol={args.symbol}")
    print(f"dotenv={args.dotenv}")
    print(f"history_days={args.history_days}")
    print(f"alpha_delay_seconds={args.alpha_delay_seconds}")
    print(f"alpha_vantage_api_key_present={bool(get_api_key())}")
    print(f"alpha_vantage_api_key_masked={mask_secret(get_api_key())}")

    test_alpha_vantage_quote(args.symbol)
    sleep_between_alpha_vantage_calls(args.alpha_delay_seconds)
    test_alpha_vantage_candles(args.symbol, lookback_days=args.history_days)
    test_yfinance(args.symbol, lookback_days=args.history_days)
    return 0


def test_alpha_vantage_quote(symbol: str) -> None:
    print_header("Alpha Vantage Quote")
    api_key = get_api_key()
    if not api_key:
        print("error=ALPHA_VANTAGE_API_KEY is missing")
        return

    params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": api_key}
    safe_params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": mask_secret(api_key)}
    print(f"url={ALPHA_VANTAGE_BASE_URL}")
    print(f"params={json.dumps(safe_params, ensure_ascii=False)}")

    try:
        response = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=20)
        print(f"status_code={response.status_code}")
        print(f"response_text={truncate(response.text, 800)}")
        try:
            payload = response.json()
        except Exception:
            payload = None
        print(f"response_json={json.dumps(payload, ensure_ascii=False, default=str, indent=2)}")
    except Exception:
        print("exception_traceback=")
        print(traceback.format_exc())


def test_alpha_vantage_candles(symbol: str, *, lookback_days: int) -> None:
    print_header("Alpha Vantage Candles")
    api_key = get_api_key()
    if not api_key:
        print("error=ALPHA_VANTAGE_API_KEY is missing")
        return

    final_day = date.today()
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "outputsize": "compact",
        "apikey": api_key,
    }
    safe_params = dict(params)
    safe_params["apikey"] = mask_secret(api_key)

    print(f"url={ALPHA_VANTAGE_BASE_URL}")
    print(f"params={json.dumps(safe_params, ensure_ascii=False)}")

    try:
        response = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=20)
        print(f"status_code={response.status_code}")
        print(f"response_text={truncate(response.text, 1200)}")
        try:
            payload = response.json()
        except Exception:
            payload = None
        print(f"response_json={json.dumps(payload, ensure_ascii=False, default=str, indent=2)}")
        if isinstance(payload, dict) and isinstance(payload.get("Time Series (Daily)"), dict):
            dates = sorted(payload["Time Series (Daily)"].keys())
            print(f"candles_count={len(dates)}")
            print(f"last_date={dates[-1]}")
            recent_dates = [current for current in dates if current <= final_day.isoformat()][-lookback_days:]
            print(f"requested_window_count={len(recent_dates)}")
    except Exception:
        print("exception_traceback=")
        print(traceback.format_exc())


def test_yfinance(symbol: str, *, lookback_days: int) -> None:
    print_header("yfinance")
    try:
        import yfinance as yf
    except Exception:
        print("exception_traceback=")
        print(traceback.format_exc())
        return

    end_day = date.today() + timedelta(days=1)
    start_day = date.today() - timedelta(days=max(lookback_days * 3, 90))
    print(f"symbol={symbol}")
    print(f"start={start_day.isoformat()}")
    print(f"end={end_day.isoformat()}")

    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(
            start=start_day.isoformat(),
            end=end_day.isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        print(f"history_empty={history.empty}")
        print(f"history_shape={getattr(history, 'shape', None)}")
        if not history.empty:
            print("history_tail=")
            print(history.tail(5).to_string())

        fast_info = getattr(ticker, "fast_info", None)
        info_summary = {}
        if fast_info is not None:
            for key in ("lastPrice", "regularMarketPrice", "previousClose"):
                try:
                    value = fast_info[key]
                except Exception:
                    value = None
                info_summary[key] = value
        print(f"fast_info={json.dumps(info_summary, ensure_ascii=False, default=str, indent=2)}")
    except Exception:
        print("exception_traceback=")
        print(traceback.format_exc())


def get_api_key() -> str | None:
    return __import__("os").environ.get("ALPHA_VANTAGE_API_KEY")


def mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def print_header(title: str) -> None:
    print()
    print(f"=== {title} ===")


def sleep_between_alpha_vantage_calls(delay_seconds: float) -> None:
    if delay_seconds <= 0:
        return
    print(f"sleeping_seconds={delay_seconds}")
    time.sleep(delay_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
