"""
test_fvg.py
مقارنة بين فلاتر FVG مختلفة.
"""

import sqlite3
import pandas as pd
from smc.fvg import detect_fvg


conn = sqlite3.connect("data/market.db")
df = pd.read_sql('SELECT * FROM "XAUUSD_H1"', conn, parse_dates=["timestamp"])
conn.close()

print(f"📊 عدد الشموع: {len(df)}\n")
print("=" * 60)
print(f"{'Filter %':<12} {'Bull FVG':<12} {'Bear FVG':<12} {'Total':<12}")
print("=" * 60)

for pct in [0.01, 0.05, 0.1, 0.2, 0.3, 0.5]:
    result = detect_fvg(df, min_size_pct=pct)
    bull = result["bullish_fvg"].sum()
    bear = result["bearish_fvg"].sum()
    print(f"{pct:<12} {bull:<12} {bear:<12} {bull + bear:<12}")

print("=" * 60)