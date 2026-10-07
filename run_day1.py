"""
run_day1.py
جلب وتنظيف وتخزين والتحقق من بيانات XAUUSD على 6 أطر زمنية.
"""

from core.config import SYMBOL_TWELVEDATA, SYMBOL_DB, TIMEFRAMES, DB_PATH, DEFAULT_SOURCE
from data_pipeline.collector import fetch_ohlcv
from data_pipeline.cleaner import clean_ohlcv
from data_pipeline.storage import store_ohlcv
from data_pipeline.validator import validate_ohlcv


def main():
    print("=" * 60)
    print(f"🚀 بدء جمع البيانات لـ {SYMBOL_TWELVEDATA}")
    print(f"📊 عدد الأطر الزمنية: {len(TIMEFRAMES)}")
    print(f"📌 المصدر: {DEFAULT_SOURCE}")
    print(f"💾 قاعدة البيانات: {DB_PATH}")
    print("=" * 60)
    print()

    summary = []

    for tf in TIMEFRAMES:
        print(f"--- {tf} ---")
        try:
            # 1. جلب البيانات
            raw = fetch_ohlcv(tf)
            print(f"   ✅ تم جلب {len(raw)} شمعة خام")

            # 2. تنظيف البيانات
            clean = clean_ohlcv(raw, tf)

            # 3. تخزين في SQLite
            store_ohlcv(clean, SYMBOL_DB, tf, str(DB_PATH))

            # 4. التحقق من السلامة
            report = validate_ohlcv(clean, tf)
            status = "✅ سليم" if report["passed"] else "❌ يوجد خلل"
            print(f"   {status} — {report['bars_count']} شمعة")
            print(f"   📅 النطاق: {report['date_range']}")
            for issue in report["issues"]:
                print(f"      {issue}")

            summary.append({
                "tf": tf,
                "count": report["bars_count"],
                "passed": report["passed"],
            })

        except Exception as e:
            print(f"   ❌ خطأ في {tf}: {e}")
            summary.append({"tf": tf, "count": 0, "passed": False})
        print()

    # ملخص نهائي
    print("=" * 60)
    print("📋 الملخص النهائي:")
    print("=" * 60)
    for s in summary:
        status = "✅" if s["passed"] else "❌"
        print(f"  {status} {s['tf']:5s} → {s['count']:5d} شمعة")
    print("=" * 60)
    print(f"🎉 انتهى اليوم الأول. البيانات محفوظة في: {DB_PATH}")


if __name__ == "__main__":
    main()