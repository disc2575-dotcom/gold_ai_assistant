"""
data_pipeline/cleaner.py
تنظيف وتوحيد بيانات OHLCV.
"""

import pandas as pd


def clean_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    تنظيف بيانات OHLCV:
    1. إزالة التكرار في التوقيت.
    2. إزالة القيم الناقصة.
    3. إزالة الشموع ذات القيم غير المنطقية.
    4. الترتيب الزمني الصحيح.
    """
    original_len = len(df)

    # 1. إزالة التكرار في التوقيت
    df = df.drop_duplicates(subset="timestamp")

    # 2. إزالة القيم الناقصة
    df = df.dropna(subset=["open", "high", "low", "close"])

    # 3. إزالة الشموع ذات القيم غير المنطقية
    df = df[(df["high"] >= df["low"]) & (df["close"] > 0) & (df["open"] > 0)]

    # 4. الترتيب الزمني الصحيح
    df = df.sort_values("timestamp").reset_index(drop=True)

    removed = original_len - len(df)
    if removed > 0:
        print(f"[{timeframe}] تم حذف {removed} صف غير صالح من أصل {original_len}")

    return df