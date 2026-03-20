from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from .analysis import build_analysis
from .provider import StockDataError, create_market_data_provider, load_dotenv, parse_stock_list

TREND_LABELS = {
    "bullish": "多头",
    "bearish": "空头",
    "sideways": "震荡",
}

RSI_LABELS = {
    "overbought": "超买",
    "oversold": "超卖",
    "neutral": "中性",
}

CROSS_LABELS = {
    "golden_cross": "金叉",
    "death_cross": "死叉",
    "none": "无信号",
}

BOOLEAN_LABELS = {
    True: "是",
    False: "否",
}

SOURCE_LABELS = {
    "alphavantage": "Alpha Vantage",
    "yfinance": "yfinance",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze US stocks from a stock list file.")
    parser.add_argument(
        "--stock-list",
        default="stock_list.txt",
        help="Path to stock list file. Supports one ticker per line or comma-separated values.",
    )
    parser.add_argument(
        "--history-days",
        type=int,
        default=90,
        help="Number of recent daily candles to retain for analysis.",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="Optional end date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--dotenv",
        default=".env",
        help="Optional dotenv file that provides ALPHA_VANTAGE_API_KEY.",
    )
    parser.add_argument(
        "--output",
        choices=("table", "markdown"),
        default="markdown",
        help="Output format. Use markdown for saved reports.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    load_dotenv(args.dotenv)
    symbols = parse_stock_list(args.stock_list)
    if not symbols:
        raise SystemExit("No tickers found in the stock list file.")

    provider = create_market_data_provider()
    analyses = []
    errors = []

    for symbol in symbols:
        try:
            market_data = provider.fetch_symbol_data(
                symbol,
                lookback_days=args.history_days,
                end_date=args.as_of,
            )
            analyses.append(
                build_analysis(
                    symbol,
                    market_data.candles,
                    quote=market_data.quote,
                    source=market_data.source,
                )
            )
        except (StockDataError, ValueError) as exc:
            errors.append({"symbol": symbol, "error": str(exc)})

    if args.output == "markdown":
        print(_render_markdown(analyses, errors, stock_list_path=args.stock_list))
    else:
        print(_render_table(analyses, errors))

    return 0 if analyses else 1


def _render_table(analyses, errors) -> str:
    lines = []
    if analyses:
        header = (
            f"{'代码':<8} {'日期':<12} {'最新价':>10} {'涨跌幅%':>10} "
            f"{'量比5日%':>10} {'趋势':<6} {'RSI14':>8} {'RSI状态':<6} {'交叉':<8}"
        )
        lines.append(header)
        lines.append("-" * len(header))
        for item in analyses:
            lines.append(
                f"{item.symbol:<8} {item.trade_date:<12} "
                f"{item.latest_price:>10.2f} {item.price_change_pct_1d:>10.2f} "
                f"{item.volume_vs_5d_avg_pct:>10.2f} {TREND_LABELS[item.trend]:<6} "
                f"{item.rsi14:>8.2f} {RSI_LABELS[item.rsi_state]:<6} "
                f"{CROSS_LABELS[item.cross_signal]:<8}"
            )
        if errors:
            lines.append("")

    if errors:
        lines.append("失败股票:")
        for error in errors:
            lines.append(f"- {error['symbol']}: {error['error']}")

    return "\n".join(lines)


def _render_markdown(analyses, errors, *, stock_list_path: str, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now()
    lines = [
        "# 美股技术分析报告",
        "",
        f"- 生成时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 股票列表: `{stock_list_path}`",
        f"- 成功数量: {len(analyses)}",
        f"- 失败数量: {len(errors)}",
        "",
    ]

    if analyses:
        lines.extend(
            [
                "## 汇总",
                "",
                "| 股票 | 日期 | 数据源 | 最新价 | 1日涨跌幅 | 成交量较昨% | 成交量较5日均量% | 趋势 | RSI14 | RSI状态 | 放量 | 交叉信号 |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- | --- |",
            ]
        )
        for item in analyses:
            lines.append(
                "| "
                f"{item.symbol} | {item.trade_date} | {SOURCE_LABELS.get(item.source, item.source)} | "
                f"{item.latest_price:.2f} | {item.price_change_pct_1d:.2f}% | "
                f"{item.volume_vs_previous_pct:.2f}% | {item.volume_vs_5d_avg_pct:.2f}% | "
                f"{TREND_LABELS[item.trend]} | {item.rsi14:.2f} | {RSI_LABELS[item.rsi_state]} | "
                f"{BOOLEAN_LABELS[item.volume_expansion]} | {CROSS_LABELS[item.cross_signal]} |"
            )

        for item in analyses:
            lines.extend(
                [
                    "",
                    f"## {item.symbol}",
                    "",
                    f"- 数据源: {SOURCE_LABELS.get(item.source, item.source)}",
                    f"- 交易日期: {item.trade_date}",
                    f"- 最新价格: {item.latest_price:.2f}",
                    f"- 最近收盘价: {item.latest_close:.2f}",
                    f"- 前收盘价: {item.previous_close:.2f}",
                    f"- 最近一日涨跌幅: {item.price_change_pct_1d:.2f}%",
                    f"- 最近一日成交量: {item.latest_volume:.0f}",
                    f"- 前一日成交量: {item.previous_volume:.0f}",
                    f"- 成交量较前一日变化: {item.volume_vs_previous_pct:.2f}%",
                    f"- 5日平均成交量: {item.volume_avg_5d:.0f}",
                    f"- 成交量较5日均量变化: {item.volume_vs_5d_avg_pct:.2f}%",
                    f"- 是否放量: {BOOLEAN_LABELS[item.volume_expansion]}",
                    f"- 趋势判断: {TREND_LABELS[item.trend]}",
                    f"- RSI14: {item.rsi14:.2f}",
                    f"- RSI状态: {RSI_LABELS[item.rsi_state]}",
                    f"- 交叉信号: {CROSS_LABELS[item.cross_signal]}",
                ]
            )

    if errors:
        lines.extend(["", "## 获取失败", ""])
        for error in errors:
            lines.append(f"- `{error['symbol']}`: {error['error']}")

    return "\n".join(lines)
