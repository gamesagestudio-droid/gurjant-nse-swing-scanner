import os
import requests
import yfinance as yf
import pandas as pd

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Starter watchlist - later expand to full NSE universe
SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "TATAMOTORS", "ITC", "BEL", "NTPC",
    "ONGC", "POWERGRID", "IRFC", "RVNL", "NHPC",
    "TATASTEEL", "SAIL", "BHEL", "PNB", "CANBK"
]

MAX_PRICE = 1500
MIN_AVG_VOLUME = 100000
VOLUME_MULTIPLE = 1.5

def scan_stock(symbol):
    ticker = symbol + ".NS"

    try:
        df = yf.download(
            ticker,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df.empty or len(df) < 50:
            return None

        close = df["Close"].squeeze()
        volume = df["Volume"].squeeze()

        price = float(close.iloc[-1])
        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1])

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = -delta.clip(upper=0).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi = float((100 - (100 / (1 + rs))).iloc[-1])

        avg_volume = float(volume.iloc[-21:-1].mean())
        today_volume = float(volume.iloc[-1])

        if avg_volume <= 0:
            return None

        volume_ratio = today_volume / avg_volume

        if (
            price <= MAX_PRICE
            and ema20 > ema50
            and 45 <= rsi <= 68
            and avg_volume >= MIN_AVG_VOLUME
            and volume_ratio >= VOLUME_MULTIPLE
        ):
            return {
                "symbol": symbol,
                "price": round(price, 2),
                "rsi": round(rsi, 1),
                "volume_ratio": round(volume_ratio, 2)
            }

    except Exception as e:
        print(symbol, "ERROR:", e)

    return None

def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram secrets missing.")
        print(message)
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={"chat_id": CHAT_ID, "text": message},
        timeout=20
    )

    response.raise_for_status()

def main():
    results = []

    for symbol in SYMBOLS:
        print("Scanning:", symbol)
        result = scan_stock(symbol)

        if result:
            results.append(result)

    results.sort(key=lambda x: x["volume_ratio"], reverse=True)

    message = "GURJANT NSE SWING SCANNER\n\n"

    if results:
        for i, stock in enumerate(results[:20], 1):
            message += (
                f"{i}. {stock['symbol']}\n"
                f"Price: ₹{stock['price']}\n"
                f"RSI: {stock['rsi']}\n"
                f"Volume: {stock['volume_ratio']}x\n\n"
            )
    else:
        message += "No stocks matched today's filters."

    message += "\nWatchlist only - not a buy recommendation."
    send_telegram(message)

    print(message)

if __name__ == "__main__":
    main()
