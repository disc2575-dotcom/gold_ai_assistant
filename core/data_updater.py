"""
core/data_updater.py
تحديث market.db ببيانات جديدة من TwelveData.
"""

import os
import time
import sqlite3
import requests
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from core.config import (
    DB_PATH, SYMBOL_TWELVEDATA, SYMBOL_DB,
    BARS_PER_TIMEFRAME, TIMEFRAMES
)

load_dotenv()

TWELVEDATA_TF_MAP = {
    "D1": "1day",
    "H4": "4h",
    "H1": "1h",
    "M30": "30min",
    "M15": "15min",
    "M5": "5min",
}


def fetch_latest(timeframe: str, bars: int = None) -> pd.DataFrame:
    """جلب أحدث البيانات من TwelveData."""
    api_key = os.getenv("TWELVEDATA_API_KEY")
    if not api_key:
        raise ValueError("❌ TWELVEDATA_API_KEY غير موجود")

    if bars is None:
        bars = BARS_PER_TIMEFRAME[timeframe]

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": SYMBOL_TWELVEDATA,
        "interval": TWELVEDATA_TF_MAP[timeframe],
        "outputsize": bars,
        "apikey": api_key,
        "timezone": "UTC",
    }

    response = requests.get(url, params=params, timeout=60)
    data = response.json()

    if "values" not in data:
        raise ValueError(f"❌ خطأ من TwelveData: {data.get('message', data)}")

    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df["volume"] = df["volume"].astype(float) if "volume" in df.columns else 0.0

    return df.sort_values("timestamp").reset_index(drop=True)[
        ["timestamp", "open", "high", "low", "close", "volume"]
    ]


def update_table(timeframe: str, new_df: pd.DataFrame):
    """دمج البيانات الجديدة مع الموجودة."""
    table_name = f"{SYMBOL_DB}_{timeframe}"
    conn = sqlite3.connect(str(DB_PATH))

    try:
        existing = pd.read_sql(
            f'SELECT * FROM "{table_name}"',
            conn,
            parse_dates=["timestamp"]
        )

        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="timestamp")
        combined = combined.sort_values("timestamp").reset_index(drop=True)

        combined.to_sql(table_name, conn, if_exists="replace", index=False)
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_{table_name}_ts ON "{table_name}"(timestamp)'
        )
        conn.commit()

        new_rows = len(combined) - len(existing)
        return new_rows, len(combined)
    finally:
        conn.close()


def update_all_timeframes():
    """تحديث جميع الأطر الزمنية."""
    print("=" * 60)
    print("🔄 تحديث market.db")
    print("=" * 60)

    for tf in TIMEFRAMES:
        try:
            print(f"\n📊 {tf}...")
            new_df = fetch_latest(tf)
            new_rows, total = update_table(tf, new_df)
            print(f"   ✅ {new_rows} صف جديد | المجموع: {total}")
            time.sleep(8)
        except Exception as e:
            print(f"   ❌ خطأ في {tf}: {e}")

    print("\n" + "=" * 60)
    print("✅ انتهى التحديث")
    print("=" * 60)


if __name__ == "__main__":
    update_all_timeframes()