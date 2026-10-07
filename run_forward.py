"""
run_forward.py
تشغيل Forward Test كامل.
"""

from core.data_updater import update_all_timeframes
from forward_test import main as forward_main


def run():
    print("=" * 70)
    print("🎯 Forward Test Pipeline")
    print("=" * 70)
    print()

    # 1. تحديث البيانات
    print("📥 الخطوة 1: تحديث البيانات من TwelveData...")
    update_all_timeframes()

    # 2. Forward Test
    print("\n\n📊 الخطوة 2: تشغيل Forward Test...")
    forward_main()


if __name__ == "__main__":
    run()