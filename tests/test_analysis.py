from __future__ import annotations

from pathlib import Path
import sys
from datetime import datetime

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from us_stock_analysis.analysis import (  # noqa: E402
    build_analysis,
    classify_rsi_state,
    classify_trend,
    detect_cross_signal,
)
import us_stock_analysis.provider as provider_module  # noqa: E402
from us_stock_analysis.cli import _render_markdown, build_parser  # noqa: E402
from us_stock_analysis.models import QuoteSnapshot  # noqa: E402
from us_stock_analysis.provider import (  # noqa: E402
    AlphaVantageClient,
    FallbackMarketDataProvider,
    StockDataError,
    create_market_data_provider,
    parse_stock_list,
)


def make_candles(closes: list[float], volumes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.date_range("2025-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": volumes,
        }
    )


def test_parse_stock_list_supports_comments_commas_and_dedup(tmp_path) -> None:
    stock_list = tmp_path / "stock_list.txt"
    stock_list.write_text("aapl, msft\n# skip\nnvda\nAAPL\n", encoding="utf-8")

    assert parse_stock_list(stock_list) == ["AAPL", "MSFT", "NVDA"]


def test_build_analysis_identifies_bullish_volume_expansion_and_overbought() -> None:
    closes = list(range(100, 130))
    volumes = [1_000] * 25 + [1_050, 1_000, 1_020, 1_010, 2_500]
    candles = make_candles(closes, volumes)
    quote = QuoteSnapshot(
        current_price=130.5,
        change=2.5,
        percent_change=1.95,
        previous_close=128.0,
    )

    result = build_analysis("AAPL", candles, quote=quote)

    assert result.trend == "bullish"
    assert result.volume_expansion is True
    assert result.rsi_state == "overbought"
    assert result.latest_price == 130.5
    assert result.price_change_pct_1d == 1.95


def test_build_analysis_identifies_bearish_volume_expansion_and_oversold() -> None:
    closes = [100] * 20 + [110, 112, 114, 116, 118, 100, 95, 90, 85, 80]
    volumes = [1_000] * 25 + [900, 950, 920, 910, 1_500]
    candles = make_candles(closes, volumes)

    result = build_analysis("TSLA", candles)

    assert result.trend == "bearish"
    assert result.rsi_state == "oversold"
    assert result.volume_expansion is True
    assert result.price_change_pct_1d == -5.8824
    assert result.volume_vs_previous_pct == 64.8352
    assert result.volume_vs_5d_avg_pct == 44.7876


def test_build_analysis_detects_death_cross_from_full_candle_series() -> None:
    closes = [100] * 20 + [110, 112, 114, 116, 118, 120, 122, 124, 120, 75]
    volumes = [1_000] * 25 + [900, 950, 920, 910, 1_500]
    candles = make_candles(closes, volumes)

    result = build_analysis("NFLX", candles)

    assert result.cross_signal == "death_cross"
    assert result.cross_details["ma5_ma10_death"] is True
    assert result.cross_details["ema7_ema14_death"] is True
    assert result.rsi_state == "oversold"
    assert result.volume_expansion is True
    assert result.volume_vs_previous_pct == 64.8352


def test_detect_cross_signal_handles_golden_and_death_cross() -> None:
    previous = pd.Series({"ma5": 9.8, "ma10": 10.0, "ema7": 9.7, "ema14": 10.0})
    latest = pd.Series({"ma5": 10.2, "ma10": 10.1, "ema7": 10.3, "ema14": 10.1})

    golden = detect_cross_signal(previous, latest)

    assert golden.signal == "golden_cross"
    assert golden.ma5_ma10_golden is True
    assert golden.ema7_ema14_golden is True

    previous = pd.Series({"ma5": 10.2, "ma10": 10.0, "ema7": 10.3, "ema14": 10.0})
    latest = pd.Series({"ma5": 9.7, "ma10": 9.9, "ema7": 9.8, "ema14": 10.0})

    death = detect_cross_signal(previous, latest)

    assert death.signal == "death_cross"
    assert death.ma5_ma10_death is True
    assert death.ema7_ema14_death is True


def test_trend_and_rsi_helpers_cover_bearish_and_neutral_cases() -> None:
    bearish_row = pd.Series({"ema7": 8.0, "ema14": 9.0, "ema21": 10.0})
    sideways_row = pd.Series({"ema7": 10.0, "ema14": 9.5, "ema21": 9.8})

    assert classify_trend(bearish_row) == "bearish"
    assert classify_trend(sideways_row) == "sideways"
    assert classify_rsi_state(25.0) == "oversold"
    assert classify_rsi_state(55.0) == "neutral"


def test_fallback_provider_uses_secondary_provider_when_primary_fails() -> None:
    candles = make_candles(list(range(100, 130)), [1_000] * 30)
    quote = QuoteSnapshot(current_price=130.0, change=1.0, percent_change=0.77, previous_close=129.0)

    class PrimaryProvider:
        def fetch_symbol_data(self, symbol: str, *, lookback_days: int = 90, end_date=None):
            raise StockDataError("primary failed")

    class SecondaryProvider:
        def fetch_symbol_data(self, symbol: str, *, lookback_days: int = 90, end_date=None):
            from us_stock_analysis.models import SymbolMarketData

            return SymbolMarketData(symbol=symbol, candles=candles, quote=quote, source="yfinance")

    provider = FallbackMarketDataProvider([PrimaryProvider(), SecondaryProvider()])

    result = provider.fetch_symbol_data("AAPL")

    assert result.source == "yfinance"
    assert result.quote.current_price == 130.0


def test_create_market_data_provider_prefers_yfinance_before_alphavantage(monkeypatch) -> None:
    class StubYahooFinanceClient:
        pass

    class StubAlphaVantageClient:
        def __init__(self, api_key=None):
            self.api_key = api_key

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "demo")
    monkeypatch.setattr(provider_module, "YahooFinanceClient", StubYahooFinanceClient)
    monkeypatch.setattr(provider_module, "AlphaVantageClient", StubAlphaVantageClient)

    provider = create_market_data_provider()

    assert [item.__class__.__name__ for item in provider.providers] == [
        "StubYahooFinanceClient",
        "StubAlphaVantageClient",
    ]


def test_cli_parser_only_supports_table_and_markdown_output() -> None:
    parser = build_parser()
    output_action = next(action for action in parser._actions if action.dest == "output")

    assert output_action.choices == ("table", "markdown")
    assert output_action.default == "markdown"


def test_alphavantage_client_parses_daily_and_quote_payloads() -> None:
    class StubAlphaVantageClient(AlphaVantageClient):
        def _get(self, params):
            if params["function"] == "TIME_SERIES_DAILY":
                return {
                    "Time Series (Daily)": {
                        "2025-01-03": {
                            "1. open": "103.0",
                            "2. high": "104.0",
                            "3. low": "102.0",
                            "4. close": "103.5",
                            "5. volume": "1200",
                        },
                        "2025-01-02": {
                            "1. open": "101.0",
                            "2. high": "102.0",
                            "3. low": "100.0",
                            "4. close": "101.5",
                            "5. volume": "1100",
                        },
                        "2025-01-01": {
                            "1. open": "100.0",
                            "2. high": "101.0",
                            "3. low": "99.0",
                            "4. close": "100.5",
                            "5. volume": "1000",
                        },
                    }
                }
            if params["function"] == "GLOBAL_QUOTE":
                return {
                    "Global Quote": {
                        "05. price": "104.2",
                        "08. previous close": "103.5",
                        "09. change": "0.7",
                        "10. change percent": "0.6763%",
                    }
                }
            raise AssertionError(f"Unexpected params: {params}")

    client = StubAlphaVantageClient(api_key="demo")
    candles = client.get_daily_candles("AAPL")
    quote = client.get_quote("AAPL")

    assert len(candles) == 3
    assert candles.iloc[-1]["close"] == 103.5
    assert quote.current_price == 104.2
    assert quote.previous_close == 103.5
    assert round(quote.percent_change, 4) == 0.6763


def test_render_markdown_contains_summary_and_failures() -> None:
    candles = make_candles(list(range(100, 130)), [1_000] * 25 + [1_050, 1_000, 1_020, 1_010, 2_500])
    analysis = build_analysis(
        "AAPL",
        candles,
        quote=QuoteSnapshot(current_price=130.5, change=2.5, percent_change=1.95, previous_close=128.0),
        source="yfinance",
    )

    rendered = _render_markdown(
        [analysis],
        [{"symbol": "MSFT", "error": "HTTP 403"}],
        stock_list_path="stock_list.txt",
        generated_at=datetime(2026, 3, 20, 10, 30, 0),
    )

    assert "# 美股技术分析报告" in rendered
    assert "| AAPL | 2025-01-30 | yfinance |" in rendered
    assert "- 是否放量: 是" in rendered
    assert "## 获取失败" in rendered
    assert "`MSFT`: HTTP 403" in rendered
