import os
import time
import csv
import requests
import pandas as pd
import pandas_ta as ta
import yfinance as yf
from datetime import datetime

# ==================== CONFIGURATION ====================
SLACK_WEBHOOK_URL = "YOUR_SLACK_WEBHOOK_URL_HERE"
LOG_FILE_NAME = "signals_log.csv"

# Mapping forex pairs to Yahoo Finance tickers
FOREX_PAIRS = {
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDJPY": "USDJPY=X"
}

PIP_THRESHOLD = 5.0  # Maximum pip distance for convergence
# =======================================================

def init_csv_logger():
    """Initializes the CSV file with headers if it doesn't already exist."""
    if not os.path.exists(LOG_FILE_NAME):
        try:
            with open(LOG_FILE_NAME, mode='w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                writer.writerow(["Timestamp", "Pair", "Current Price", "50 EMA", "Daily Pivot", "Threshold (Pips)"])
            print(f"📁 Initialised new logging storage: {LOG_FILE_NAME}")
        except Exception as e:
            print(f"❌ Failed to initialize log file: {e}")

def log_intersection_to_csv(pair, price, ema, pivot):
    """Appends a new intersection instance row to the CSV log file."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with open(LOG_FILE_NAME, mode='a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow([timestamp, pair, f"{price:.5f}", f"{ema:.5f}", f"{pivot:.5f}", PIP_THRESHOLD])
        print(f"💾 Instance successfully logged to local file for {pair}.")
    except Exception as e:
        print(f"❌ Failed writing row data to CSV file: {e}")

def send_slack_alert(pair, price, ema, pivot):
    """Sends a clean, formatted alert notification to Slack."""
    message = (
        f"🚨 *Match-Trader Forex Signal* 🚨\n"
        f"*Pair:* `{pair}` | *Timeframe:* `1 Hour`\n"
        f"----------------------------------------\n"
        f"🔹 *Current Price:* `{price:.5f}`\n"
        f"🔹 *50 EMA:* `{ema:.5f}`\n"
        f"🔹 *Daily Pivot:* `{pivot:.5f}`\n"
        f"----------------------------------------\n"
        f"🎯 *Intersection Match:* Elements are within {PIP_THRESHOLD} pips on your WFunded setup!\n"
        f"💾 _This instance has been logged locally._"
    )
    
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        if response.status_code == 200:
            print(f"✅ Alert successfully posted to Slack for {pair}")
        else:
            print(f"❌ Slack API Error {response.status_code}: {response.text}")
    except Exception as e:
        print(f"❌ Failed connection to Slack: {e}")

def get_h1_data_and_ema(ticker_symbol):
    """Fetches H1 data using yfinance and appends 50 EMA."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(interval="1h", period="5d")
        if df.empty or len(df) < 50:
            return None, None
        
        # Calculate 50 Exponential Moving Average
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
        df_daily = ticker.history(interval="1d", period="2d") # Today + Yesterday
        if len(df_daily) < 2:
            return None
        
        # Row index 0 represents the completed previous day's trading session
        prev_day = df_daily.iloc[0]
        high = prev_day['High']
        low = prev_day['Low']
        close = prev_day['Close']
        
        # Classic Daily Floor Pivot Formula
        pivot_point = (high + low + close) / 3
        return pivot_point
    except Exception as e:
        print(f"❌ Error calculating Daily Pivot for {ticker_symbol}: {e}")
        return None

def monitor_markets():
    """Loops over currency cross pairs checking mathematical distance rules."""
    print(f"🔄 Scanning Match-Trader feeds... [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")
    
    for pair_name, ticker_symbol in FOREX_PAIRS.items():
        # 1. Gather Calculations
        current_price, current_ema = get_h1_data_and_ema(ticker_symbol)
        daily_pivot = calculate_daily_pivot(ticker_symbol)
        
        if current_price is None or current_ema is None or daily_pivot is None:
            continue
        
        # 2. Adjust calculation scale for JPY cross-currency vs standard majors
        pip_unit = 0.01 if "JPY" in pair_name else 0.0001
        threshold_distance = PIP_THRESHOLD * pip_unit
        
        # 3. Intersection Proximity Math Checks
        diff_price_ema = abs(current_price - current_ema)
        diff_price_pivot = abs(current_price - daily_pivot)
        diff_ema_pivot = abs(current_ema - daily_pivot)
        
        if (diff_price_ema <= threshold_distance and 
            diff_price_pivot <= threshold_distance and 
            diff_ema_pivot <= threshold_distance):
            
            print(f"🔥 Intersection Match Found on {pair_name}!")
            
            # Executing our alert pipelines concurrently
            log_intersection_to_csv(pair_name, current_price, current_ema, daily_pivot)
            send_slack_alert(pair_name, current_price, current_ema, daily_pivot)

def main():
    print("🚀 WFunded / Match-Trader Alert Engine Active. Monitoring H1 Candles...")
    init_csv_logger()
    last_checked_hour = -1
    
    try:
        while True:
            current_time = datetime.now()
            
            # Checks market metrics precisely at the close/open transition of each hour bar
            if current_time.hour != last_checked_hour:
                monitor_markets()
                last_checked_hour = current_time.hour
                
            # Idle script loop checks clock timing every 30 seconds
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitor script deactivated manually.")

if __name__ == "__main__":
    main()
