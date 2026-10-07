"""
debug_backtest.py
فحص سريع — لماذا Backtest لا يُنتج تداولات؟
"""

import sqlite3
import pandas as pd
from core.config import SYMBOL_DB as SYMBOL, DB_PATH
from smc.engine import analyze
from smc.signal_generator import generate_signal
from backtest_runner import load_full_data, df_to_snapshot, LOOKBACK_BARS


def main():
    df = load_full_data(SYMBOL, "H1", DB_PATH)
    print(f"عدد الشموع: {len(df)}")

    # نأخذ نقطة واحدة في المنتصف
    test_idx = len(df) // 2
    print(f"\nنختبر الشمعة رقم: {test_idx}")
    print(f"التاريخ: {df.iloc[test_idx]['timestamp']}")

    window = df.iloc[:test_idx].copy()
    print(f"حجم النافذة: {len(window)}")

    # 1) التحليل
    print("\n[1] تشغيل analyze...")
    try:
        analyzed = analyze(window)
        new_cols = [c for c in analyzed.columns if c not in window.columns]
        print(f"    ✅ تم. الأعمدة الجديدة: {new_cols}")
    except Exception as e:
        print(f"    ❌ فشل: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2) التحويل إلى snapshot
    print("\n[2] تحويل إلى snapshot...")
    try:
        snapshot = df_to_snapshot(analyzed)
        print(f"    ✅ تم. المفاتيح: {list(snapshot.keys())}")

        h1_data = snapshot.get("H1", {})
        print(f"    H1.current_trend : {h1_data.get('current_trend')}")
        print(f"    H1.last_close    : {h1_data.get('last_close')}")
        print(f"    H1.fvgs count    : {len(h1_data.get('fvgs', []))}")
        print(f"    H1.obs count     : {len(h1_data.get('order_blocks', []))}")
        print(f"    H1.liqs count    : {len(h1_data.get('liquidity', []))}")
    except Exception as e:
        print(f"    ❌ فشل: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3) توليد إشارة
    print("\n[3] توليد إشارة...")
    try:
        signal = generate_signal(snapshot)
        print(f"    ✅ الإشارة: {signal['signal']}")
        print(f"    الثقة: {signal['confidence']}%")
        print(f"    bias: {signal['bias']}")
        print(f"    bias_score: {signal['bias_score']}")
        print(f"    consensus: {signal['consensus_ratio']}")
        print(f"    levels: {signal['levels']}")
    except Exception as e:
        print(f"    ❌ فشل: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4) تحليل السبب
    print("\n[4] التحليل:")
    if signal["signal"] == "WAIT":
        print("    ⚠️  الإشارة WAIT — لهذا Backtest يتجاهلها")
        print(f"\n    الأسباب:")
        for r in signal.get("reasoning", []):
            print(f"      • {r}")
        print(f"\n    التحذيرات:")
        for w in signal.get("warnings", []):
            print(f"      • {w}")
    else:
        print(f"    ✅ الإشارة ليست WAIT — ستُسجَّل في Backtest")


if __name__ == "__main__":
    main()