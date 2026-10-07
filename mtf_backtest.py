"""
mtf_backtest.py
Backtest متعدد الأطر الزمنية: H4 Bias → H1 BOS → M15 Zone → Retest → Confirmation
"""

import json
import sqlite3
from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd

from core.config import DB_PATH, SYMBOL_DB
from smc.engine import analyze


# ============================================================
# SETTINGS
# ============================================================
SYMBOL = SYMBOL_DB

H4_TABLE = "XAUUSD_H4"
H1_TABLE = "XAUUSD_H1"
M15_TABLE = "XAUUSD_M15"

RR = 2.0

ATR_PERIOD = 14
H1_ATR_MULTIPLIER = 1.0
M15_ZONE_BUFFER_ATR = 0.20

H4_ANALYSIS_BARS = 250
H1_ANALYSIS_BARS = 250
M15_ANALYSIS_BARS = 500

BOS_RECENT_HOURS = 30

MAX_RETEST_M15_BARS = 80
MAX_HOLD_M15_BARS = 96

COOLDOWN_HOURS = 12

OUTPUT_DIR = Path("data")
JSON_OUTPUT = OUTPUT_DIR / "mtf_backtest_results.json"
CSV_OUTPUT = OUTPUT_DIR / "mtf_backtest_trades.csv"


# ============================================================
# DATA LOADING
# ============================================================
def load_data():
    print("📊 تحميل البيانات (H4, H1, M15)...")

    conn = sqlite3.connect(DB_PATH)
    try:
        h4 = pd.read_sql(f"SELECT * FROM {H4_TABLE} ORDER BY timestamp ASC", conn)
        h1 = pd.read_sql(f"SELECT * FROM {H1_TABLE} ORDER BY timestamp ASC", conn)
        m15 = pd.read_sql(f"SELECT * FROM {M15_TABLE} ORDER BY timestamp ASC", conn)
    finally:
        conn.close()

    for df in [h4, h1, m15]:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df.dropna(subset=["timestamp", "open", "high", "low", "close"], inplace=True)
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)

    print(f"  H4  : {len(h4)} شمعة")
    print(f"  H1  : {len(h1)} شمعة")
    print(f"  M15 : {len(m15)} شمعة")

    return h4, h1, m15


# ============================================================
# ATR
# ============================================================
def add_atr(df, period=14):
    out = df.copy()
    previous_close = out["close"].shift(1)
    tr1 = out["high"] - out["low"]
    tr2 = (out["high"] - previous_close).abs()
    tr3 = (out["low"] - previous_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["atr"] = true_range.rolling(period).mean()
    return out


# ============================================================
# SAFE ANALYZE
# ============================================================
def run_analysis(df):
    if df is None or len(df) < 30:
        return None
    try:
        result = analyze(df.copy())
        if not isinstance(result, pd.DataFrame):
            return None
        return result
    except Exception as exc:
        print(f"⚠️ خطأ في analyze(): {exc}")
        return None


# ============================================================
# NORMALIZE DIRECTION
# ============================================================
def normalize_direction(value):
    if value is None:
        return None
    value = str(value).strip().lower()
    if value in ["bullish", "bull", "buy", "long", "up"]:
        return "bullish"
    if value in ["bearish", "bear", "sell", "short", "down"]:
        return "bearish"
    return None


# ============================================================
# GET H4 BIAS
# ============================================================
def get_h4_bias(h4_df, timestamp):
    available = h4_df[h4_df["timestamp"] <= timestamp].copy()
    if len(available) < 60:
        return None
    available = available.tail(H4_ANALYSIS_BARS)
    analyzed = run_analysis(available)
    if analyzed is None:
        return None
    last = analyzed.iloc[-1]
    return normalize_direction(last.get("trend", None))


# ============================================================
# GET H1 BOS EVENTS
# ============================================================
def get_h1_bos_events(h1_df, timestamp):
    available = h1_df[h1_df["timestamp"] <= timestamp].copy()
    if len(available) < 60:
        return []
    available = available.tail(H1_ANALYSIS_BARS)
    analyzed = run_analysis(available)
    if analyzed is None:
        return []

    events = []
    for _, row in analyzed.iterrows():
        if not bool(row.get("bos", False)):
            continue
        direction = normalize_direction(row.get("break_direction", None))
        if direction is None:
            direction = normalize_direction(row.get("trend", None))
        if direction is None:
            continue
        events.append({
            "timestamp": pd.Timestamp(row["timestamp"]),
            "direction": direction,
            "level": float(row["bos_choch_level"]) if pd.notna(row.get("bos_choch_level", np.nan)) else None,
        })
    return events


# ============================================================
# FIND MATCHING BOS
# ============================================================
def find_matching_bos(h1_df, current_time, bias):
    events = get_h1_bos_events(h1_df, current_time)
    if not events:
        return None
    cutoff = current_time - timedelta(hours=BOS_RECENT_HOURS)
    candidates = [
        e for e in events
        if e["timestamp"] >= cutoff and e["timestamp"] <= current_time and e["direction"] == bias
    ]
    if not candidates:
        return None
    return candidates[-1]


# ============================================================
# EXTRACT M15 ZONES
# ============================================================
def extract_new_m15_zones(m15_df, bos_time, current_time, direction):
    available = m15_df[
        (m15_df["timestamp"] >= bos_time) & (m15_df["timestamp"] <= current_time)
    ].copy()
    if len(available) < 30:
        return []
    available = available.tail(M15_ANALYSIS_BARS)
    analyzed = run_analysis(available)
    if analyzed is None:
        return []

    zones = []
    for _, row in analyzed.iterrows():
        timestamp = pd.Timestamp(row["timestamp"])
        if timestamp < bos_time or timestamp > current_time:
            continue

        if direction == "bullish":
            if bool(row.get("bullish_ob", False)) and pd.notna(row.get("ob_high", np.nan)) and pd.notna(row.get("ob_low", np.nan)):
                zones.append({
                    "type": "bullish_ob",
                    "timestamp": timestamp,
                    "high": float(row["ob_high"]),
                    "low": float(row["ob_low"]),
                })
        else:
            if bool(row.get("bearish_ob", False)) and pd.notna(row.get("ob_high", np.nan)) and pd.notna(row.get("ob_low", np.nan)):
                zones.append({
                    "type": "bearish_ob",
                    "timestamp": timestamp,
                    "high": float(row["ob_high"]),
                    "low": float(row["ob_low"]),
                })

        # FVG
        if direction == "bullish" and bool(row.get("bullish_fvg", False)):
            if pd.notna(row.get("fvg_top", np.nan)) and pd.notna(row.get("fvg_bottom", np.nan)):
                zones.append({
                    "type": "bullish_fvg",
                    "timestamp": timestamp,
                    "high": float(row["fvg_top"]),
                    "low": float(row["fvg_bottom"]),
                })
        elif direction == "bearish" and bool(row.get("bearish_fvg", False)):
            if pd.notna(row.get("fvg_top", np.nan)) and pd.notna(row.get("fvg_bottom", np.nan)):
                zones.append({
                    "type": "bearish_fvg",
                    "timestamp": timestamp,
                    "high": float(row["fvg_top"]),
                    "low": float(row["fvg_bottom"]),
                })

    return zones


# ============================================================
# CANDLE CONFIRMATION
# ============================================================
def bullish_confirmation(previous, current):
    po, pc = float(previous["open"]), float(previous["close"])
    co, cc = float(current["open"]), float(current["close"])
    ch, cl = float(current["high"]), float(current["low"])

    body = abs(cc - co)
    candle_range = ch - cl
    if candle_range <= 0:
        return False, None

    lower_wick = min(co, cc) - cl
    upper_wick = ch - max(co, cc)

    # Bullish Engulfing
    if pc < po and cc > co and co <= pc and cc >= po:
        return True, "Bullish Engulfing"

    # Bullish Pin Bar
    if cc > co and lower_wick >= body * 2 and lower_wick > upper_wick:
        return True, "Bullish Pin Bar"

    return False, None


def bearish_confirmation(previous, current):
    po, pc = float(previous["open"]), float(previous["close"])
    co, cc = float(current["open"]), float(current["close"])
    ch, cl = float(current["high"]), float(current["low"])

    body = abs(cc - co)
    candle_range = ch - cl
    if candle_range <= 0:
        return False, None

    upper_wick = ch - max(co, cc)
    lower_wick = min(co, cc) - cl

    # Bearish Engulfing
    if pc > po and cc < co and co >= pc and cc <= po:
        return True, "Bearish Engulfing"

    # Bearish Pin Bar
    if cc < co and upper_wick >= body * 2 and upper_wick > lower_wick:
        return True, "Bearish Pin Bar"

    return False, None


# ============================================================
# FIND RETEST
# ============================================================
def find_retest(m15_df, zone, direction, bos_time):
    data = m15_df[m15_df["timestamp"] >= zone["timestamp"]].copy()
    data = data[data["timestamp"] > bos_time].copy()
    data = data.head(MAX_RETEST_M15_BARS)

    if len(data) < 2:
        return None

    left_zone = False
    previous = None

    for _, row in data.iterrows():
        high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
        zone_high, zone_low = float(zone["high"]), float(zone["low"])

        if direction == "bullish":
            if close > zone_high:
                left_zone = True
        else:
            if close < zone_low:
                left_zone = True

        if not left_zone:
            previous = row
            continue

        touched = low <= zone_high and high >= zone_low
        if not touched:
            previous = row
            continue

        if previous is None:
            previous = row
            continue

        if direction == "bullish":
            confirmed, confirmation_type = bullish_confirmation(previous, row)
        else:
            confirmed, confirmation_type = bearish_confirmation(previous, row)

        if not confirmed:
            previous = row
            continue

        return {
            "timestamp": pd.Timestamp(row["timestamp"]),
            "entry": close,
            "confirmation": confirmation_type,
        }

    return None


# ============================================================
# GET ATR AT TIME
# ============================================================
def get_atr_at_time(atr_df, timestamp):
    available = atr_df[atr_df["timestamp"] <= timestamp]
    if available.empty:
        return None
    value = available.iloc[-1]["atr"]
    if pd.isna(value):
        return None
    return float(value)


# ============================================================
# CALCULATE LEVELS
# ============================================================
def calculate_levels(direction, entry, zone, h1_atr, m15_atr):
    if h1_atr is None:
        return None
    if m15_atr is None:
        m15_atr = 0.0

    buffer = m15_atr * M15_ZONE_BUFFER_ATR
    entry = float(entry)
    zone_low, zone_high = float(zone["low"]), float(zone["high"])

    if direction == "bullish":
        zone_sl = zone_low - buffer
        atr_sl = entry - (h1_atr * H1_ATR_MULTIPLIER)
        sl = min(zone_sl, atr_sl)
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + risk * RR
    else:
        zone_sl = zone_high + buffer
        atr_sl = entry + (h1_atr * H1_ATR_MULTIPLIER)
        sl = max(zone_sl, atr_sl)
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - risk * RR

    return {"entry": entry, "sl": float(sl), "tp": float(tp), "risk": float(risk)}


# ============================================================
# MANAGE TRADE
# ============================================================
def manage_trade(m15_df, entry_time, direction, entry, sl, tp):
    future = m15_df[m15_df["timestamp"] > entry_time].copy()
    future = future.head(MAX_HOLD_M15_BARS)

    if future.empty:
        return {
            "result": "timeout",
            "exit_time": entry_time,
            "exit_price": entry,
            "r": 0.0,
            "mfe_r": 0.0,
            "mae_r": 0.0,
            "ambiguous": False,
        }

    risk = abs(entry - sl)
    mfe = 0.0
    mae = 0.0

    for _, row in future.iterrows():
        high, low = float(row["high"]), float(row["low"])

        if direction == "bullish":
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

        mfe_r = mfe / risk if risk > 0 else 0
        mae_r = mae / risk if risk > 0 else 0

        if hit_sl and hit_tp:
            return {
                "result": "loss",
                "exit_time": row["timestamp"],
                "exit_price": sl,
                "r": -1.0,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
                "ambiguous": True,
            }

        if hit_sl:
            return {
                "result": "loss",
                "exit_time": row["timestamp"],
                "exit_price": sl,
                "r": -1.0,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
                "ambiguous": False,
            }

        if hit_tp:
            return {
                "result": "win",
                "exit_time": row["timestamp"],
                "exit_price": tp,
                "r": RR,
                "mfe_r": mfe_r,
                "mae_r": mae_r,
                "ambiguous": False,
            }

    last = future.iloc[-1]
    last_close = float(last["close"])
    r = (last_close - entry) / risk if direction == "bullish" else (entry - last_close) / risk

    return {
        "result": "timeout",
        "exit_time": last["timestamp"],
        "exit_price": last_close,
        "r": float(r),
        "mfe_r": mfe / risk if risk > 0 else 0,
        "mae_r": mae / risk if risk > 0 else 0,
        "ambiguous": False,
    }


# ============================================================
# RUN BACKTEST
# ============================================================
def run_backtest(h4_df, h1_df, m15_df):
    print()
    print("🔍 تشغيل MTF Backtest...")
    print("   H4 → H1 BOS → M15 Zone → Retest → Confirmation")
    print(f"   R:R = {RR}")
    print(f"   BOS recent = {BOS_RECENT_HOURS} hours")
    print(f"   M15 max hold = {MAX_HOLD_M15_BARS} bars")

    h1_atr_df = add_atr(h1_df, ATR_PERIOD)
    m15_atr_df = add_atr(m15_df, ATR_PERIOD)

    trades = []
    funnel = {
        "h1_checked": 0,
        "h4_bias_found": 0,
        "bos_found": 0,
        "bos_matches_bias": 0,
        "zone_found": 0,
        "retest_found": 0,
        "confirmation_found": 0,
        "trade_created": 0,
        "cooldown_skipped": 0,
        "invalid_levels": 0,
    }

    last_entry_time = None

    for i in range(80, len(h1_df)):
        current_time = pd.Timestamp(h1_df.iloc[i]["timestamp"])
        funnel["h1_checked"] += 1

        # Cooldown
        if last_entry_time is not None:
            elapsed_hours = (current_time - last_entry_time).total_seconds() / 3600
            if elapsed_hours < COOLDOWN_HOURS:
                funnel["cooldown_skipped"] += 1
                continue

        # H4 Bias
        bias = get_h4_bias(h4_df, current_time)
        if bias is None:
            continue
        funnel["h4_bias_found"] += 1

        # H1 BOS
        bos = find_matching_bos(h1_df, current_time, bias)
        if bos is None:
            continue
        funnel["bos_found"] += 1
        funnel["bos_matches_bias"] += 1

        bos_time = bos["timestamp"]

        # M15 Zones
        zones = extract_new_m15_zones(m15_df, bos_time, current_time, bias)
        if not zones:
            zone_data = m15_df[m15_df["timestamp"] >= bos_time].head(MAX_RETEST_M15_BARS)
            if not zone_data.empty:
                zones = extract_new_m15_zones(m15_df, bos_time, zone_data.iloc[-1]["timestamp"], bias)
        if not zones:
            continue
        funnel["zone_found"] += 1

        zones = sorted(zones, key=lambda x: x["timestamp"], reverse=True)

        selected_retest = None
        selected_zone = None

        for zone in zones:
            retest = find_retest(m15_df, zone, bias, bos_time)
            if retest is None:
                continue
            selected_zone = zone
            selected_retest = retest
            break

        if selected_retest is None:
            continue
        funnel["retest_found"] += 1
        funnel["confirmation_found"] += 1

        entry_time = selected_retest["timestamp"]
        entry = selected_retest["entry"]

        h1_atr = get_atr_at_time(h1_atr_df, entry_time)
        m15_atr = get_atr_at_time(m15_atr_df, entry_time)

        levels = calculate_levels(bias, entry, selected_zone, h1_atr, m15_atr)
        if levels is None:
            funnel["invalid_levels"] += 1
            continue

        sl, tp, risk = levels["sl"], levels["tp"], levels["risk"]

        management = manage_trade(m15_df, entry_time, bias, entry, sl, tp)

        trade = {
            "entry_time": str(entry_time),
            "exit_time": str(management["exit_time"]),
            "direction": bias,
            "h4_bias": bias,
            "bos_time": str(bos_time),
            "bos_level": bos["level"],
            "zone_time": str(selected_zone["timestamp"]),
            "zone_type": selected_zone["type"],
            "zone_high": selected_zone["high"],
            "zone_low": selected_zone["low"],
            "confirmation": selected_retest["confirmation"],
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "risk": risk,
            "result": management["result"],
            "r": management["r"],
            "mfe_r": management["mfe_r"],
            "mae_r": management["mae_r"],
            "ambiguous_bar": management["ambiguous"],
        }

        trades.append(trade)
        funnel["trade_created"] += 1
        last_entry_time = entry_time

    return trades, funnel


# ============================================================
# PERFORMANCE
# ============================================================
def calculate_performance(trades):
    if not trades:
        return {
            "trades": 0, "wins": 0, "losses": 0, "timeouts": 0,
            "win_rate": 0.0, "profit_factor": 0.0, "total_r": 0.0,
            "expectancy_r": 0.0, "max_drawdown_r": 0.0,
            "avg_win_r": 0.0, "avg_loss_r": 0.0, "avg_timeout_r": 0.0,
            "avg_mfe_r": 0.0, "avg_mae_r": 0.0,
            "max_win_streak": 0, "max_loss_streak": 0,
        }

    df = pd.DataFrame(trades)
    wins = df[df["result"] == "win"]
    losses = df[df["result"] == "loss"]
    timeouts = df[df["result"] == "timeout"]

    gross_profit = float(wins["r"].sum())
    gross_loss = abs(float(losses["r"].sum()))

    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    total_r = float(df["r"].sum())
    expectancy_r = float(df["r"].mean())
    win_rate = len(wins) / len(df) * 100

    equity = df["r"].cumsum()
    peak = equity.cummax()
    drawdown = equity - peak
    max_drawdown_r = abs(float(drawdown.min()))

    max_win_streak, max_loss_streak = 0, 0
    current_win, current_loss = 0, 0
    for result in df["result"]:
        if result == "win":
            current_win += 1
            current_loss = 0
            max_win_streak = max(max_win_streak, current_win)
        elif result == "loss":
            current_loss += 1
            current_win = 0
            max_loss_streak = max(max_loss_streak, current_loss)
        else:
            current_win, current_loss = 0, 0

    return {
        "trades": len(df),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(timeouts),
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "total_r": total_r,
        "expectancy_r": expectancy_r,
        "max_drawdown_r": max_drawdown_r,
        "avg_win_r": float(wins["r"].mean()) if not wins.empty else 0.0,
        "avg_loss_r": float(losses["r"].mean()) if not losses.empty else 0.0,
        "avg_timeout_r": float(timeouts["r"].mean()) if not timeouts.empty else 0.0,
        "avg_mfe_r": float(df["mfe_r"].mean()),
        "avg_mae_r": float(df["mae_r"].mean()),
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
    }


# ============================================================
# PRINT REPORT
# ============================================================
def print_report(trades, funnel, performance):
    print()
    print("=" * 68)
    print("📊 نتائج Multi-Timeframe Backtest — XAUUSD")
    print("   H4 Bias → H1 BOS → M15 Zone → Retest → Confirmation")
    print("=" * 68)

    print()
    print("🔎 SIGNAL FUNNEL")
    print(f"  H1 checked             : {funnel['h1_checked']}")
    print(f"  H4 bias found          : {funnel['h4_bias_found']}")
    print(f"  H1 BOS found           : {funnel['bos_found']}")
    print(f"  BOS matches H4 bias    : {funnel['bos_matches_bias']}")
    print(f"  M15 zone found         : {funnel['zone_found']}")
    print(f"  M15 retest found       : {funnel['retest_found']}")
    print(f"  M15 confirmation       : {funnel['confirmation_found']}")
    print(f"  Invalid levels         : {funnel['invalid_levels']}")
    print(f"  Trades created         : {funnel['trade_created']}")
    print(f"  Cooldown skipped       : {funnel['cooldown_skipped']}")

    print()
    print("📈 PERFORMANCE")
    print(f"  عدد التداولات          : {performance['trades']}")
    print(f"  ✅ رابحة               : {performance['wins']}")
    print(f"  ❌ خاسرة               : {performance['losses']}")
    print(f"  ⏳ Timeout             : {performance['timeouts']}")
    print(f"  🎯 Win Rate            : {performance['win_rate']:.2f}%")

    pf = performance["profit_factor"]
    pf_text = "∞" if np.isinf(pf) else f"{pf:.3f}"
    print(f"  ⚖️ Profit Factor       : {pf_text}")
    print(f"  📊 Total R             : {performance['total_r']:.3f}R")
    print(f"  📐 Expectancy          : {performance['expectancy_r']:.3f}R")
    print(f"  📉 Max Drawdown        : {performance['max_drawdown_r']:.3f}R")
    print(f"  📈 Average Win         : {performance['avg_win_r']:.3f}R")
    print(f"  📉 Average Loss        : {performance['avg_loss_r']:.3f}R")
    print(f"  ⏳ Average Timeout     : {performance['avg_timeout_r']:.3f}R")
    print(f"  🚀 Average MFE         : {performance['avg_mfe_r']:.3f}R")
    print(f"  ⚠️ Average MAE         : {performance['avg_mae_r']:.3f}R")
    print(f"  🔥 Max Win Streak      : {performance['max_win_streak']}")
    print(f"  🧊 Max Loss Streak     : {performance['max_loss_streak']}")

    print()
    print("📋 آخر 10 تداولات")
    for trade in trades[-10:]:
        icon = "✅" if trade["result"] == "win" else ("❌" if trade["result"] == "loss" else "⏳")
        print(f"  {icon} {trade['entry_time']} | {trade['direction'].upper()} | "
              f"Entry: {trade['entry']:.2f} | SL: {trade['sl']:.2f} | TP: {trade['tp']:.2f} | R: {trade['r']:.3f}")
        print(f"      ↳ Zone:{trade['zone_type']} | M15:{trade['confirmation']} | "
              f"MFE:{trade['mfe_r']:.2f}R | MAE:{trade['mae_r']:.2f}R")

    print("=" * 68)


# ============================================================
# SAVE RESULTS
# ============================================================
def save_results(trades, funnel, performance):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "symbol": SYMBOL,
        "settings": {
            "rr": RR,
            "atr_period": ATR_PERIOD,
            "h1_atr_multiplier": H1_ATR_MULTIPLIER,
            "m15_zone_buffer_atr": M15_ZONE_BUFFER_ATR,
            "h4_analysis_bars": H4_ANALYSIS_BARS,
            "h1_analysis_bars": H1_ANALYSIS_BARS,
            "m15_analysis_bars": M15_ANALYSIS_BARS,
            "bos_recent_hours": BOS_RECENT_HOURS,
            "max_retest_m15_bars": MAX_RETEST_M15_BARS,
            "max_hold_m15_bars": MAX_HOLD_M15_BARS,
            "cooldown_hours": COOLDOWN_HOURS,
        },
        "funnel": funnel,
        "performance": performance,
        "trades": trades,
    }

    with open(JSON_OUTPUT, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2, default=str)

    if trades:
        pd.DataFrame(trades).to_csv(CSV_OUTPUT, index=False, encoding="utf-8-sig")

    print()
    print(f"💾 تم حفظ النتائج في:")
    print(f"   JSON: {JSON_OUTPUT}")
    if trades:
        print(f"   CSV : {CSV_OUTPUT}")


# ============================================================
# MAIN
# ============================================================
def main():
    h4_df, h1_df, m15_df = load_data()
    trades, funnel = run_backtest(h4_df, h1_df, m15_df)
    performance = calculate_performance(trades)
    print_report(trades, funnel, performance)
    save_results(trades, funnel, performance)


if __name__ == "__main__":
    main()