"""
backtest/full_backtest.py
Backtest شامل مع إعدادات مخصصة لكل إطار.
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import (
    DB_PATH, SYMBOL_DB,
    TIMEFRAME_SETTINGS,
    BACKTEST_CONFIG,
)
from smc.engine import analyze


# ============================================================
# الإعدادات
# ============================================================
TIMEFRAMES = [tf for tf, s in TIMEFRAME_SETTINGS.items() if s.get("enabled", True)]

LOOKBACK_BARS = BACKTEST_CONFIG["lookback_bars"]
FORWARD_BARS = BACKTEST_CONFIG["forward_bars"]
STEP = BACKTEST_CONFIG["step"]
COOLDOWN_BARS = BACKTEST_CONFIG["cooldown_bars"]
ATR_PERIOD = BACKTEST_CONFIG["atr_period"]

OUTPUT_DIR = Path("data")
JSON_OUTPUT = OUTPUT_DIR / "full_backtest_results.json"


# ============================================================
# تحميل البيانات
# ============================================================
def load_data(timeframe: str) -> pd.DataFrame:
    table = f"{SYMBOL_DB}_{timeframe}"
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
# ATR
# ============================================================
def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ============================================================
# شروط الدخول
# ============================================================
def check_entry_conditions(df: pd.DataFrame, i: int, min_score: float = 6.5) -> dict:
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

    score = 2.0
    reasons = ["Trend"]

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
        reasons.append("BOS")

    # OB
    ob_window = df.iloc[max(0, i - 10):i + 1]
    for _, row in ob_window.iterrows():
        if side == "BUY" and row.get("bullish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["low"] <= row["ob_high"]:
                    score += 2.0
                    reasons.append("OB")
                    break
        elif side == "SELL" and row.get("bearish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["high"] <= row["ob_high"]:
                    score += 2.0
                    reasons.append("OB")
                    break

    # FVG
    fvg_window = df.iloc[max(0, i - 10):i + 1]
    for _, row in fvg_window.iterrows():
        if side == "BUY" and row.get("bullish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["low"] <= row["fvg_top"]:
                    score += 1.0
                    reasons.append("FVG")
                    break
        elif side == "SELL" and row.get("bearish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["high"] <= row["fvg_top"]:
                    score += 1.0
                    reasons.append("FVG")
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
            reasons.append("Engulfing")
    else:
        if (last["close"] < last["open"] and
            prev["close"] > prev["open"] and
            last["close"] < prev["open"] and
            last["open"] > prev["close"] and
            body_last > body_prev * 0.6):
            score += 2.0
            reasons.append("Engulfing")

    if score >= min_score:
        return {"action": side, "score": score, "reason": " + ".join(reasons)}

    return {"action": None}


# ============================================================
# Backtest لإطار واحد
# ============================================================
def backtest_timeframe(df: pd.DataFrame, timeframe: str) -> dict:
    settings = TIMEFRAME_SETTINGS[timeframe]
    atr_mult = settings["atr_mult"]
    min_score = settings["min_score"]
    rr_ratio = settings["rr"]

    total_bars = len(df)
    if total_bars < LOOKBACK_BARS + FORWARD_BARS + 20:
        return {"error": "بيانات غير كافية"}

    df = df.copy()
    df["_atr"] = calculate_atr(df, ATR_PERIOD)

    trades = []
    last_trade_end_bar = 0

    for i in range(LOOKBACK_BARS, total_bars - FORWARD_BARS, STEP):
        if i < last_trade_end_bar:
            continue

        start = max(0, i - LOOKBACK_BARS)
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

        future = df.iloc[i + 1:i + 1 + FORWARD_BARS]
        if future.empty:
            continue

        outcome = "open"
        exit_price = entry_price
        exit_bar = i + FORWARD_BARS

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

        last_trade_end_bar = exit_bar + COOLDOWN_BARS

        if entry["action"] == "BUY":
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        trades.append({
            "timestamp": str(df.iloc[i]["timestamp"]),
            "signal": entry["action"],
            "entry": entry_price,
            "sl": sl,
            "tp": tp,
            "outcome": outcome,
            "exit_price": exit_price,
            "pnl_pct": pnl_pct,
        })

    return analyze_results(trades)


# ============================================================
# إحصائيات
# ============================================================
def analyze_results(trades: list) -> dict:
    if not trades:
        return {
            "total": 0, "wins": 0, "losses": 0, "open": 0,
            "win_rate": 0.0, "profit_factor": 0.0, "total_pnl": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0,
        }

    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    opens = [t for t in trades if t["outcome"] == "open"]

    gp = sum(t["pnl_pct"] for t in wins)
    gl = abs(sum(t["pnl_pct"] for t in losses))
    pf = gp / gl if gl > 0 else float("inf") if gp > 0 else 0.0
    total_pnl = sum(t["pnl_pct"] for t in trades)
    wr = len(wins) / len(trades) * 100 if trades else 0

    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "open": len(opens),
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(gp / len(wins), 3) if wins else 0.0,
        "avg_loss": round(-gl / len(losses), 3) if losses else 0.0,
    }


# ============================================================
# Backtest كل الأطر
# ============================================================
def run_full_backtest() -> dict:
    print("=" * 70)
    print("🚀 Backtest شامل — XAUUSD")
    print("=" * 70)
    print(f"   STEP = {STEP} | FORWARD = {FORWARD_BARS} | LOOKBACK = {LOOKBACK_BARS}")
    print(f"   الأطر المفعلة: {', '.join(TIMEFRAMES)}")
    print()

    results = {}

    for tf in TIMEFRAMES:
        s = TIMEFRAME_SETTINGS[tf]
        print(f"📊 {tf} — ATR×{s['atr_mult']} | Score≥{s['min_score']} | RR={s['rr']}")
        try:
            df = load_data(tf)
            result = backtest_timeframe(df, tf)
            results[tf] = result
            print(f"   ✅ الصفقات: {result.get('total', 0)} | "
                  f"WR: {result.get('win_rate', 0)}% | "
                  f"PF: {result.get('profit_factor', 0)} | "
                  f"PnL: {result.get('total_pnl', 0)}%")
        except Exception as e:
            print(f"   ❌ خطأ: {e}")
            results[tf] = {"error": str(e)}
        print()

    return results


# ============================================================
# الطباعة
# ============================================================
def print_summary(results: dict):
    print("=" * 70)
    print("📊 الملخص النهائي")
    print("=" * 70)
    print(f"{'TF':<6} {'Trades':<8} {'Wins':<6} {'Losses':<8} {'WR%':<8} {'PF':<8} {'PnL%':<10}")
    print("-" * 70)

    total_pnl = 0.0

    for tf, r in results.items():
        if "error" in r:
            print(f"{tf:<6} ❌ {r['error']}")
            continue
        print(f"{tf:<6} {r['total']:<8} {r['wins']:<6} {r['losses']:<8} "
              f"{r['win_rate']:<8} {r['profit_factor']:<8} {r['total_pnl']:<10}")
        total_pnl += r["total_pnl"]

    print("-" * 70)
    print(f"{'المجموع':<6} {'':<8} {'':<6} {'':<8} {'':<8} {'':<8} {round(total_pnl, 2):<10}")
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
    results = run_full_backtest()
    print_summary(results)
    save_results(results)


if __name__ == "__main__":
    main()