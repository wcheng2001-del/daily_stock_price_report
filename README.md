# daily_stock_price_report

一个不使用 LLM 的 GitHub Actions 股票价格日报工具。它会取得最近可用交易日的行情，并生成适合邮件阅读的表格与每只股票近 3 个月的日线图。

报告包括：

- 开盘、收盘、当日高点、当日低点与当日涨跌幅
- 52 周高点／低点、最近 1 周高点／低点
- SMA 20、SMA 50、RSI 14，以及标准 MACD（12、26、9）
- MACD 的多头／空头、金叉／死叉等动能状态提示
- 最近约 3 个月的日线 OHLC 图、成交量、均线与 MACD 柱状图

## 设定股票

在 GitHub 仓库的 **Settings → Secrets and variables → Actions → Variables** 新增：

```text
STOCK_LIST=AVGO,AAPL,TSLA
```

新增的 `STOCK_A` 工作流使用独立清单，因此请另建：

```text
STOCK_A_LIST=NVDA,MSFT
```

中国 A 股可直接写六位代码，程序会自动转换为 Yahoo Finance 格式：

```text
STOCK_A_LIST=600000,600036,000001,300750
```

其中 `6xxxxx` 会转为 `.SS`（上交所），`0xxxxx`／`3xxxxx` 会转为 `.SZ`（深交所），`4xxxxx`／`8xxxxx` 会转为 `.BJ`（北交所）。也可以自行填写完整代码，例如 `600000.SS`。

也可以从 **Actions → 每日股票价格报告 → Run workflow** 临时输入股票清单。

## 设定寄信

在 **Settings → Secrets and variables → Actions → Secrets** 新增下列值：

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=你的 Gmail 地址
SMTP_PASSWORD=Gmail App Password
EMAIL_FROM=你的 Gmail 地址
EMAIL_TO=收件人地址（多个地址请以逗号分隔）
```

邮件主题为：`[daily_stock_price_report] 股票价格日报 - YYYY-MM-DD`。
`STOCK_A` 的主题会额外标示为 `[STOCK_A]`。

## 排程

默认会在**北京时间周一至周五早上 7:00**运行：

```yaml
- cron: '0 23 * * 0,1,2,3,4'
```

GitHub Actions 的 cron 以 UTC 为准。若要改时间，请编辑 `.github/workflows/daily-price-report.yml`。

## 本机执行

```bash
pip install -r requirements.txt
set STOCK_LIST=AVGO,AAPL
python stock_price_report.py
```

加上 `--send-email` 会使用上述 SMTP 环境变量寄信。
