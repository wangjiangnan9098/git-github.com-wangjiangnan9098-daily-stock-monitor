from __future__ import annotations

import math

import pandas as pd

from .models import CrossSignal, QuoteSnapshot, StockAnalysisResult

RSI_WINDOW = 14


def compute_indicators(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles.copy()
    frame = frame.sort_values("date").reset_index(drop=True)

    frame["ma5"] = frame["close"].rolling(window=5).mean()
    frame["ma10"] = frame["close"].rolling(window=10).mean()
    frame["ema7"] = frame["close"].ewm(span=7, adjust=False).mean()
    frame["ema14"] = frame["close"].ewm(span=14, adjust=False).mean()
    frame["ema21"] = frame["close"].ewm(span=21, adjust=False).mean()
    frame["volume_avg_5d"] = frame["volume"].rolling(window=5).mean()
    frame["rsi14"] = _compute_rsi(frame["close"], window=RSI_WINDOW)
    return frame


def _compute_rsi(series: pd.Series, *, window: int) -> pd.Series:
    delta = series.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)

    avg_gains = gains.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_losses = losses.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()

    relative_strength = avg_gains / avg_losses.replace(0.0, pd.NA)
    rsi = 100 - (100 / (1 + relative_strength))

    no_losses_mask = avg_losses.eq(0) & avg_gains.gt(0)
    no_moves_mask = avg_losses.eq(0) & avg_gains.eq(0)
    rsi = rsi.mask(no_losses_mask, 100.0)
    rsi = rsi.mask(no_moves_mask, 50.0)
    return rsi.astype(float)


def classify_trend(row: pd.Series) -> str:
    if row["ema7"] > row["ema14"] > row["ema21"]:
        return "bullish"
    if row["ema7"] < row["ema14"] < row["ema21"]:
        return "bearish"
    return "sideways"


def classify_rsi_state(rsi_value: float) -> str:
    if rsi_value >= 70:
        return "overbought"
    if rsi_value <= 30:
        return "oversold"
    return "neutral"


def detect_cross_signal(previous_row: pd.Series, latest_row: pd.Series) -> CrossSignal:
    ma_golden = bool(
        _crossed_above(previous_row["ma5"], latest_row["ma5"], previous_row["ma10"], latest_row["ma10"])
    )
    ma_death = bool(
        _crossed_below(previous_row["ma5"], latest_row["ma5"], previous_row["ma10"], latest_row["ma10"])
    )
    ema_golden = bool(
        _crossed_above(previous_row["ema7"], latest_row["ema7"], previous_row["ema14"], latest_row["ema14"])
    )
    ema_death = bool(
        _crossed_below(previous_row["ema7"], latest_row["ema7"], previous_row["ema14"], latest_row["ema14"])
    )

    if ma_golden or ema_golden:
        signal = "golden_cross"
    elif ma_death or ema_death:
        signal = "death_cross"
    else:
        signal = "none"

    return CrossSignal(
        signal=signal,
        ma5_ma10_golden=ma_golden,
        ma5_ma10_death=ma_death,
        ema7_ema14_golden=ema_golden,
        ema7_ema14_death=ema_death,
    )


def _crossed_above(prev_left: float, curr_left: float, prev_right: float, curr_right: float) -> bool:
    return (
        _is_valid_number(prev_left)
        and _is_valid_number(curr_left)
        and _is_valid_number(prev_right)
        and _is_valid_number(curr_right)
        and prev_left <= prev_right
        and curr_left > curr_right
    )


def _crossed_below(prev_left: float, curr_left: float, prev_right: float, curr_right: float) -> bool:
    return (
        _is_valid_number(prev_left)
        and _is_valid_number(curr_left)
        and _is_valid_number(prev_right)
        and _is_valid_number(curr_right)
        and prev_left >= prev_right
        and curr_left < curr_right
    )


def _is_valid_number(value: float) -> bool:
    return value is not None and not math.isnan(float(value))


def build_analysis(
    symbol: str,
    candles: pd.DataFrame,
    *,
    quote: QuoteSnapshot | None = None,
    source: str = "finnhub",
) -> StockAnalysisResult:
    if len(candles) < 21:
        raise ValueError(f"{symbol} requires at least 21 daily candles for analysis")

    frame = compute_indicators(candles)
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]

    latest_price = quote.current_price if quote and quote.current_price else float(latest["close"])
    previous_close = quote.previous_close if quote and quote.previous_close else float(previous["close"])
    price_change_pct = (
        quote.percent_change
        if quote and quote.current_price and quote.previous_close
        else _pct_change(float(previous["close"]), float(latest["close"]))
    )

    latest_volume = float(latest["volume"])
    previous_volume = float(previous["volume"])
    volume_avg_5d = float(latest["volume_avg_5d"])
    volume_vs_previous_pct = _pct_change(previous_volume, latest_volume)
    volume_vs_5d_avg_pct = _pct_change(volume_avg_5d, latest_volume)
    cross = detect_cross_signal(previous, latest)
    rsi14 = float(latest["rsi14"])

    return StockAnalysisResult(
        symbol=symbol,
        trade_date=latest["date"].strftime("%Y-%m-%d"),
        latest_price=round(latest_price, 4),
        latest_close=round(float(latest["close"]), 4),
        previous_close=round(previous_close, 4),
        price_change_pct_1d=round(price_change_pct, 4),
        latest_volume=round(latest_volume, 2),
        previous_volume=round(previous_volume, 2),
        volume_vs_previous_pct=round(volume_vs_previous_pct, 4),
        volume_avg_5d=round(volume_avg_5d, 2),
        volume_vs_5d_avg_pct=round(volume_vs_5d_avg_pct, 4),
        volume_expansion=latest_volume > volume_avg_5d,
        trend=classify_trend(latest),
        rsi14=round(rsi14, 4),
        rsi_state=classify_rsi_state(rsi14),
        cross_signal=cross.signal,
        cross_details=cross.to_dict(),
        source=source,
    )


def _pct_change(base_value: float, latest_value: float) -> float:
    if base_value == 0:
        return 0.0
    return ((latest_value - base_value) / base_value) * 100
