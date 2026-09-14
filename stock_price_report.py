"""Generate a stock-price email report without using an LLM."""

from __future__ import annotations

import argparse
import html
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import matplotlib
import pandas as pd
import yfinance as yf

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

REPORT_DIR = Path("reports")
CHART_DIR = REPORT_DIR / "charts"


@dataclass
class Snapshot:
    ticker: str
    date: str
    open: float
    close: float
    high: float
    low: float
    high_52w: float
    low_52w: float
    high_1w: float
    low_1w: float
    change: float
    sma20: float
    sma50: float
    rsi14: float
    macd: float
    macd_signal: float
    macd_histogram: float
    macd_status: str
    chart: Path


def parse_tickers(raw: str) -> list[str]:
    tickers = [item.strip().upper() for item in raw.replace("\n", ",").split(",") if item.strip()]
    if not tickers:
        raise ValueError("STOCK_LIST cannot be empty, for example: AVGO,AAPL,TSLA")
    return list(dict.fromkeys(tickers))


def rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = -delta.clip(upper=0).rolling(period).mean().replace(0, float("nan"))
    return float((100 - 100 / (1 + gains / losses)).iloc[-1])


def macd_values(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Standard MACD: 12-period EMA minus 26-period EMA, with a 9-period signal."""
    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal


def macd_status(macd: pd.Series, signal: pd.Series) -> str:
    current, previous = macd.iloc[-1], macd.iloc[-2]
    signal_now, signal_previous = signal.iloc[-1], signal.iloc[-2]
    if current > signal_now and previous <= signal_previous:
        return "金叉 ↑（偏多）"
    if current < signal_now and previous >= signal_previous:
        return "死叉 ↓（偏空）"
    if current > signal_now and current > 0:
        return "多头 ↑"
    if current > signal_now:
        return "转强 ↑"
    if current < signal_now and current < 0:
        return "空头 ↓"
    return "转弱 ↓"


def get_history(ticker: str) -> pd.DataFrame:
    data = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=False)
    data = data.dropna(subset=["Open", "High", "Low", "Close"])
    if len(data) < 50:
        raise RuntimeError("fewer than 50 daily trading rows were returned")
    return data


def draw_chart(ticker: str, data: pd.DataFrame) -> Path:
    daily = data.tail(63).copy()
    daily["SMA20"] = data["Close"].rolling(20).mean().tail(63)
    daily["SMA50"] = data["Close"].rolling(50).mean().tail(63)
    macd, signal, histogram = macd_values(data.Close)
    daily["MACD"] = macd.tail(63)
    daily["Signal"] = signal.tail(63)
    daily["Histogram"] = histogram.tail(63)
    fig, (price_axis, macd_axis, volume_axis) = plt.subplots(
        3, 1, figsize=(12, 8.5), sharex=True, gridspec_kw={"height_ratios": [4, 1.25, 1]}
    )
    for timestamp, row in daily.iterrows():
        x = mdates.date2num(timestamp.to_pydatetime())
        color = "#16a34a" if row.Close >= row.Open else "#dc2626"
        price_axis.vlines(x, row.Low, row.High, color=color, linewidth=1)
        price_axis.add_patch(Rectangle((x - 0.28, min(row.Open, row.Close)), 0.56, max(abs(row.Close - row.Open), 0.01), color=color))
        volume_axis.bar(x, row.Volume, width=0.56, color=color, alpha=0.55)
    price_axis.plot(daily.index, daily.SMA20, color="#2563eb", linewidth=1.4, label="SMA 20")
    price_axis.plot(daily.index, daily.SMA50, color="#f59e0b", linewidth=1.4, label="SMA 50")
    price_axis.set_title(f"{ticker} — 3-Month Daily OHLC", loc="left", fontweight="bold")
    price_axis.set_ylabel("Price")
    price_axis.grid(alpha=0.2)
    price_axis.legend(loc="upper left")
    macd_axis.axhline(0, color="#64748b", linewidth=0.8)
    macd_axis.bar(daily.index, daily.Histogram, color=["#16a34a" if value >= 0 else "#dc2626" for value in daily.Histogram], width=0.7, alpha=0.75)
    macd_axis.plot(daily.index, daily.MACD, color="#2563eb", linewidth=1.3, label="MACD")
    macd_axis.plot(daily.index, daily.Signal, color="#f59e0b", linewidth=1.3, label="Signal (9)")
    macd_axis.set_ylabel("MACD")
    macd_axis.grid(alpha=0.15)
    macd_axis.legend(loc="upper left", ncol=2)
    volume_axis.set_ylabel("Volume")
    volume_axis.grid(alpha=0.15)
    volume_axis.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    volume_axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"{ticker.lower()}_3m.png"
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def snapshot(ticker: str) -> Snapshot:
    data = get_history(ticker)
    last = data.iloc[-1]
    week = data.tail(5)
    macd, signal, histogram = macd_values(data.Close)
    return Snapshot(
        ticker=ticker,
        date=data.index[-1].strftime("%Y-%m-%d"),
        open=float(last.Open), close=float(last.Close), high=float(last.High), low=float(last.Low),
        high_52w=float(data.High.max()), low_52w=float(data.Low.min()),
        high_1w=float(week.High.max()), low_1w=float(week.Low.min()),
        change=(float(last.Close) / float(data.Close.iloc[-2]) - 1) * 100,
        sma20=float(data.Close.rolling(20).mean().iloc[-1]),
        sma50=float(data.Close.rolling(50).mean().iloc[-1]),
        rsi14=rsi(data.Close),
        macd=float(macd.iloc[-1]), macd_signal=float(signal.iloc[-1]),
        macd_histogram=float(histogram.iloc[-1]), macd_status=macd_status(macd, signal),
        chart=draw_chart(ticker, data),
    )


def price(value: float) -> str:
    return f"{value:,.2f}"


def html_report(items: list[Snapshot], failed: list[str]) -> str:
    rows = []
    for item in items:
        color = "#15803d" if item.change >= 0 else "#b91c1c"
        macd_color = "#15803d" if "↑" in item.macd_status else "#b91c1c"
        rows.append(
            f"<tr><td><b>{html.escape(item.ticker)}</b></td><td>{item.date}</td>"
            f"<td>{price(item.open)}</td><td><b>{price(item.close)}</b></td>"
            f"<td style='color:{color}'>{item.change:+.2f}%</td>"
            f"<td>{price(item.high)} / {price(item.low)}</td>"
            f"<td>{price(item.high_52w)} / {price(item.low_52w)}</td>"
            f"<td>{price(item.high_1w)} / {price(item.low_1w)}</td>"
            f"<td>{price(item.sma20)} / {price(item.sma50)}</td><td>{item.rsi14:.1f}</td>"
            f"<td>{item.macd:.2f} / {item.macd_signal:.2f} / {item.macd_histogram:.2f}</td>"
            f"<td style='color:{macd_color}'><b>{item.macd_status}</b></td></tr>"
        )
    charts = "".join(
        f"<section><h2>{html.escape(item.ticker)} 近 3 个月日线</h2><img src='cid:{item.ticker.lower()}-chart' alt='{html.escape(item.ticker)} 日线图'></section>"
        for item in items
    )
    problems = "" if not failed else f"<p class='warning'>未能取得：{html.escape('；'.join(failed))}</p>"
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>
body {{font-family:Arial,'Microsoft JhengHei',sans-serif;color:#1f2937;margin:24px}} .muted{{color:#6b7280}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:20px 0}} th{{background:#0f172a;color:#fff;text-align:right;padding:9px 8px;white-space:nowrap}}
td{{border-bottom:1px solid #e5e7eb;text-align:right;padding:9px 8px;white-space:nowrap}} th:first-child,th:nth-child(2),td:first-child,td:nth-child(2){{text-align:left}}
tr:nth-child(even){{background:#f8fafc}} img{{width:100%;max-width:960px;border:1px solid #e5e7eb;border-radius:8px}} section{{margin-top:30px}}
.warning{{color:#b45309;background:#fffbeb;padding:10px;border-radius:6px}}
</style></head><body><h1>股票价格日报</h1><p class='muted'>生成时间：{now}（数据为最近可用交易日收盘数据）</p>{problems}
<table><thead><tr><th>代码</th><th>交易日</th><th>开盘</th><th>收盘</th><th>日涨跌</th><th>日高 / 日低</th><th>52 周高 / 低</th><th>1 周高 / 低</th><th>SMA20 / SMA50</th><th>RSI14</th><th>MACD / Signal / 柱</th><th>MACD 状态</th></tr></thead><tbody>{''.join(rows)}</tbody></table>{charts}</body></html>"""


def send_mail(subject: str, body: str, items: list[Snapshot]) -> None:
    needed = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "EMAIL_FROM", "EMAIL_TO"]
    missing = [name for name in needed if not os.getenv(name)]
    if missing:
        raise RuntimeError("missing email configuration: " + ", ".join(missing))
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, os.environ["EMAIL_FROM"], os.environ["EMAIL_TO"]
    message.set_content("请使用支持 HTML 的邮件客户端查看股票价格日报。")
    message.add_alternative(body, subtype="html")
    html_part = message.get_payload()[-1]
    for item in items:
        html_part.add_related(item.chart.read_bytes(), maintype="image", subtype="png", cid=f"<{item.ticker.lower()}-chart>")
    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stocks", default=os.getenv("STOCK_LIST", "AVGO"))
    parser.add_argument("--send-email", action="store_true")
    args = parser.parse_args()
    items, failed = [], []
    for ticker in parse_tickers(args.stocks):
        try:
            items.append(snapshot(ticker))
            print(f"Completed: {ticker}")
        except Exception as error:
            failed.append(f"{ticker} ({error})")
            print(f"Failed: {ticker} — {error}")
    if not items:
        raise RuntimeError("no stock reports could be generated: " + "; ".join(failed))
    body = html_report(items, failed)
    REPORT_DIR.mkdir(exist_ok=True)
    report = REPORT_DIR / f"stock_price_report_{datetime.now():%Y%m%d}.html"
    report.write_text(body, encoding="utf-8")
    print(f"Report generated: {report}")
    if args.send_email:
        send_mail(f"[daily_stock_price_report] 股票价格日报 - {datetime.now():%Y-%m-%d}", body, items)
        print("Email sent successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
