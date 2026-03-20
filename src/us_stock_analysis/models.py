from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class QuoteSnapshot:
    current_price: float
    change: float
    percent_change: float
    previous_close: float


@dataclass(frozen=True)
class SymbolMarketData:
    symbol: str
    candles: Any
    quote: QuoteSnapshot
    source: str


@dataclass(frozen=True)
class CrossSignal:
    signal: str
    ma5_ma10_golden: bool
    ma5_ma10_death: bool
    ema7_ema14_golden: bool
    ema7_ema14_death: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StockAnalysisResult:
    symbol: str
    trade_date: str
    latest_price: float
    latest_close: float
    previous_close: float
    price_change_pct_1d: float
    latest_volume: float
    previous_volume: float
    volume_vs_previous_pct: float
    volume_avg_5d: float
    volume_vs_5d_avg_pct: float
    volume_expansion: bool
    trend: str
    rsi14: float
    rsi_state: str
    cross_signal: str
    cross_details: dict[str, Any]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
