"""
backtest/tune_h1.py
اختبار 3 إعدادات مختلفة لـ H1.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import DB_PATH, SYMBOL_DB
from smc.engine import analyze
from backtest.full_backtest import (
    load_data, calculate_atr, check_entry_conditions, calculate_levels
)


# ============================================================
# 3 سيناريوهات مختلفة
# ============================================================
SCENARIOS = [
    {
        "name": "A — الحالي",
        "atr_mult": 1.8,
        "min_score": 6.5,
        "rr": 2.0,
    },
    {
        "name": "B — SL أوسع",
        "atr_mult": 2.5,
        "min_score": 6.5,
        "rr": 2.0,
    },
    {
        "name": "C — SL أوسع + RR أعلى",
        "atr_mult": 2.5,
        "min_score": 7.0,
        "rr": 2.5,
    },
    {
        "name": "D — SL متوسط + فلتر أقوى",
        "atr_mult": 2.0,
        "min_score": 7.5,
        "rr": 2.0,
    },
]


# ============================================================
# Backtest مع إعدادات مخصصة
# ============================================================
def backtest_with_settings(df, settings):
    atr_mult = settings["atr_mult"]
    min_score = settings["min_score"]
    rr = settings["rr"]

    total_bars = len(df)
    lookback = 100
    forward = 50
    step = 15
    cooldown = 8
    atr_period = 14

    df = df.copy()
    df["_atr"] = calculate_atr(df, atr_period)

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

        entry = check_entry_conditions_with_score(analyzed, len(analyzed) - 1, min_score)
        if not entry["action"]:
            continue

        atr = df.iloc[i]["_atr"]
        if pd.isna(atr) or atr <= 0:
            atr = df.iloc[i]["close"] * 0.003

        entry_price = df.iloc[i]["close"]
        sl_distance = atr * atr_mult

        if entry["action"] == "BUY":
            sl = entry_price - sl_distance
            tp = entry_price + sl_distance * rr
        else:
            sl = entry_price + sl_distance
            tp = entry_price - sl_distance * rr

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
            "outcome": outcome,
            "pnl_pct": pnl_pct,
        })

    return analyze_trades(trades)


def check_entry_conditions_with_score(df, i, min_score):
    """نفس الدالة الأصلية لكن مع min_score متغير."""
    if i < 25:
        return {"action": None}

    last = df.iloc[i]
    prev = df.iloc[i - 1]

    trend = last.get("trend", "neutral")
    if trend == "bullish":
        side = "BUY"
    elif trend == "bearish":
        side = "SELL"
    else:
        return {"action": None}

    score = 2.0  # Trend

    # BOS
    bos_window = df.iloc[max(0, i - 15):i + 1]
    if "break_direction" in bos_window.columns:
        if side == "BUY":
            bos_recent = bool((bos_window["bos"] & (bos_window["break_direction"] == "bullish")).any())
        else:
            bos_recent = bool((bos_window["bos"] & (bos_window["break_direction"] == "bearish")).any())
    else:
        bos_recent = bool(bos_window["bos"].any())
    if bos_recent:
        score += 2.0

    # OB
    ob_window = df.iloc[max(0, i - 10):i + 1]
    for _, row in ob_window.iterrows():
        if side == "BUY" and row.get("bullish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["low"] <= row["ob_high"]:
                    score += 2.0
                    break
        elif side == "SELL" and row.get("bearish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["high"] <= row["ob_high"]:
                    score += 2.0
                    break

    # FVG
    fvg_window = df.iloc[max(0, i - 10):i + 1]
    for _, row in fvg_window.iterrows():
        if side == "BUY" and row.get("bullish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["low"] <= row["fvg_top"]:
                    score += 1.0
                    break
        elif side == "SELL" and row.get("bearish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["high"] <= row["fvg_top"]:
                    score += 1.0
                    break

    # Engulfing
    body_last = abs(last["close"] - last["open"])
    body_prev = abs(prev["close"] - prev["open"])

    if side == "BUY":
        if (last["close"] > last["open"] and
            prev["close"] < prev["open"] and
            last["close"] > prev["open"] and
            last["open"] < prev["close"] and
            body_last > body_prev * 0.6):
            score += 2.0
    else:
        if (last["close"] < last["open"] and
            prev["close"] > prev["open"] and
            last["close"] < prev["open"] and
            last["open"] > prev["close"] and
            body_last > body_prev * 0.6):
            score += 2.0

    if score >= min_score:
        return {"action": side, "score": score}

    return {"action": None}


def analyze_trades(trades):
    if not trades:
        return {"total": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "profit_factor": 0.0, "total_pnl": 0.0}

    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]

    gp = sum(t["pnl_pct"] for t in wins)
    gl = abs(sum(t["pnl_pct"] for t in losses))
    pf = gp / gl if gl > 0 else 0.0
    wr = len(wins) / len(trades) * 100
    total = sum(t["pnl_pct"] for t in trades)

    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "total_pnl": round(total, 2),
    }


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 80)
    print("🔬 اختبار 4 سيناريوهات لتحسين H1")
    print("=" * 80)
    print()

    df = load_data("H1")
    print(f"📊 عدد شموع H1: {len(df)}")
    print()

    results = []

    for scenario in SCENARIOS:
        print(f"🧪 {scenario['name']}")
        print(f"   ATR_MULT={scenario['atr_mult']} | MIN_SCORE={scenario['min_score']} | RR={scenario['rr']}")

        result = backtest_with_settings(df, scenario)
        results.append({"name": scenario["name"], **result})

        print(f"   → صفقات: {result['total']} | "
              f"WR: {result['win_rate']}% | "
              f"PF: {result['profit_factor']} | "
              f"PnL: {result['total_pnl']}%")
        print()

    # جدول نهائي
    print("=" * 80)
    print("📊 مقارنة نهائية")
    print("=" * 80)
    print(f"{'السيناريو':<30} {'صفقات':<8} {'WR%':<8} {'PF':<8} {'PnL%':<10}")
    print("-" * 80)

    for r in results:
        print(f"{r['name']:<30} {r['total']:<8} {r['win_rate']:<8} "
              f"{r['profit_factor']:<8} {r['total_pnl']:<10}")

    print("=" * 80)

    # أفضل سيناريو
    best = max(results, key=lambda x: x["profit_factor"])
    print(f"\n🏆 الأفضل: {best['name']}")
    print(f"   PF: {best['profit_factor']} | PnL: {best['total_pnl']}% | WR: {best['win_rate']}%")


if __name__ == "__main__":
    main()