"""
forward_test.py
Forward Test — اختبار الاستراتيجية على بيانات جديدة.
"""

import json
from pathlib import Path
from datetime import timedelta

import pandas as pd

from core.config import TIMEFRAME_SETTINGS
from smc.engine import analyze
from backtest.full_backtest import (
    load_data,
    analyze_results,
    check_entry_conditions,
    calculate_atr,
)


OUTPUT_DIR = Path("data")
JSON_OUTPUT = OUTPUT_DIR / "forward_test_results.json"

FORWARD_DAYS = 180
ACTIVE_TIMEFRAMES = [tf for tf, s in TIMEFRAME_SETTINGS.items() if s.get("enabled", True)]


# ============================================================
# Backtest على DataFrame
# ============================================================
def run_backtest_on_df(df: pd.DataFrame, timeframe: str) -> dict:
    if len(df) < 50:
        return {"total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "profit_factor": 0.0, "total_pnl": 0.0}

    settings = TIMEFRAME_SETTINGS[timeframe]
    atr_mult = settings["atr_mult"]
    min_score = settings["min_score"]
    rr_ratio = settings["rr"]

    lookback = 30
    forward = 30
    step = 5
    cooldown = 5

    df = df.copy()
    df["_atr"] = calculate_atr(df, 14)

    total_bars = len(df)
    trades = []
    last_trade_end_bar = 0

    for i in range(lookback, total_bars - forward, step):
        if i < last_trade_end_bar:
            continue

        start = max(0, i - lookback)
        window = df.iloc[start:i + 1].copy()

        try:
            analyzed = analyze(window)
        except Exception:
            continue

        entry = check_entry_conditions(analyzed, len(analyzed) - 1, min_score)
        if not entry["action"]:
            continue

        atr = df.iloc[i]["_atr"]
        if pd.isna(atr) or atr <= 0:
            atr = df.iloc[i]["close"] * 0.003

        entry_price = df.iloc[i]["close"]
        sl_distance = atr * atr_mult

        if entry["action"] == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * rr_ratio
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * rr_ratio

        future = df.iloc[i + 1:i + 1 + forward]
        if future.empty:
            continue

        outcome = "open"
        exit_price = entry_price
        exit_bar = i + forward

        for j, (_, row) in enumerate(future.iterrows(), start=i + 1):
            if entry["action"] == "BUY":
                if row["low"] <= sl:
                    outcome, exit_price, exit_bar = "loss", sl, j
                    break
                if row["high"] >= tp:
                    outcome, exit_price, exit_bar = "win", tp, j
                    break
            else:
                if row["high"] >= sl:
                    outcome, exit_price, exit_bar = "loss", sl, j
                    break
                if row["low"] <= tp:
                    outcome, exit_price, exit_bar = "win", tp, j
                    break

        last_trade_end_bar = exit_bar + cooldown

        if entry["action"] == "BUY":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        trades.append({
            "timestamp": str(df.iloc[i]["timestamp"]),
            "signal": entry["action"],
            "outcome": outcome,
            "pnl_pct": pnl_pct,
        })

    return analyze_results(trades)


# ============================================================
# تقسيم البيانات
# ============================================================
def split_data(df: pd.DataFrame, days: int) -> tuple:
    if df.empty:
        return df, df

    latest = df["timestamp"].max()
    cutoff = latest - timedelta(days=days)

    backtest_df = df[df["timestamp"] < cutoff].copy().reset_index(drop=True)
    forward_df = df[df["timestamp"] >= cutoff].copy().reset_index(drop=True)

    return backtest_df, forward_df


# ============================================================
# Forward Test الرئيسي
# ============================================================
def run_forward_test():
    print("=" * 70)
    print("🚀 Forward Test — اختبار على بيانات جديدة")
    print("=" * 70)
    print(f"   الأطر: {', '.join(ACTIVE_TIMEFRAMES)}")
    print(f"   فترة Forward: آخر {FORWARD_DAYS} يوم")
    print()

    results = {}

    for tf in ACTIVE_TIMEFRAMES:
        print(f"\n📊 {tf}")
        print("-" * 70)

        try:
            df = load_data(tf)
            if df.empty:
                print("   ❌ لا توجد بيانات")
                continue

            print(f"   📥 عدد الشموع: {len(df)}")

            backtest_df, forward_df = split_data(df, FORWARD_DAYS)

            print(f"   📊 Backtest: {len(backtest_df)} شمعة")
            print(f"   📊 Forward:  {len(forward_df)} شمعة")

            if len(forward_df) < 20:
                print("   ⚠️ بيانات Forward قليلة جداً")
                continue

            print("\n   🔵 Backtest (البيانات الكاملة)...")
            full_result = run_backtest_on_df(df, tf)
            print(f"      → صفقات: {full_result['total']} | "
                  f"WR: {full_result['win_rate']}% | "
                  f"PF: {full_result['profit_factor']} | "
                  f"PnL: {full_result['total_pnl']}%")

            print("\n   🟢 Forward Test (البيانات الحديثة)...")
            forward_result = run_backtest_on_df(forward_df, tf)
            print(f"      → صفقات: {forward_result['total']} | "
                  f"WR: {forward_result['win_rate']}% | "
                  f"PF: {forward_result['profit_factor']} | "
                  f"PnL: {forward_result['total_pnl']}%")

            if full_result["total"] > 0 and forward_result["total"] > 0:
                wr_diff = forward_result["win_rate"] - full_result["win_rate"]
                pf_diff = forward_result["profit_factor"] - full_result["profit_factor"]
                pnl_diff = forward_result["total_pnl"] - full_result["total_pnl"]

                stability = "✅ مستقر" if abs(pf_diff) < 0.5 else "⚠️ غير مستقر"

                print(f"\n   📊 المقارنة:")
                print(f"      WR: {wr_diff:+.1f}% | PF: {pf_diff:+.2f} | PnL: {pnl_diff:+.2f}%")
                print(f"      {stability}")

            results[tf] = {
                "backtest": full_result,
                "forward": forward_result,
            }

        except Exception as e:
            print(f"   ❌ خطأ: {e}")
            results[tf] = {"error": str(e)}

    return results


# ============================================================
# الطباعة
# ============================================================
def print_summary(results: dict):
    print("\n" + "=" * 70)
    print("📊 الملخص النهائي — Forward Test")
    print("=" * 70)
    print(f"{'TF':<6} {'Stage':<10} {'Trades':<8} {'WR%':<8} {'PF':<8} {'PnL%':<10}")
    print("-" * 70)

    for tf, r in results.items():
        if "error" in r:
            print(f"{tf:<6} ❌ {r['error']}")
            continue

        bt = r["backtest"]
        fw = r["forward"]

        print(f"{tf:<6} {'Backtest':<10} {bt['total']:<8} {bt['win_rate']:<8} "
              f"{bt['profit_factor']:<8} {bt['total_pnl']:<10}")
        print(f"{tf:<6} {'Forward':<10} {fw['total']:<8} {fw['win_rate']:<8} "
              f"{fw['profit_factor']:<8} {fw['total_pnl']:<10}")
        print("-" * 70)

    print("=" * 70)


def save_results(results: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n💾 تم حفظ النتائج في: {JSON_OUTPUT}")


# ============================================================
# Main
# ============================================================
def main():
    results = run_forward_test()
    print_summary(results)
    save_results(results)


if __name__ == "__main__":
    main()