"""
run_day2.py
تشغيل تحليل SMC الكامل على كل الأطر الزمنية وحفظ النتائج.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd

from core.config import SYMBOL_DB as SYMBOL, TIMEFRAMES, DB_PATH
from smc.engine import analyze, summarize


def load_from_db(symbol: str, timeframe: str, db_path, drop_last: bool = True) -> pd.DataFrame:
    """
    تحميل الشموع لإطار زمني واحد من قاعدة البيانات.

    drop_last: إذا True، نستبعد آخر شمعة (غير مكتملة) لأن التحليل
               عليها غير موثوق — الشمعة الحالية قد تتغير في ثوانيها الأخيرة.
    """
    table = f"{symbol}_{timeframe}"
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql(
            f'SELECT * FROM "{table}" ORDER BY timestamp ASC',
            conn,
            parse_dates=["timestamp"],
        )
    finally:
        conn.close()

    # استبعاد آخر شمعة (غير مكتملة)
    if drop_last and len(df) > 1:
        df = df.iloc[:-1].copy()

    return df


def main():
    results = {}

    for tf in TIMEFRAMES:
        print(f"--- {tf} ---")
        try:
            df = load_from_db(SYMBOL, tf, DB_PATH)

            if df.empty:
                print(f"⚠️ لا توجد بيانات لـ {tf}\n")
                results[tf] = {"error": "empty_table"}
                continue

            # التحليل الكامل
            df = analyze(df)

            # ملخص
            summary = summarize(df)
            results[tf] = summary

            print(f"  الاتجاه الحالي : {summary['current_trend']}")
            print(f"  آخر إغلاق      : {summary['last_close']:.2f}")
            print(f"  آخر شمعة       : {summary['last_timestamp']}")
            print(f"  --------- الأعداد الكلية ---------")
            print(f"  BOS/CHOCH      : {summary['totals']['events']}")
            print(f"  FVG            : {summary['totals']['fvgs']}")
            print(f"  Order Blocks   : {summary['totals']['order_blocks']}")
            print(f"  مناطق سيولة    : {summary['totals']['liquidity']}")
            print(f"  --------- آخر 5 من كل نوع ---------")
            print(f"  آخر 5 أحداث    : {len(summary['events'])}")
            print(f"  آخر 5 FVG      : {len(summary['fvgs'])}")
            print(f"  آخر 5 OB       : {len(summary['order_blocks'])}")
            print(f"  آخر 5 سيولة    : {len(summary['liquidity'])}")
            print()

        except Exception as e:
            print(f"❌ خطأ في {tf}: {e}\n")
            results[tf] = {"error": str(e)}

    # حفظ النتائج
    out_path = Path("data/smc_snapshot.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    print(f"✅ تم حفظ النتائج في {out_path}")


if __name__ == "__main__":
    main()