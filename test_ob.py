"""
test_ob.py
اختبار كشف Order Blocks على XAUUSD H1.
"""

import sqlite3
import pandas as pd
from smc.structure import detect_bos_choch
from smc.order_blocks import detect_order_blocks


conn = sqlite3.connect("data/market.db")
df = pd.read_sql('SELECT * FROM "XAUUSD_H1"', conn, parse_dates=["timestamp"])
conn.close()

# 1. كشف BOS/CHOCH أولاً
df = detect_bos_choch(df, window=10)

# 2. كشف Order Blocks
df = detect_order_blocks(df, window=5)

# 3. الإحصائيات
bull_ob = df["bullish_ob"].sum()
bear_ob = df["bearish_ob"].sum()

print("=" * 50)
print("📊 نتائج كشف Order Blocks على H1:")
print("=" * 50)
print(f"  Bullish OB: {bull_ob}")
print(f"  Bearish OB: {bear_ob}")
print(f"  المجموع:    {bull_ob + bear_ob}")
print()

# 4. عرض آخر 5 Bullish OB
print("=" * 50)
print("🟢 آخر 5 Bullish OB:")
print("=" * 50)
bull_obs = df[df["bullish_ob"]].tail(5)
for _, row in bull_obs.iterrows():
    print(f"  {row['timestamp']} | High: {row['ob_high']:.2f} | Low: {row['ob_low']:.2f}")

print()

# 5. عرض آخر 5 Bearish OB
print("=" * 50)
print("🔴 آخر 5 Bearish OB:")
print("=" * 50)
bear_obs = df[df["bearish_ob"]].tail(5)
for _, row in bear_obs.iterrows():
    print(f"  {row['timestamp']} | High: {row['ob_high']:.2f} | Low: {row['ob_low']:.2f}")