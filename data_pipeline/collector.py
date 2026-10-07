"""
data_pipeline/collector.py
جلب بيانات OHLCV من TwelveData API.
"""

import os
import requests
import pandas as pd
from dotenv import load_dotenv
from core.config import SYMBOL_TWELVEDATA, BARS_PER_TIMEFRAME

load_dotenv()

TWELVEDATA_TF_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M30": "30min",
    "M15": "15min",
    "M5": "5min",
}


def fetch_ohlcv_twelvedata(symbol: str, timeframe: str, bars: int) -> pd.DataFrame:
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise ValueError("❌ لم يتم العثور على TWELVEDATA_API_KEY في ملف .env")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": TWELVEDATA_TF_MAP[timeframe],
        "outputsize": bars,
        "apikey": api_key,
        "timezone": "UTC",
    }

    print(f"   ⏳ جلب بيانات {timeframe} من TwelveData...")
    response = requests.get(url, params=params, timeout=60)
    data = response.json()

    if "values" not in data:
        error_msg = data.get("message", str(data))
        raise ValueError(f"❌ خطأ من TwelveData: {error_msg}")

    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df["volume"] = df["volume"].astype(float) if "volume" in df.columns else 0.0

    df = df.sort_values("timestamp").reset_index(drop=True)

    return df[["timestamp", "open", "high", "low", "close", "volume"]]


def fetch_ohlcv(timeframe: str) -> pd.DataFrame:
    return fetch_ohlcv_twelvedata(
        SYMBOL_TWELVEDATA,
        timeframe,
        BARS_PER_TIMEFRAME[timeframe],
    )