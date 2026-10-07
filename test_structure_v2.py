"""
test_structure_v2.py

اختبار Market Structure V2 على XAUUSD H1.
"""

import sqlite3
import pandas as pd

from structure_v2 import find_swing_points, detect_bos_choch


# ============================================================
# 1) الاتصال بقاعدة البيانات
# ============================================================

conn = sqlite3.connect("data/market.db")

df = pd.read_sql(
    'SELECT * FROM "XAUUSD_H1"',
    conn,
    parse_dates=["timestamp"],
)

conn.close()


# ============================================================
# 2) تشغيل Market Structure V2
# ============================================================

df = detect_bos_choch(
    df,
    swing_left=5,
    swing_right=5,
)


# ============================================================
# 3) عرض النتائج العامة
# ============================================================

print("=" * 60)
print("📊 Market Structure V2 - XAUUSD H1")
print("=" * 60)

print(f"عدد الشموع : {len(df)}")
print(f"Swing High : {int(df['swing_high'].sum())}")
print(f"Swing Low  : {int(df['swing_low'].sum())}")
print(f"BOS        : {int(df['bos'].sum())}")
print(f"CHOCH      : {int(df['choch'].sum())}")


# ============================================================
# 4) عرض آخر أحداث BOS / CHOCH
# ============================================================

print()
print("=" * 60)
print("📌 آخر 10 أحداث Structure")
print("=" * 60)

events = df[df["bos"] | df["choch"]].tail(10)

if events.empty:
    print("لا توجد أحداث BOS أو CHOCH.")
else:
    for _, row in events.iterrows():

        if row["choch"]:
            event = "CHOCH"
        else:
            event = "BOS"

        print(
            f"{row['timestamp']} | "
            f"{event:5} | "
            f"الاتجاه: {row['trend']:7} | "
            f"المستوى: {row['bos_choch_level']:.2f}"
        )


# ============================================================
# 5) عرض آخر Swing Points
# ============================================================

print()
print("=" * 60)
print("📍 آخر 10 Swing Points")
print("=" * 60)

swings = df[
    df["swing_high"] | df["swing_low"]
].tail(10)

if swings.empty:
    print("لا توجد Swing Points.")
else:

    for _, row in swings.iterrows():

        if row["swing_high"]:
            point = f"Swing High {row['high']:.2f}"

        elif row["swing_low"]:
            point = f"Swing Low  {row['low']:.2f}"

        else:
            continue

        print(
            f"{row['timestamp']} | {point}"
        )


# ============================================================
# 6) عرض آخر اتجاه حالي
# ============================================================

print()
print("=" * 60)
print("📈 الاتجاه الحالي")
print("=" * 60)

if len(df) > 0:
    print(f"الاتجاه: {df.iloc[-1]['trend']}")


# ============================================================
# 7) عرض آخر سعر
# ============================================================

print()
print("=" * 60)
print("💰 آخر سعر")
print("=" * 60)

if len(df) > 0:
    print(f"Close: {df.iloc[-1]['close']:.2f}")


# ============================================================
# نهاية الاختبار
# ============================================================

print()
print("=" * 60)
print("✅ انتهى اختبار Market Structure V2")
print("=" * 60)