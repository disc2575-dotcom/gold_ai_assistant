"""
run_day3.py
اختبار نظام الإشارات + إدارة المخاطر.
"""

import sqlite3
import pandas as pd

from core.config import DB_PATH
from smc.engine import analyze
from signals.generator import generate_signal
from risk.manager import manage_risk


def main():
    print("=" * 70)
    print("🚀 اليوم الثالث: نظام الإشارات + إدارة المخاطر")
    print("=" * 70)

    # 1. تحميل البيانات
    print("\n📊 تحميل بيانات XAUUSD H1...")
    conn = sqlite3.connect(str(DB_PATH))
    df = pd.read_sql(
        'SELECT * FROM "XAUUSD_H1" ORDER BY timestamp ASC',
        conn,
        parse_dates=["timestamp"],
    )
    conn.close()
    print(f"✅ عدد الشموع: {len(df)}")

    # 2. تحليل SMC
    print("\n🔍 تحليل SMC...")
    df = analyze(df)
    print("✅ تم التحليل")

    # 3. توليد الإشارات
    print("\n📡 توليد الإشارات...")
    signals = []
    for i in range(25, len(df)):
        signal = generate_signal(df, i)
        if signal["action"]:
            signals.append({
                "idx": i,
                "timestamp": df.iloc[i]["timestamp"],
                **signal,
            })

    print(f"✅ عدد الإشارات: {len(signals)}")

    # 4. إدارة المخاطر + عرض النتائج
    print("\n💰 إدارة المخاطر + عرض النتائج:")
    print("=" * 70)

    if not signals:
        print("⚠️  لا توجد إشارات.")
        return

    # عرض آخر 10 إشارات
    for sig in signals[-10:]:
        idx = sig["idx"]
        risk = manage_risk(df, idx, sig["action"])

        print(f"\n{'🟢' if sig['action'] == 'BUY' else '🔴'} {sig['timestamp']}")
        print(f"   الإشارة: {sig['action']} | الثقة: {sig['confidence']}%")
        print(f"   الدخول:  {risk['entry']}")
        print(f"   SL:      {risk['stop_loss']}")
        print(f"   TP:      {risk['target']}")
        print(f"   الحجم:   {risk['position_size']} لوت")
        print(f"   المخاطرة: {risk['risk_amount']}$ ({risk['risk_pct']}%)")
        print(f"   الأسباب: {', '.join(sig['reasons'])}")

    # 5. إحصائيات
    print("\n" + "=" * 70)
    print("📊 إحصائيات الإشارات:")
    print("=" * 70)

    buy_count = sum(1 for s in signals if s["action"] == "BUY")
    sell_count = sum(1 for s in signals if s["action"] == "SELL")
    avg_confidence = sum(s["confidence"] for s in signals) / len(signals)

    print(f"  🟢 BUY:  {buy_count}")
    print(f"  🔴 SELL: {sell_count}")
    print(f"  📈 متوسط الثقة: {avg_confidence:.1f}%")
    print(f"  📊 المجموع: {len(signals)}")

    print("\n" + "=" * 70)
    print("🎉 انتهى اليوم الثالث!")
    print("=" * 70)


if __name__ == "__main__":
    main()