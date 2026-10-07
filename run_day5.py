"""
run_day5.py
تشغيل نظام الجدولة.
"""

from core.scheduler import run_scheduler


def main():
    print("=" * 60)
    print("🚀 اليوم الخامس: نظام متكامل")
    print("=" * 60)
    print()
    print("🔄 سيقوم النظام بـ:")
    print("   1. تحديث البيانات كل 5 دقائق")
    print("   2. تحليل SMC")
    print("   3. توليد الإشارات")
    print("   4. حفظ في signal.json")
    print()
    print("⏹️  لإيقاف النظام: اضغط Ctrl+C")
    print("=" * 60)
    print()

    try:
        run_scheduler(interval_minutes=5)
    except KeyboardInterrupt:
        print("\n✅ تم إيقاف النظام بشكل نظيف")


if __name__ == "__main__":
    main()