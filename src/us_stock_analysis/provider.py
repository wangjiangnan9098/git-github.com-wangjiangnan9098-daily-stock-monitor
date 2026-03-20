from __future__ import annotations

import contextlib
import io
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd
import requests

from .models import QuoteSnapshot, SymbolMarketData

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"


class StockDataError(RuntimeError):
    pass


def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def parse_stock_list(stock_list_path: str | Path) -> list[str]:
    path = Path(stock_list_path)
    if not path.exists():
        raise FileNotFoundError(f"Stock list file not found: {path}")

    symbols: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").replace(",", "\n").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        normalized = line.upper()
        if normalized not in symbols:
            symbols.append(normalized)
    return symbols


def _to_unix_timestamp(day: date, *, is_end: bool = False) -> int:
    current_time = time.max if is_end else time.min
    current_dt = datetime.combine(day, current_time, tzinfo=timezone.utc)
    return int(current_dt.timestamp())


def _normalize_history_frame(history: pd.DataFrame, *, symbol: str, source: str) -> pd.DataFrame:
    if history.empty:
        raise StockDataError(f"Empty daily candle data for {symbol} from {source}")

    columns = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    frame = history.rename(columns=columns).copy()
    if "date" not in frame.columns:
        frame["date"] = pd.to_datetime(frame.index)

    dates = pd.to_datetime(frame["date"])
    if getattr(dates.dt, "tz", None) is not None:
        dates = dates.dt.tz_localize(None)
    frame["date"] = dates

    required_columns = ["date", "open", "high", "low", "close", "volume"]
    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise StockDataError(
            f"Missing required columns for {symbol} from {source}: {', '.join(missing_columns)}"
        )

    frame = frame[required_columns].sort_values("date").dropna().reset_index(drop=True)
    if frame.empty:
        raise StockDataError(f"No usable daily candle data for {symbol} from {source}")
    return frame


class MarketDataClient(Protocol):
    def fetch_symbol_data(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> SymbolMarketData: ...


@dataclass
class UnavailableMarketDataClient:
    name: str
    reason: str

    def fetch_symbol_data(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> SymbolMarketData:
        raise StockDataError(self.reason)


@dataclass
class AlphaVantageClient:
    api_key: str | None = None
    session: requests.Session | None = None
    base_url: str = ALPHA_VANTAGE_BASE_URL

    def __post_init__(self) -> None:
        self.api_key = self.api_key or os.environ.get("ALPHA_VANTAGE_API_KEY")
        if not self.api_key:
            raise StockDataError(
                "ALPHA_VANTAGE_API_KEY is required. Set it in the environment or .env file."
            )
        self.session = self.session or requests.Session()

    def _get(self, params: dict[str, object]) -> dict:
        request_params = dict(params)
        request_params["apikey"] = self.api_key

        try:
            response = self.session.get(
                self.base_url,
                params=request_params,
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code is not None:
                message = f"Request to Alpha Vantage failed: HTTP {status_code}"
            else:
                message = f"Request to Alpha Vantage failed: {exc.__class__.__name__}"
            raise StockDataError(message) from exc

        if not isinstance(payload, dict):
            raise StockDataError(f"Unexpected Alpha Vantage payload: {payload!r}")

        if payload.get("Error Message"):
            raise StockDataError(str(payload["Error Message"]))
        if payload.get("Note"):
            raise StockDataError(str(payload["Note"]))
        if payload.get("Information"):
            raise StockDataError(str(payload["Information"]))
        return payload

    def get_quote(self, symbol: str) -> QuoteSnapshot:
        payload = self._get({"function": "GLOBAL_QUOTE", "symbol": symbol})
        quote_payload = payload.get("Global Quote")
        if not isinstance(quote_payload, dict) or not quote_payload:
            raise StockDataError(f"No Alpha Vantage quote returned for {symbol}: {payload}")

        current_price = _to_float(quote_payload.get("05. price"))
        change = _to_float(quote_payload.get("09. change"))
        previous_close = _to_float(quote_payload.get("08. previous close"))
        percent_change_raw = str(quote_payload.get("10. change percent", "")).replace("%", "").strip()
        percent_change = _to_float(percent_change_raw)
        return QuoteSnapshot(
            current_price=current_price,
            change=change,
            percent_change=percent_change,
            previous_close=previous_close,
        )

    def get_daily_candles(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        if lookback_days < 30:
            lookback_days = 30

        final_day = end_date or date.today()
        payload = self._get(
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": "compact",
            }
        )
        series = payload.get("Time Series (Daily)")
        if not isinstance(series, dict) or not series:
            raise StockDataError(f"No Alpha Vantage daily candles returned for {symbol}: {payload}")

        records: list[dict[str, object]] = []
        for trade_date, values in series.items():
            if trade_date > final_day.isoformat():
                continue
            records.append(
                {
                    "date": pd.to_datetime(trade_date),
                    "open": _to_float(values.get("1. open")),
                    "high": _to_float(values.get("2. high")),
                    "low": _to_float(values.get("3. low")),
                    "close": _to_float(values.get("4. close")),
                    "volume": _to_float(values.get("5. volume")),
                }
            )

        raw_frame = pd.DataFrame(records)
        frame = _normalize_history_frame(raw_frame, symbol=symbol, source="alphavantage")
        return frame.tail(lookback_days).reset_index(drop=True)

    def fetch_symbol_data(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> SymbolMarketData:
        candles = self.get_daily_candles(symbol, lookback_days=lookback_days, end_date=end_date)
        try:
            quote = self.get_quote(symbol)
        except StockDataError:
            quote = _build_quote_from_candles(candles)
        return SymbolMarketData(symbol=symbol, candles=candles, quote=quote, source="alphavantage")


@dataclass
class YahooFinanceClient:
    ticker_factory: Callable[[str], Any] | None = None

    def __post_init__(self) -> None:
        if self.ticker_factory is not None:
            return
        try:
            import yfinance as yf
        except ModuleNotFoundError as exc:
            raise StockDataError(
                "yfinance is not installed. Run `pip install -r requirements.txt` to enable fallback."
            ) from exc
        self.ticker_factory = yf.Ticker

    def fetch_symbol_data(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> SymbolMarketData:
        assert self.ticker_factory is not None

        if lookback_days < 30:
            lookback_days = 30

        final_day = end_date or date.today()
        calendar_window = max(lookback_days * 3, 90)
        start_day = final_day - timedelta(days=calendar_window)
        history_end = final_day + timedelta(days=1)

        ticker = self.ticker_factory(symbol)
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                history = ticker.history(
                    start=start_day.isoformat(),
                    end=history_end.isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                )
        except Exception as exc:  # pragma: no cover - depends on external library behavior
            raise StockDataError(f"Request to yfinance failed for {symbol}: {exc.__class__.__name__}") from exc

        frame = _normalize_history_frame(history, symbol=symbol, source="yfinance")
        frame = frame.tail(lookback_days).reset_index(drop=True)
        if len(frame) < 2:
            raise StockDataError(f"Not enough yfinance history returned for {symbol}")

        previous_close = float(frame.iloc[-2]["close"])
        fallback_close = float(frame.iloc[-1]["close"])
        market_price = self._extract_market_price(ticker, fallback_close)
        change = market_price - previous_close
        percent_change = 0.0 if previous_close == 0 else (change / previous_close) * 100

        quote = QuoteSnapshot(
            current_price=market_price,
            change=change,
            percent_change=percent_change,
            previous_close=previous_close,
        )
        return SymbolMarketData(symbol=symbol, candles=frame, quote=quote, source="yfinance")

    def _extract_market_price(self, ticker: Any, fallback_close: float) -> float:
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info is not None:
            for key in ("lastPrice", "regularMarketPrice"):
                value = self._safe_lookup(fast_info, key)
                if value not in (None, 0):
                    return float(value)

        info = getattr(ticker, "info", None)
        if info:
            for key in ("regularMarketPrice", "currentPrice"):
                value = self._safe_lookup(info, key)
                if value not in (None, 0):
                    return float(value)

        return float(fallback_close)

    @staticmethod
    def _safe_lookup(container: Any, key: str) -> Any:
        try:
            if isinstance(container, dict):
                return container.get(key)
            return container[key]
        except Exception:
            return None


@dataclass
class FallbackMarketDataProvider:
    providers: list[MarketDataClient]

    def fetch_symbol_data(
        self,
        symbol: str,
        *,
        lookback_days: int = 90,
        end_date: date | None = None,
    ) -> SymbolMarketData:
        errors: list[str] = []
        for provider in self.providers:
            provider_name = provider.__class__.__name__
            try:
                return provider.fetch_symbol_data(
                    symbol,
                    lookback_days=lookback_days,
                    end_date=end_date,
                )
            except StockDataError as exc:
                errors.append(f"{provider_name}: {exc}")

        joined = "; ".join(errors) if errors else "No provider configured"
        raise StockDataError(f"All data providers failed for {symbol}: {joined}")


def create_market_data_provider() -> FallbackMarketDataProvider:
    providers: list[MarketDataClient] = []

    try:
        providers.append(YahooFinanceClient())
    except StockDataError as exc:
        providers.append(UnavailableMarketDataClient(name="YahooFinanceClient", reason=str(exc)))

    alpha_vantage_key = os.environ.get("ALPHA_VANTAGE_API_KEY")
    if alpha_vantage_key:
        providers.append(AlphaVantageClient(api_key=alpha_vantage_key))

    if not providers:
        raise StockDataError(
            "No available data provider. Configure ALPHA_VANTAGE_API_KEY or install yfinance."
        )

    return FallbackMarketDataProvider(providers=providers)


def _to_float(value: object) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _build_quote_from_candles(candles: pd.DataFrame) -> QuoteSnapshot:
    latest_close = float(candles.iloc[-1]["close"])
    previous_close = float(candles.iloc[-2]["close"])
    change = latest_close - previous_close
    percent_change = 0.0 if previous_close == 0 else (change / previous_close) * 100
    return QuoteSnapshot(
        current_price=latest_close,
        change=change,
        percent_change=percent_change,
        previous_close=previous_close,
    )
