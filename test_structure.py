"""
test_structure.py
اختبار BOS/CHOCH على أطر زمنية مختلفة.
"""

import sqlite3
import pandas as pd
from smc.structure import detect_bos_choch


conn = sqlite3.connect("data/market.db")

timeframes = ["D1", "H4", "H1", "M30", "M15", "M5"]

print("=" * 70)
print(f"{'TF':<6} {'Bars':<8} {'Swing H':<10} {'Swing L':<10} {'BOS':<8} {'CHOCH':<8}")
print("=" * 70)

for tf in timeframes:
    df = pd.read_sql(f'SELECT * FROM "XAUUSD_{tf}"', conn, parse_dates=["timestamp"])
    result = detect_bos_choch(df, window=10)

    print(f"{tf:<6} {len(df):<8} {result['swing_high'].sum():<10} "
          f"{result['swing_low'].sum():<10} {result['bos'].sum():<8} "
          f"{result['choch'].sum():<8}")

conn.close()
print("=" * 70)