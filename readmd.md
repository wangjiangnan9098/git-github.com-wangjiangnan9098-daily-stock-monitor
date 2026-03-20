# 美股日线分析工具说明文档

## 1. 项目简介

这是一个用于美股自选股技术分析的 Python 工具。它会从 `stock_list.txt` 读取股票代码，抓取日线数据和最新价格，计算趋势、RSI、成交量变化以及金叉/死叉信号，并生成 Markdown 报告。

当前数据源策略如下：

- 优先使用 `yfinance`
- 当 `yfinance` 不可用时，自动降级到 `Alpha Vantage`

当前报告输出策略如下：

- 默认输出 `markdown`
- 报告保存到 `reports/`
- 保存报告时，也会把分析结果直接输出到终端/对话，而不只是落盘

## 2. 目录结构

```text
daily-stock-monitor/
├── .env
├── requirements.txt
├── stock_list.txt
├── readmd.md
├── scripts/
│   ├── analyze_us_stocks.py
│   └── debug_data_sources.py
├── src/us_stock_analysis/
│   ├── analysis.py
│   ├── cli.py
│   ├── models.py
│   └── provider.py
└── tests/
    └── test_analysis.py
```

## 3. 环境准备

建议使用 `conda` 虚拟环境 `daily_stock_analysis`。

```bash
conda activate daily_stock_analysis
pip install -r requirements.txt
```

`.env` 中至少需要配置：

```env
ALPHA_VANTAGE_API_KEY=your_api_key
```

说明：

- `yfinance` 为首选数据源，不依赖 `ALPHA_VANTAGE_API_KEY`
- `Alpha Vantage` 只在 `yfinance` 失败时使用
- `Alpha Vantage` 有频率限制，调试脚本中已经支持延迟控制

## 4. 股票列表配置

在 `stock_list.txt` 中填写股票代码，每行一个，也支持逗号分隔，例如：

```text
AAPL
MSFT
NVDA
AMZN
META
```

## 5. 分析能力

当前脚本会输出以下指标和判断：

- 最新价格
- 最近一日涨跌幅
- 最近一日成交量
- 成交量相对前一日变化
- 成交量相对 5 日均量变化
- 多头趋势：`ema7 > ema14 > ema21`
- 空头趋势：`ema7 < ema14 < ema21`
- 震荡：不满足多头或空头
- 放量：最新成交量大于 5 日平均成交量
- RSI14 状态
- 超买：`RSI >= 70`
- 超卖：`RSI <= 30`
- 金叉：`ma5` 上穿 `ma10` 或 `ema7` 上穿 `ema14`
- 死叉：`ma5` 下穿 `ma10` 或 `ema7` 下穿 `ema14`

## 6. 运行分析脚本

直接运行：

```bash
conda run -n daily_stock_analysis python scripts/analyze_us_stocks.py
```

指定股票列表：

```bash
conda run -n daily_stock_analysis python scripts/analyze_us_stocks.py \
  --stock-list stock_list.txt
```

指定日期做快照分析：

```bash
conda run -n daily_stock_analysis python scripts/analyze_us_stocks.py \
  --stock-list stock_list.txt \
  --as-of 2026-03-20
```

输出格式：

```bash
conda run -n daily_stock_analysis python scripts/analyze_us_stocks.py \
  --stock-list stock_list.txt \
  --output markdown
```

说明：

- 当前 `--output` 支持 `markdown` 和 `table`
- 默认输出为 `markdown`
- 已不再使用 `json` 作为报告输出格式

## 7. 保存报告

推荐将报告保存到 `reports/` 目录：

```bash
mkdir -p reports
conda run -n daily_stock_analysis python scripts/analyze_us_stocks.py \
  --stock-list stock_list.txt \
  --output markdown > reports/us_stock_analysis_2026-03-21.md
```

执行时的预期行为：

- 报告内容会在终端可见
- 如果做了重定向，报告会保存到 `reports/` 文件中
- 后续在 agent/skill 工作流里，保存报告后也应同步输出结果摘要

## 8. 调试数据源

如果需要单独检查 `yfinance` 和 `Alpha Vantage` 是否可用，可以运行：

```bash
conda run -n daily_stock_analysis python scripts/debug_data_sources.py \
  --symbol AAPL \
  --history-days 30 \
  --alpha-delay-seconds 1.2
```

说明：

- `--alpha-delay-seconds` 用于控制 Alpha Vantage 请求间隔
- 该参数用于避免超过 Alpha Vantage 的频率限制

## 9. 运行测试

运行单元测试：

```bash
pytest -q
```

检查源码是否能正常编译：

```bash
python -m compileall src scripts tests
```

## 10. 常见问题

### 1. 为什么 sandbox 里请求失败？

如果在 sandbox 中看到以下错误：

- `NameResolutionError`
- `DNSError`
- `Failed to resolve host`

通常不是代码问题，而是 sandbox 的网络或 DNS 解析受限。

### 2. 为什么不同数据源的日期可能不一致？

这是正常现象。不同数据源的刷新时间不同，例如：

- `yfinance` 可能已经拿到 `2026-03-20`
- `Alpha Vantage` 可能还停留在 `2026-03-19`

### 3. 为什么 Markdown 和终端看到的价格会有轻微差异？

在线行情是实时变化的。如果两次请求不是同一时刻发出，价格和成交量可能会有小幅波动。

## 11. 关键文件

- `scripts/analyze_us_stocks.py`
  - 分析脚本入口
- `scripts/debug_data_sources.py`
  - 数据源联通性调试脚本
- `src/us_stock_analysis/provider.py`
  - 数据源获取与回退逻辑
- `src/us_stock_analysis/analysis.py`
  - 技术指标与信号计算
- `src/us_stock_analysis/cli.py`
  - 命令行参数与报告输出
- `tests/test_analysis.py`
  - 单元测试
