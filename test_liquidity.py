"""
test_liquidity.py
اختبار كشف مناطق السيولة على XAUUSD H1.
"""

import sqlite3
import pandas as pd
from smc.liquidity import detect_liquidity


conn = sqlite3.connect("data/market.db")
df = pd.read_sql('SELECT * FROM "XAUUSD_H1"', conn, parse_dates=["timestamp"])
conn.close()

df = detect_liquidity(df, window=10)

buy_liq = df["buy_liquidity"].sum()
sell_liq = df["sell_liquidity"].sum()

print("=" * 50)
print("📊 نتائج كشف Liquidity على H1:")
print("=" * 50)
print(f"  Buy-side Liquidity:  {buy_liq}")
print(f"  Sell-side Liquidity: {sell_liq}")
print(f"  المجموع:             {buy_liq + sell_liq}")
print()

print("=" * 50)
print("🔵 آخر 5 Buy-side Liquidity:")
print("=" * 50)
for _, row in df[df["buy_liquidity"]].tail(5).iterrows():
    print(f"  {row['timestamp']} | المستوى: {row['liq_level']:.2f}")

print()
print("=" * 50)
print("🔴 آخر 5 Sell-side Liquidity:")
print("=" * 50)
for _, row in df[df["sell_liquidity"]].tail(5).iterrows():
    print(f"  {row['timestamp']} | المستوى: {row['liq_level']:.2f}")