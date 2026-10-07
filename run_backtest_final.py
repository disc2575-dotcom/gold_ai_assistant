"""
run_backtest_final.py
Backtest النهائي الشامل - يستخدم كل مكونات النظام.
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np

from core.config import DB_PATH, SYMBOL_DB
from smc.engine import analyze
from signals.generator import generate_signal
from risk.manager import manage_risk


# ============================================================
# إعدادات
# ============================================================
TIMEFRAME = "H1"
LOOKBACK_BARS = 300
FORWARD_BARS = 100
STEP = 5
MAX_HOLD_BARS = 100
COOLDOWN_BARS = 8
MIN_CONFIDENCE = 40

OUTPUT_DIR = Path("data")
JSON_OUTPUT = OUTPUT_DIR / "backtest_final_results.json"
CSV_OUTPUT = OUTPUT_DIR / "backtest_final_trades.csv"
REPORT_OUTPUT = OUTPUT_DIR / "backtest_final_report.txt"


# ============================================================
# تحميل البيانات
# ============================================================
def load_data() -> pd.DataFrame:
    table = f"{SYMBOL_DB}_{TIMEFRAME}"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        df = pd.read_sql(
            f'SELECT * FROM "{table}" ORDER BY timestamp ASC',
            conn,
            parse_dates=["timestamp"],
        )
    finally:
        conn.close()
    return df.reset_index(drop=True)


# ============================================================
# تشغيل Backtest
# ============================================================
def run_backtest(df: pd.DataFrame):
    print(f"📊 عدد الشموع: {len(df)}")
    print(f"🔍 جاري التحليل الشامل...")

    # تحليل SMC كامل
    print("   ⏳ تحليل SMC...")
    analyzed = analyze(df.copy())
    print(f"   ✅ تم التحليل")

    trades = []
    last_trade_end = 0
    signals_generated = 0

    total_bars = len(analyzed)

    for i in range(LOOKBACK_BARS, total_bars - FORWARD_BARS, STEP):
        # Cooldown
        if i < last_trade_end:
            continue

        # توليد الإشارة
        signal = generate_signal(analyzed, i)

        if not signal["action"]:
            continue

        if signal["confidence"] < MIN_CONFIDENCE:
            continue

        signals_generated += 1

        # إدارة المخاطر
        try:
            risk_data = manage_risk(analyzed, i, signal["action"])
        except Exception:
            continue

        entry = risk_data["entry"]
        sl = risk_data["stop_loss"]
        tp = risk_data["target"]
        direction = signal["action"]

        if direction == "BUY":
            if sl >= entry or tp <= entry:
                continue
        else:
            if sl <= entry or tp >= entry:
                continue

        # متابعة الصفقة
        future = analyzed.iloc[i + 1:i + 1 + FORWARD_BARS]
        if future.empty:
            continue

        outcome = "open"
        exit_price = None
        exit_bar = i + FORWARD_BARS
        mfe = 0.0
        mae = 0.0
        risk = abs(entry - sl)

        for j, (_, row) in enumerate(future.iterrows(), start=i + 1):
            high = float(row["high"])
            low = float(row["low"])

            if direction == "BUY":
                favorable = high - entry
                adverse = entry - low
                hit_sl = low <= sl
                hit_tp = high >= tp
            else:
                favorable = entry - low
                adverse = high - entry
                hit_sl = high >= sl
                hit_tp = low <= tp

            mfe = max(mfe, favorable)
            mae = max(mae, adverse)

            if hit_sl and hit_tp:
                outcome, exit_price, exit_bar = "loss", sl, j
                break
            if hit_sl:
                outcome, exit_price, exit_bar = "loss", sl, j
                break
            if hit_tp:
                outcome, exit_price, exit_bar = "win", tp, j
                break

        if outcome == "open":
            exit_price = float(future["close"].iloc[-1])

        last_trade_end = exit_bar + COOLDOWN_BARS

        # حساب النتيجة بـ R
        if direction == "BUY":
            r = (exit_price - entry) / risk if risk > 0 else 0
        else:
            r = (entry - exit_price) / risk if risk > 0 else 0

        trades.append({
            "bar": i,
            "timestamp": str(analyzed.iloc[i]["timestamp"]),
            "direction": direction,
            "confidence": signal["confidence"],
            "reasons": " + ".join(signal["reasons"]),
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "exit_price": round(exit_price, 2),
            "outcome": outcome,
            "r": round(r, 3),
            "mfe_r": round(mfe / risk, 3) if risk > 0 else 0,
            "mae_r": round(mae / risk, 3) if risk > 0 else 0,
        })

    print(f"✅ تم توليد {signals_generated} إشارة")
    print(f"✅ تم إنشاء {len(trades)} صفقة")
    return trades


# ============================================================
# حساب الأداء
# ============================================================
def calculate_performance(trades: list) -> dict:
    if not trades:
        return {
            "total": 0, "wins": 0, "losses": 0, "open": 0,
            "win_rate": 0.0, "profit_factor": 0.0,
            "total_r": 0.0, "expectancy": 0.0,
            "max_dd": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "avg_mfe": 0.0, "avg_mae": 0.0,
        }

    df = pd.DataFrame(trades)

    wins = df[df["outcome"] == "win"]
    losses = df[df["outcome"] == "loss"]
    opened = df[df["outcome"] == "open"]

    gross_profit = wins["r"].sum() if len(wins) > 0 else 0
    gross_loss = abs(losses["r"].sum()) if len(losses) > 0 else 0

    if gross_loss > 0:
        pf = gross_profit / gross_loss
    elif gross_profit > 0:
        pf = float('inf')
    else:
        pf = 0.0

    total_r = df["r"].sum()
    expectancy = df["r"].mean()

    # Drawdown
    equity = df["r"].cumsum()
    peak = equity.cummax()
    dd = equity - peak
    max_dd = abs(dd.min())

    wr = len(wins) / (len(wins) + len(losses)) * 100 if (len(wins) + len(losses)) > 0 else 0

    return {
        "total": len(df),
        "wins": len(wins),
        "losses": len(losses),
        "open": len(opened),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2) if pf != float('inf') else "∞",
        "total_r": round(total_r, 2),
        "expectancy": round(expectancy, 3),
        "max_dd": round(max_dd, 2),
        "avg_win": round(wins["r"].mean(), 3) if len(wins) > 0 else 0,
        "avg_loss": round(losses["r"].mean(), 3) if len(losses) > 0 else 0,
        "avg_mfe": round(df["mfe_r"].mean(), 3),
        "avg_mae": round(df["mae_r"].mean(), 3),
    }


# ============================================================
# طباعة التقرير
# ============================================================
def print_report(perf: dict, trades: list):
    print()
    print("=" * 70)
    print("📊 نتائج Backtest النهائي — XAUUSD H1")
    print("=" * 70)

    print("\n📈 الأداء:")
    print(f"  عدد الصفقات:     {perf['total']}")
    print(f"  ✅ رابحة:        {perf['wins']}")
    print(f"  ❌ خاسرة:        {perf['losses']}")
    print(f"  ⏳ مفتوحة:       {perf['open']}")
    print()
    print(f"  🎯 Win Rate:     {perf['win_rate']}%")
    print(f"  ⚖️  Profit Factor: {perf['profit_factor']}")
    print(f"  📊 Total R:      {perf['total_r']}R")
    print(f"  📐 Expectancy:   {perf['expectancy']}R")
    print(f"  📉 Max Drawdown: {perf['max_dd']}R")
    print()
    print(f"  📈 متوسط الربح:  {perf['avg_win']}R")
    print(f"  📉 متوسط الخسارة: {perf['avg_loss']}R")
    print(f"  🚀 متوسط MFE:    {perf['avg_mfe']}R")
    print(f"  ⚠️  متوسط MAE:    {perf['avg_mae']}R")

    if trades:
        print("\n📋 آخر 10 صفقات:")
        print("-" * 70)
        for t in trades[-10:]:
            icon = "✅" if t["outcome"] == "win" else "❌" if t["outcome"] == "loss" else "⏳"
            print(f"  {icon} {t['timestamp'][:19]} | {t['direction']:4} | "
                  f"entry: {t['entry']:.2f} | R: {t['r']:+.3f}")

    print()
    print("=" * 70)


# ============================================================
# حفظ النتائج
# ============================================================
def save_results(perf: dict, trades: list):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "timestamp": str(datetime.now()),
        "settings": {
            "timeframe": TIMEFRAME,
            "min_confidence": MIN_CONFIDENCE,
            "cooldown_bars": COOLDOWN_BARS,
            "forward_bars": FORWARD_BARS,
        },
        "performance": perf,
        "trades": trades,
    }

    with open(JSON_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    if trades:
        pd.DataFrame(trades).to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")

    # تقرير نصي
    with open(REPORT_OUTPUT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("📊 Backtest Final Report\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write(f"Timeframe: {TIMEFRAME}\n\n")
        f.write(f"Total Trades: {perf['total']}\n")
        f.write(f"Win Rate: {perf['win_rate']}%\n")
        f.write(f"Profit Factor: {perf['profit_factor']}\n")
        f.write(f"Total R: {perf['total_r']}R\n")
        f.write(f"Expectancy: {perf['expectancy']}R\n")
        f.write(f"Max Drawdown: {perf['max_dd']}R\n")

    print(f"\n💾 تم حفظ النتائج:")
    print(f"   JSON: {JSON_OUTPUT}")
    print(f"   CSV: {CSV_OUTPUT}")
    print(f"   Report: {REPORT_OUTPUT}")


# ============================================================
# Main
# ============================================================
def main():
    print("=" * 70)
    print("🚀 Backtest النهائي — XAUUSD H1")
    print("=" * 70)
    print()

    df = load_data()

    if len(df) < LOOKBACK_BARS + FORWARD_BARS + 50:
        print("⚠️ بيانات غير كافية")
        return

    trades = run_backtest(df)

    perf = calculate_performance(trades)
    print_report(perf, trades)
    save_results(perf, trades)

    print("\n🎉 انتهى Backtest النهائي!")


if __name__ == "__main__":
    main()