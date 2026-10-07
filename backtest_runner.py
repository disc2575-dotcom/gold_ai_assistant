"""
backtest_runner.py
Backtest مباشر لمنطق SMC - نسخة v4 (بعد 4 إصلاحات جوهرية).

الإصلاحات:
1. SL/TP بـ ATR فقط (بدل last_low الذي كان بعيداً جداً)
2. منع الصفقات المتتالية (لا صفقة جديدة حتى تنتهي السابقة + 10 شموع)
3. FORWARD_BARS = 100 (بدل 50) لتحقيق أهداف TP
4. ATR_SL_MULT = 2.5 (بدل 1.5) لإعطاء مساحة أكبر للسعر
5. RR_RATIO = 1.5 (بدل 2.0) لزيادة فرص الوصول لـ TP
6. MIN_SCORE = 7.0 (بدل 6.0) لفلترة الإشارات الضعيفة
"""

import json
import sqlite3
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import SYMBOL_DB as SYMBOL, DB_PATH
from smc.engine import analyze


# ============================================================
# إعدادات
# ============================================================
TIMEFRAME = "H1"
LOOKBACK_BARS = 200
FORWARD_BARS = 100           # ← إصلاح: زدناها من 50
STEP = 5
RR_RATIO = 1.5               # ← إصلاح: خفضناها من 2.0
ATR_PERIOD = 14
ATR_SL_MULT = 2.5            # ← إصلاح: زدناها من 1.5
BOS_LOOKBACK = 15
OB_LOOKBACK = 10
FVG_LOOKBACK = 10
LIQ_LOOKBACK = 5
MIN_SCORE = 7.0              # ← إصلاح: رفعناها من 6.0
COOLDOWN_BARS = 10           # ← إصلاح: زدناها من 5


# ============================================================
# تحميل البيانات
# ============================================================
def load_full_data(symbol: str, timeframe: str, db_path) -> pd.DataFrame:
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
# شروط الدخول (نظام النقاط)
# ============================================================
def check_entry_conditions(df: pd.DataFrame, i: int) -> dict:
    """نظام النقاط لتوليد إشارات الدخول."""
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

    score = 0.0
    reasons = []

    # 1. الاتجاه
    score += 2.0
    reasons.append("Trend")

    # 2. BOS
    bos_window = df.iloc[max(0, i - BOS_LOOKBACK):i + 1]
    if side == "BUY":
        bos_recent = bool(
            (bos_window["bos"] &
             (bos_window.get("break_direction", pd.Series(["bullish"] * len(bos_window), index=bos_window.index)) == "bullish")).any()
        )
    else:
        bos_recent = bool(
            (bos_window["bos"] &
             (bos_window.get("break_direction", pd.Series(["bearish"] * len(bos_window), index=bos_window.index)) == "bearish")).any()
        )
    if bos_recent:
        score += 2.0
        reasons.append("BOS")

    # 3. OB
    ob_window = df.iloc[max(0, i - OB_LOOKBACK):i + 1]
    touched_ob = False
    for _, row in ob_window.iterrows():
        if side == "BUY" and row.get("bullish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["low"] <= row["ob_high"]:
                    touched_ob = True
                    break
        elif side == "SELL" and row.get("bearish_ob", False):
            if pd.notna(row.get("ob_low")) and pd.notna(row.get("ob_high")):
                if row["ob_low"] <= row["high"] <= row["ob_high"]:
                    touched_ob = True
                    break
    if touched_ob:
        score += 2.0
        reasons.append("OB")

    # 4. FVG
    fvg_window = df.iloc[max(0, i - FVG_LOOKBACK):i + 1]
    touched_fvg = False
    for _, row in fvg_window.iterrows():
        if side == "BUY" and row.get("bullish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["low"] <= row["fvg_top"]:
                    touched_fvg = True
                    break
        elif side == "SELL" and row.get("bearish_fvg", False):
            if pd.notna(row.get("fvg_bottom")) and pd.notna(row.get("fvg_top")):
                if row["fvg_bottom"] <= row["high"] <= row["fvg_top"]:
                    touched_fvg = True
                    break
    if touched_fvg:
        score += 1.0
        reasons.append("FVG")

    # 5. Engulfing
    body_last = abs(last["close"] - last["open"])
    body_prev = abs(prev["close"] - prev["open"])

    if side == "BUY":
        bull_engulf = (
            last["close"] > last["open"] and
            prev["close"] < prev["open"] and
            last["close"] > prev["open"] and
            last["open"] < prev["close"] and
            body_last > body_prev * 0.6
        )
        if bull_engulf:
            score += 2.0
            reasons.append("Engulfing")
    else:
        bear_engulf = (
            last["close"] < last["open"] and
            prev["close"] > prev["open"] and
            last["close"] < prev["open"] and
            last["open"] > prev["close"] and
            body_last > body_prev * 0.6
        )
        if bear_engulf:
            score += 2.0
            reasons.append("Engulfing")

    # 6. Pin Bar
    if body_last > 0:
        if side == "BUY":
            lower_wick = min(last["open"], last["close"]) - last["low"]
            upper_wick = last["high"] - max(last["open"], last["close"])
            if lower_wick > body_last * 1.5 and upper_wick < body_last * 0.7:
                score += 1.5
                reasons.append("PinBar")
        else:
            upper_wick = last["high"] - max(last["open"], last["close"])
            lower_wick = min(last["open"], last["close"]) - last["low"]
            if upper_wick > body_last * 1.5 and lower_wick < body_last * 0.7:
                score += 1.5
                reasons.append("PinBar")

    # 7. سيولة
    liq_window = df.iloc[max(0, i - LIQ_LOOKBACK):i + 1]
    if "liq_swept" in liq_window.columns:
        if side == "BUY":
            broke_liq = bool(
                ((liq_window["buy_liquidity"] == True) &
                 (liq_window["liq_swept"] == True)).any()
            )
        else:
            broke_liq = bool(
                ((liq_window["sell_liquidity"] == True) &
                 (liq_window["liq_swept"] == True)).any()
            )
        if broke_liq:
            score += 1.5
            reasons.append("LiqSweep")

    if score >= MIN_SCORE:
        return {
            "action": side,
            "score": score,
            "reason": f"{side} | Score: {score:.1f} | " + " + ".join(reasons),
        }

    return {"action": None}


# ============================================================
# SL/TP
# ============================================================
def calculate_sl_tp(df: pd.DataFrame, i: int, action: str, atr: float) -> dict:
    """
    SL/TP بـ ATR فقط.
    """
    last = df.iloc[i]
    entry_price = last["close"]

    if pd.isna(atr) or atr <= 0:
        atr = entry_price * 0.003

    sl_distance = atr * ATR_SL_MULT

    if action == "BUY":
        sl = entry_price - sl_distance
        tp = entry_price + (sl_distance * RR_RATIO)
    else:
        sl = entry_price + sl_distance
        tp = entry_price - (sl_distance * RR_RATIO)

    return {
        "entry": round(entry_price, 2),
        "stop_loss": round(sl, 2),
        "target": round(tp, 2),
        "risk_pct": round(abs(sl_distance / entry_price) * 100, 3),
    }


# ============================================================
# Backtest
# ============================================================
def run_backtest(df: pd.DataFrame, step: int = STEP):
    """
    تنفيذ Backtest مع منع الصفقات المكررة.
    """
    total_bars = len(df)
    if total_bars < LOOKBACK_BARS + FORWARD_BARS + 20:
        print(f"⚠️  البيانات غير كافية")
        return []

    df["_atr"] = calculate_atr(df, ATR_PERIOD)

    trades = []
    start_idx = LOOKBACK_BARS
    last_trade_end_bar = 0

    for i in range(start_idx, total_bars - FORWARD_BARS, step):
        # تخطي إذا فيه صفقة حديثة
        if i < last_trade_end_bar:
            continue

        window = df.iloc[:i + 1].copy()

        try:
            analyzed = analyze(window)
        except Exception:
            continue

        entry = check_entry_conditions(analyzed, len(analyzed) - 1)
        if not entry["action"]:
            continue

        atr_value = df.iloc[i].get("_atr", df.iloc[i]["close"] * 0.003)
        sltp = calculate_sl_tp(analyzed, len(analyzed) - 1, entry["action"], atr_value)

        entry_price = sltp["entry"]
        sl = sltp["stop_loss"]
        tp = sltp["target"]

        future = df.iloc[i + 1:i + 1 + FORWARD_BARS]
        if future.empty:
            continue

        outcome = "open"
        exit_price = None
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

        if outcome == "open":
            exit_price = future["close"].iloc[-1]

        last_trade_end_bar = exit_bar + COOLDOWN_BARS

        if entry["action"] == "BUY":
            pnl = (exit_price - entry_price) / entry_price * 100
        else:
            pnl = (entry_price - exit_price) / entry_price * 100

        trades.append({
            "bar": i,
            "timestamp": str(df.iloc[i]["timestamp"]),
            "signal": entry["action"],
            "score": entry.get("score", 0),
            "reason": entry["reason"],
            "entry": entry_price,
            "stop_loss": sl,
            "target": tp,
            "outcome": outcome,
            "exit_price": round(exit_price, 2),
            "pnl_pct": round(pnl, 3),
        })

    return trades


# ============================================================
# الإحصائيات
# ============================================================
def analyze_results(trades: list) -> dict:
    if not trades:
        return {
            "total": 0, "wins": 0, "losses": 0, "open": 0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "profit_factor": 0.0, "total_pnl_pct": 0.0,
        }

    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    opened = sum(1 for t in trades if t["outcome"] == "open")

    win_trades = [t for t in trades if t["outcome"] == "win"]
    loss_trades = [t for t in trades if t["outcome"] == "loss"]

    avg_win = sum(t["pnl_pct"] for t in win_trades) / len(win_trades) if win_trades else 0
    avg_loss = sum(t["pnl_pct"] for t in loss_trades) / len(loss_trades) if loss_trades else 0

    gp = sum(t["pnl_pct"] for t in win_trades)
    gl = abs(sum(t["pnl_pct"] for t in loss_trades))
    pf = gp / gl if gl > 0 else float('inf')
    wr = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    total_pnl = sum(t["pnl_pct"] for t in trades)

    return {
        "total": total, "wins": wins, "losses": losses, "open": opened,
        "win_rate": round(wr, 1),
        "avg_win": round(avg_win, 3),
        "avg_loss": round(avg_loss, 3),
        "profit_factor": round(pf, 2),
        "total_pnl_pct": round(total_pnl, 3),
    }


# ============================================================
# الطباعة
# ============================================================
def print_results(stats: dict, trades: list):
    print()
    print("═" * 70)
    print("📊 نتائج Backtest — XAUUSD H1")
    print("═" * 70)
    print(f"  عدد التداولات    : {stats['total']}")
    print(f"  ✅ رابحة          : {stats['wins']}")
    print(f"  ❌ خاسرة          : {stats['losses']}")
    print(f"  ⏳ مفتوحة         : {stats['open']}")
    print("─" * 70)
    print(f"  🎯 Win Rate       : {stats['win_rate']}%")
    print(f"  📈 متوسط الربح    : {stats['avg_win']}%")
    print(f"  📉 متوسط الخسارة  : {stats['avg_loss']}%")
    print(f"  ⚖️  Profit Factor  : {stats['profit_factor']}")
    print(f"  💰 إجمالي PnL      : {stats['total_pnl_pct']}%")
    print("═" * 70)

    if trades:
        print()
        print("📋 آخر 10 تداولات:")
        print("─" * 70)
        for t in trades[-10:]:
            emoji = "✅" if t["outcome"] == "win" else "❌" if t["outcome"] == "loss" else "⏳"
            print(f"  {emoji} {t['timestamp']} | {t['signal']:4} | "
                  f"entry: {t['entry']} | SL: {t['stop_loss']} | TP: {t['target']} | "
                  f"PnL: {t['pnl_pct']:+.3f}%")

    out_path = Path("data/backtest_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "trades": trades}, f, indent=2,
                  ensure_ascii=False, default=str)
    print(f"\n💾 تم حفظ النتائج في {out_path}")


# ============================================================
# Main
# ============================================================
def main():
    print(f"📊 تحميل بيانات {SYMBOL} على {TIMEFRAME}...")
    df = load_full_data(SYMBOL, TIMEFRAME, DB_PATH)
    print(f"✅ عدد الشموع: {len(df)}")

    if len(df) < LOOKBACK_BARS + FORWARD_BARS + 20:
        print("⚠️  البيانات غير كافية.")
        return

    print(f"🔍 تشغيل Backtest (نافذة {LOOKBACK_BARS}، تقدّم {STEP})...")
    print(f"   MIN_SCORE = {MIN_SCORE} | R:R = {RR_RATIO}")
    print(f"   SL = {ATR_SL_MULT} × ATR | FORWARD_BARS = {FORWARD_BARS}")
    print(f"   COOLDOWN = {COOLDOWN_BARS} شموع بين الصفقات")
    print()

    trades = run_backtest(df)
    if not trades:
        print("⚠️  لم تُسجَّل أي تداولات.")
        return

    stats = analyze_results(trades)
    print_results(stats, trades)


if __name__ == "__main__":
    main()