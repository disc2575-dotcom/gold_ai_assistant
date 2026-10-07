"""
data_pipeline/storage.py
تخزين واسترجاع بيانات OHLCV في SQLite.
"""

import sqlite3
import pandas as pd


def store_ohlcv(df: pd.DataFrame, symbol: str, timeframe: str, db_path: str):
    """
    حفظ DataFrame في جدول SQLite.
    اسم الجدول: {symbol}_{timeframe} مثال: XAUUSD_H1
    """
    conn = sqlite3.connect(db_path)
    table_name = f"{symbol}_{timeframe}"

    df.to_sql(table_name, conn, if_exists="replace", index=False)

    # فهرس على التوقيت لتسريع الاستعلامات لاحقاً
    conn.execute(
        f'CREATE INDEX IF NOT EXISTS idx_{table_name}_ts ON "{table_name}"(timestamp)'
    )
    conn.commit()
    conn.close()
    print(f"[{timeframe}] تم حفظ {len(df)} شمعة في الجدول {table_name}")


def load_ohlcv(symbol: str, timeframe: str, db_path: str) -> pd.DataFrame:
    """
    استرجاع بيانات OHLCV من SQLite.
    """
    conn = sqlite3.connect(db_path)
    table_name = f"{symbol}_{timeframe}"

    df = pd.read_sql(
        f'SELECT * FROM "{table_name}"',
        conn,
        parse_dates=["timestamp"]
    )
    conn.close()
    return df