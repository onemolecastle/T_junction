import os
import time
import io
import csv
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime
import threading
from flask import Flask

# ==================== CONFIGURATION ====================
SLACK_BOT_TOKEN = "xoxb-YOUR-NEW-BOT-TOKEN-HERE"  # Starts with xoxb-
SLACK_CHANNEL_ID = "C0123456789"                  # The ID of your slack channel

# Mapping forex pairs to Yahoo Finance tickers
FOREX_PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDJPY": "USDJPY=X"
}

PIP_THRESHOLD = 5.0  # Maximum pip distance for convergence
# =======================================================

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running fine!", 200

def upload_log_to_slack(pair, price, ema, pivot):
    """Generates an in-memory CSV file and uploads it directly to Slack."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Create a CSV structure inside system memory (RAM) instead of saving to disk
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    
    # Add structure headers and row metadata
    writer.writerow(["Timestamp", "Pair", "Current Price", "50 EMA", "Daily Pivot", "Threshold (Pips)"])
    writer.writerow([timestamp, pair, f"{price:.5f}", f"{ema:.5f}", f"{pivot:.5f}", PIP_THRESHOLD])
    
    # Reset buffer position for reading
    csv_data = csv_buffer.getvalue()
    csv_buffer.close()

    # 2. Call Slack files.uploadV2 API endpoint using standard multi-part form parameters
    url = "https://slack.com"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    
    files = {
        "file": (f"{pair}_intersection_log.csv", csv_data, "text/csv")
    }
    data = {
        "channels": SLACK_CHANNEL_ID,
        "initial_comment": (
            f"🚨 *Match-Trader Forex Signal* 🚨\n"
            f"*Pair:* `{pair}` | *Timeframe:* `1 Hour`\n"
            f"----------------------------------------\n"
            f"🔹 *Current Price:* `{price:.5f}`\n"
            f"🔹 *50 EMA:* `{ema:.5f}`\n"
            f"🔹 *Daily Pivot:* `{pivot:.5f}`\n"
            f"----------------------------------------\n"
            f"🎯 *Intersection Match:* Elements are within {PIP_THRESHOLD} pips on your WFunded setup!\n"
            f"📁 _Detailed analytical metrics attached below._"
        )
    }

    try:
        response = requests.post(url, headers=headers, data=data, files=files)
        result = response.json()
        if result.get("ok"):
            print(f"✅ Alert and data log file successfully uploaded to Slack for {pair}")
        else:
            print(f"❌ Slack API Upload Error: {result.get('error')}")
    except Exception as e:
        print(f"❌ Connection error while transferring data logs to Slack: {e}")

def get_h1_data_and_ema(ticker_symbol):
    """Fetches H1 data using yfinance and appends 50 EMA."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(interval="1h", period="5d")
        if df.empty or len(df) < 50:
            return None, None
        
        df['ema50'] = ta.ema(df['Close'], length=50)
        latest_price = df['Close'].iloc[-1]
        latest_ema = df['ema50'].iloc[-1]
        return latest_price, latest_ema
    except Exception as e:
        print(f"❌ Error fetching H1 data for {ticker_symbol}: {e}")
        return None, None

def calculate_daily_pivot(ticker_symbol):
    """Fetches D1 data to isolate the previous closed day's metrics."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df_daily = ticker.history(interval="1d", period="2d")
        if len(df_daily) < 2:
            return None
        
        prev_day = df_daily.iloc[0]
        high = prev_day['High']
        low = prev_day['low'] if 'low' in prev_day else prev_day['Low']
        close = prev_day['Close']
        
        pivot_point = (high + low + close) / 3
        return pivot_point
    except Exception as e:
        print(f"❌ Error calculating Daily Pivot for {ticker_symbol}: {e}")
        return None

def monitor_markets():
    """Loops over currency cross pairs checking mathematical distance rules."""
    print(f"🔄 Scanning Match-Trader feeds... [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    
    for pair_name, ticker_symbol in FOREX_PAIRS.items():
        current_price, current_ema = get_h1_data_and_ema(ticker_symbol)
        daily_pivot = calculate_daily_pivot(ticker_symbol)
        
        if current_price is None or current_ema is None or daily_pivot is None:
            continue
        
        pip_unit = 0.01 if "JPY" in pair_name else 0.0001
        threshold_distance = PIP_THRESHOLD * pip_unit
        
        diff_price_ema = abs(current_price - current_ema)
        diff_price_pivot = abs(current_price - daily_pivot)
        diff_ema_pivot = abs(current_ema - daily_pivot)
        
        if (diff_price_ema <= threshold_distance and 
            diff_price_pivot <= threshold_distance and 
            diff_ema_pivot <= threshold_distance):
            
            print(f"🔥 Intersection Match Found on {pair_name}! Uploading payload...")
            # Automatically pushes message text and the logging attachment file as a unified payload
            upload_log_to_slack(pair_name, current_price, current_ema, daily_pivot)

def market_monitor_loop():
    """The background tracking engine running inside a persistent processing thread."""
    last_checked_hour = -1
    while True:
        current_time = datetime.now()
        if current_time.hour != last_checked_hour:
            monitor_markets()
            last_checked_hour = current_time.hour
        time.sleep(30)

def main():
    # 1. Fire up background analytics
    monitor_thread = threading.Thread(target=market_monitor_loop, daemon=True)
    monitor_thread.start()
    
    # 2. Fire up web endpoint mapping for Render/Railway cloud health engines
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
