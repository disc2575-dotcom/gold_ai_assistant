"""
run_day3.py
تشغيل محرك الإشارات وطباعة التقرير النهائي - النسخة المحسّنة.
"""

import json
from pathlib import Path

from smc.signal_generator import generate_signal


SNAPSHOT_PATH = "data/smc_snapshot.json"


def _format_trend(trend: str) -> str:
    if trend == "bullish":
        return "🟢 صاعد "
    elif trend == "bearish":
        return "🔴 هابط "
    return "⚪ محايد"


def _print_separator(char="═", length=70):
    print(char * length)


def print_report(signal: dict):
    _print_separator()
    print("🎯 إشارة التداول — XAUUSD")
    _print_separator()

    # ============ تحليل الأطر ============
    print("\n📊 تحليل الأطر الزمنية:")
    for tf in ["D1", "H4", "H1", "M30", "M15", "M5"]:
        info = signal["timeframes"].get(tf, {})
        trend = info.get("trend", "?")
        weight = info.get("weight", 0)
        price = info.get("last_close")
        price_str = f" | {price:.2f}" if price else ""
        print(f"   {tf:4} {_format_trend(trend)} (وزن {weight}){price_str}")

    # ============ القرار ============
    print()
    _print_separator("─")
    signal_emoji = {
        "BUY": "🟢 شراء",
        "SELL": "🔴 بيع ",
        "WAIT": "⏸️  انتظار",
    }
    print(f"🎯 التوصية: {signal_emoji.get(signal['signal'], signal['signal'])}")
    print(f"📈 الاتجاه المرجّح: {signal['bias']}")
    print(f"🎚️  الثقة: {signal['confidence']}%")
    print(f"🤝 الإجماع: {signal['consensus_ratio']*100:.0f}%")
    _print_separator("─")

    # ============ الأسباب ============
    print("\n🔍 التحليل:")
    for r in signal["reasoning"]:
        print(f"   • {r}")

    # ============ التحذيرات ============
    if signal["warnings"]:
        print("\n⚠️  تحذيرات:")
        for w in signal["warnings"]:
            print(f"   • {w}")

    # ============ شرط التحول ============
    if signal.get("switch_condition"):
        print("\n🔄 شرط التحول إلى إشارة فعلية:")
        print(f"   • {signal['switch_condition']}")

    # ============ المستويات ============
    lv = signal["levels"]
    print("\n💰 المستويات المهمة:")
    print(f"   السعر الحالي: {lv.get('current_price', 'N/A')}")

    if lv.get("nearest_resistance"):
        print(f"   أقرب مقاومة : {lv['nearest_resistance']}")
    if lv.get("nearest_support"):
        print(f"   أقرب دعم    : {lv['nearest_support']}")

    # ============ مستويات التداول (حتى في حالة WAIT) ============
    if lv.get("entry") and lv.get("stop_loss"):
        print()
        _print_separator("─")
        direction = "بيع 🔴" if signal["bias"] == "bearish" else "شراء 🟢"
        print(f"📋 سيناريو {direction} (إذا تحققت الشروط):")
        print(f"   الدخول  : {lv['entry']}")
        print(f"   الوقف   : {lv['stop_loss']}")

        entry = lv["entry"]
        sl = lv["stop_loss"]
        risk = abs(entry - sl)
        for idx, tp in enumerate(lv["targets"], 1):
            reward = abs(tp - entry)
            rr = reward / risk if risk > 0 else 0
            print(f"   TP{idx}   : {tp}  (R:R = {rr:.2f})")
        _print_separator("─")

    # ============ السيناريوهات الشرطية ============
    if signal.get("conditional_scenarios"):
        print()
        _print_separator("─")
        print("🎬 سيناريوهات شرطية:")
        for sc in signal["conditional_scenarios"]:
            print(f"\n   📌 {sc['condition']}")
            print(f"      الإجراء: {sc['action']}")
            print(f"      الدخول : {sc['entry']}")
            print(f"      الوقف  : {sc['stop_loss']}")
            entry = sc["entry"]
            sl = sc["stop_loss"]
            risk = abs(entry - sl)
            for idx, tp in enumerate(sc["targets"], 1):
                reward = abs(tp - entry)
                rr = reward / risk if risk > 0 else 0
                print(f"      TP{idx}   : {tp}  (R:R = {rr:.2f})")
        _print_separator("─")

    print()


def main():
    snapshot_path = Path(SNAPSHOT_PATH)
    if not snapshot_path.exists():
        print(f"❌ لم يُعثر على {snapshot_path}")
        print("   شغّل أولاً: python run_day2.py")
        return

    with open(snapshot_path, "r", encoding="utf-8") as f:
        snapshot = json.load(f)

    print(f"✅ تم تحميل snapshot من {snapshot_path}")
    print(f"   الأطر المتوفرة: {list(snapshot.keys())}")
    print()

    signal = generate_signal(snapshot)

    print_report(signal)

    out_path = Path("data/signal.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, indent=2, ensure_ascii=False, default=str)
    print(f"💾 تم حفظ الإشارة في {out_path}")


if __name__ == "__main__":
    main()