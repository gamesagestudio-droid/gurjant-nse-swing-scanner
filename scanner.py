
import os
import time
from io import StringIO

import pandas as pd
import requests
import yfinance as yf

# GURJANT NSE SWING SCANNER V2

NIFTY500_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"

MAX_PRICE = 1500
MIN_AVG_VOLUME = 50000
VOLUME_MULTIPLE = 1.2
RSI_MIN = 40
RSI_MAX = 70
BATCH_SIZE = 40
TOP_N = 30

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()


def get_symbols():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.niftyindices.com/"
    }

    response = requests.get(
        NIFTY500_URL,
        headers=headers,
        timeout=30
    )
    response.raise_for_status()

    table = pd.read_csv(StringIO(response.text))

    if "Symbol" not in table.columns:
        raise ValueError("NIFTY 500 Symbol column missing")

    symbols = (
        table["Symbol"]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .drop_duplicates()
        .tolist()
    )

    if len(symbols) < 450:
        raise ValueError(
            f"Incomplete stock list: {len(symbols)} symbols"
        )

    return symbols


def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.clip(lower=0).ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    loss = (-delta.clip(upper=0)).ewm(
        alpha=1 / period,
        adjust=False
    ).mean()

    rs = gain / loss.replace(0, float("nan"))

    return (100 - 100 / (1 + rs)).fillna(100)


def get_series(data, field, ticker):
    if isinstance(data.columns, pd.MultiIndex):
        for key in [(field, ticker), (ticker, field)]:
            if key in data.columns:
                return data[key].dropna()

        return pd.Series(dtype=float)

    if field in data.columns:
        return data[field].dropna()

    return pd.Series(dtype=float)


def scan_batch(symbols):
    tickers = [symbol + ".NS" for symbol in symbols]

    data = yf.download(
        tickers=tickers,
        period="6mo",
        interval="1d",
        auto_adjust=True,
        group_by="column",
        threads=True,
        progress=False,
        timeout=25
    )

    matches = []

    for symbol, ticker in zip(symbols, tickers):
        try:
            close = get_series(
                data, "Close", ticker
            ).astype(float)

            volume = get_series(
                data, "Volume", ticker
            ).astype(float)

            if len(close) < 60 or len(volume) < 25:
                continue

            price = float(close.iloc[-1])

            avg_volume = float(
                volume.iloc[-21:-1].mean()
            )

            latest_volume = float(volume.iloc[-1])

            if avg_volume <= 0:
                continue

            volume_ratio = latest_volume / avg_volume

            ema20 = float(
                close.ewm(span=20, adjust=False)
                .mean().iloc[-1]
            )

            ema50 = float(
                close.ewm(span=50, adjust=False)
                .mean().iloc[-1]
            )

            rsi = float(
                calculate_rsi(close).iloc[-1]
            )

            if (
                price <= MAX_PRICE
                and avg_volume >= MIN_AVG_VOLUME
                and volume_ratio >= VOLUME_MULTIPLE
                and ema20 > ema50
                and RSI_MIN <= rsi <= RSI_MAX
            ):
                matches.append({
                    "symbol": symbol,
                    "price": price,
                    "rsi": rsi,
                    "volume_ratio": volume_ratio
                })

        except Exception as error:
            print(symbol, "ERROR:", error)

    return matches


def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram secrets missing.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    parts = []

    while len(message) > 3900:
        cut = message.rfind("\n", 0, 3900)

        if cut < 100:
            cut = 3900

        parts.append(message[:cut])
        message = message[cut:].lstrip()

    parts.append(message)

    for part in parts:
        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": part
            },
            timeout=25
        )

        try:
            result = response.json()
        except Exception:
            result = {"description": response.text[:250]}

        if not response.ok or not result.get("ok", False):
            raise RuntimeError(
                "Telegram error: "
                + result.get("description", "Unknown error")
            )

    return True


def main():
    print("Downloading NIFTY 500 stock list...")

    symbols = get_symbols()

    print("Total stocks:", len(symbols))

    matches = []

    for start in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[start:start + BATCH_SIZE]

        print(
            "Scanning batch:",
            start // BATCH_SIZE + 1
        )

        found = scan_batch(batch)

        matches.extend(found)

        time.sleep(1)

    matches.sort(
        key=lambda x: x["volume_ratio"],
        reverse=True
    )

    lines = [
        "GURJANT NSE SWING SCANNER V2",
        f"NIFTY 500 stocks: {len(symbols)}",
        f"Price <= Rs {MAX_PRICE}",
        f"Average Volume >= {MIN_AVG_VOLUME}",
        f"Volume >= {VOLUME_MULTIPLE}x",
        "EMA20 > EMA50",
        f"RSI {RSI_MIN}-{RSI_MAX}",
        ""
    ]

    if matches:
        lines.append(
            f"Matched stocks: {len(matches)}"
        )

        for i, stock in enumerate(
            matches[:TOP_N], 1
        ):
            lines.append(
                f"{i}. {stock['symbol']} | "
                f"Price Rs {stock['price']:.2f} | "
                f"RSI {stock['rsi']:.1f} | "
                f"Volume {stock['volume_ratio']:.2f}x"
            )

    else:
        lines.append(
            "No stocks matched today's filters."
        )

    lines.extend([
        "",
        "Watchlist only - not a buy recommendation.",
        "No automatic orders are placed."
    ])

    report = "\n".join(lines)

    print("\nFINAL SCANNER REPORT:\n")
    print(report)

    sent = send_telegram(report)

    print(
        "TELEGRAM STATUS:",
        "SENT" if sent else "NOT SENT"
    )


if __name__ == "__main__":
    main()
