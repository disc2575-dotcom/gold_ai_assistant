"""
core/scheduler.py
جدولة تحديث البيانات والإشارات تلقائياً.
- الأطر المفعلة: D1 + H4.
- إشعارات عبر ntfy.sh.
- فلتر أخبار (Google News + Groq AI).
- ترجمة العناوين إلى العربية.
- حساب TPs متسلسل (TP3 > TP2 > TP1).
"""

import time
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np
import requests

from core.config import (
    DB_PATH, SYMBOL_TWELVEDATA, SYMBOL_DB,
    TIMEFRAMES, BARS_PER_TIMEFRAME,
    TIMEFRAME_SETTINGS,
)
from core.data_updater import fetch_latest, update_table
from core.news_fetcher import fetch_latest_news
from smc.engine import analyze


# ============================================================
# إعدادات
# ============================================================
SIGNAL_PATH = Path("data/signal.json")
UPDATE_INTERVAL_MINUTES = 15

ACTIVE_TIMEFRAMES = [tf for tf, s in TIMEFRAME_SETTINGS.items() if s.get("enabled", True)]

TIMEFRAME_WEIGHTS = {
    "D1": 3.0, "H4": 3.0, "H1": 2.0,
    "M30": 2.0, "M15": 1.0, "M5": 1.0,
}

MIN_CONFIDENCE = 60
LOOKBACK_BARS = 300

CONFIDENCE_MULTIPLIER = 80
CONFIDENCE_CAP = 90

NTFY_TOPIC = "Bot"
NTFY_SERVER = "https://ntfy.sh"


# ============================================================
# الحالة
# ============================================================
_scheduler_running = False
_scheduler_thread = None
_stop_event = None


def is_scheduler_running() -> bool:
    return _scheduler_running


def log(message: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}")


# ============================================================
# تحديث البيانات
# ============================================================
def update_data():
    log("🔄 تحديث البيانات...")
    for tf in TIMEFRAMES:
        try:
            new_df = fetch_latest(tf, bars=10)
            new_rows, total = update_table(tf, new_df)
            log(f"   ✅ {tf}: {new_rows} صف جديد | المجموع: {total}")
        except Exception as e:
            log(f"   ⚠️ {tf}: {e}")


# ============================================================
# تحميل آخر N شمعة
# ============================================================
def load_latest_bars(timeframe: str, bars: int = LOOKBACK_BARS) -> pd.DataFrame:
    table = f"{SYMBOL_DB}_{timeframe}"
    conn = sqlite3.connect(str(DB_PATH))
    try:
        df = pd.read_sql(
            f'SELECT * FROM ('
            f'  SELECT * FROM "{table}" ORDER BY timestamp DESC LIMIT {bars}'
            f') ORDER BY timestamp ASC',
            conn, parse_dates=["timestamp"],
        )
    finally:
        conn.close()
    return df.reset_index(drop=True)


# ============================================================
# تحليل إطار واحد
# ============================================================
def analyze_single_timeframe(timeframe: str) -> dict:
    try:
        df = load_latest_bars(timeframe, LOOKBACK_BARS)
        if len(df) < 30:
            return {"trend": "neutral", "price": None}

        analyzed = analyze(df)
        if analyzed is None or analyzed.empty:
            return {"trend": "neutral", "price": None}

        last = analyzed.iloc[-1]
        return {
            "trend": last.get("trend", "neutral"),
            "price": float(last["close"]),
            "weight": TIMEFRAME_WEIGHTS.get(timeframe, 1.0),
            "df": analyzed,
        }
    except Exception as e:
        log(f"   ⚠️ خطأ في {timeframe}: {e}")
        return {"trend": "neutral", "price": None}


# ============================================================
# المستويات: الدعم والمقاومة
# ============================================================
def find_support_resistance(df: pd.DataFrame, current_price: float) -> dict:
    if df is None or df.empty:
        return {"nearest_support": None, "nearest_resistance": None}

    highs = []
    lows = []

    if "swing_high" in df.columns:
        for _, row in df[df["swing_high"] == True].iterrows():
            highs.append(float(row["high"]))
    if "swing_low" in df.columns:
        for _, row in df[df["swing_low"] == True].iterrows():
            lows.append(float(row["low"]))

    resistances = [h for h in highs if h > current_price]
    supports = [l for l in lows if l < current_price]

    nearest_resistance = min(resistances) if resistances else None
    nearest_support = max(supports) if supports else None

    return {
        "nearest_support": round(nearest_support, 2) if nearest_support else None,
        "nearest_resistance": round(nearest_resistance, 2) if nearest_resistance else None,
    }


# ============================================================
# استخراج مناطق OB و FVG
# ============================================================
def extract_ob_fvg(df: pd.DataFrame, current_price: float, limit: int = 10) -> list:
    if df is None or df.empty:
        return []

    zones = []
    last_rows = df.tail(200)

    for _, row in last_rows.iterrows():
        ts = str(row.get("timestamp", ""))

        if row.get("bullish_ob", False):
            zones.append({
                "type": "bullish_ob",
                "label": "طلب (Bullish OB)",
                "top": round(float(row["ob_high"]), 2),
                "bottom": round(float(row["ob_low"]), 2),
                "timestamp": ts,
            })

        if row.get("bearish_ob", False):
            zones.append({
                "type": "bearish_ob",
                "label": "عرض (Bearish OB)",
                "top": round(float(row["ob_high"]), 2),
                "bottom": round(float(row["ob_low"]), 2),
                "timestamp": ts,
            })

        if row.get("bullish_fvg", False):
            zones.append({
                "type": "bullish_fvg",
                "label": "طلب (Bullish FVG)",
                "top": round(float(row["fvg_top"]), 2),
                "bottom": round(float(row["fvg_bottom"]), 2),
                "timestamp": ts,
            })

        if row.get("bearish_fvg", False):
            zones.append({
                "type": "bearish_fvg",
                "label": "عرض (Bearish FVG)",
                "top": round(float(row["fvg_top"]), 2),
                "bottom": round(float(row["fvg_bottom"]), 2),
                "timestamp": ts,
            })

    return zones[-limit:]


# ============================================================
# تحليل الأخبار + الترجمة
# ============================================================
def get_news_analysis() -> dict:
    """جلب الأخبار وتحليلها باستخدام AI + ترجمة إلى العربية."""
    log("📰 جلب الأخبار...")
    news = fetch_latest_news()

    if not news:
        log("   ⚠️ لم يتم جلب أخبار")
        return {
            "sentiment": "neutral",
            "score": 0,
            "reasoning": "لا توجد أخبار.",
            "key_topics": [],
            "headlines": [],
            "headlines_en": [],
            "sources": [],
        }

    log(f"   ✅ عدد الأخبار: {len(news)}")
    log("   🤖 تحليل المشاعر بـ AI...")

    from ai.analyzer import analyze_news_sentiment, translate_headlines
    analysis = analyze_news_sentiment(news)

    log(f"   🎯 المشاعر: {analysis.get('sentiment', 'N/A')} (score: {analysis.get('score', 0)})")

    # العناوين بالإنجليزية
    headlines_en = [n["title"] for n in news[:8]]

    log("   🌐 ترجمة العناوين إلى العربية...")
    headlines_ar = translate_headlines(headlines_en)

    analysis["headlines"] = headlines_ar          # عربي
    analysis["headlines_en"] = headlines_en       # إنجليزي
    analysis["sources"] = [n["source"] for n in news[:8]]

    return analysis


# ============================================================
# توليد الإشارة
# ============================================================
def generate_signal():
    log("🎯 تحليل الأطر الزمنية...")

    timeframes_data = {}
    total_score = 0.0
    total_weight = 0.0

    for tf in ACTIVE_TIMEFRAMES:
        data = analyze_single_timeframe(tf)
        if data["trend"] != "neutral":
            timeframes_data[tf] = data
            weight = data["weight"]
            score = weight if data["trend"] == "bullish" else -weight
            total_score += score
            total_weight += weight

    if total_weight == 0:
        log("⏸️ لا توجد بيانات كافية")
        return None

    weighted_score = total_score / total_weight
    if weighted_score > 0.2:
        bias = "bullish"
    elif weighted_score < -0.2:
        bias = "bearish"
    else:
        bias = "neutral"

    confidence = min(abs(weighted_score) * CONFIDENCE_MULTIPLIER, CONFIDENCE_CAP)

    current_price = None
    for tf in ["D1", "H4", "H1", "M30"]:
        if tf in timeframes_data and timeframes_data[tf]["price"]:
            current_price = timeframes_data[tf]["price"]
            break

    signal = "WAIT"
    if confidence >= MIN_CONFIDENCE and bias != "neutral":
        signal = bias.upper()

    # ========================================================
    # المستويات
    # ========================================================
    levels_data = {"current_price": round(current_price, 2) if current_price else None}
    zones = []

    for tf_key in ["H1", "H4", "D1"]:
        if tf_key in timeframes_data and "df" in timeframes_data[tf_key]:
            df = timeframes_data[tf_key]["df"]
            sr = find_support_resistance(df, current_price)
            if sr["nearest_support"]:
                levels_data["nearest_support"] = sr["nearest_support"]
            if sr["nearest_resistance"]:
                levels_data["nearest_resistance"] = sr["nearest_resistance"]
            if not zones:
                zones = extract_ob_fvg(df, current_price)
            break

    # ========================================================
    # خطة الدخول (مع TP متسلسل)
    # ========================================================
    entry = None
    stop_loss = None
    targets = []

    if bias == "bullish" and levels_data.get("nearest_support"):
        entry = round(current_price, 2)
        stop_loss = round(levels_data["nearest_support"] - 5, 2)
        risk = entry - stop_loss

        if risk > 0:
            tp1 = round(entry + risk * 1, 2)
            tp2 = round(entry + risk * 2, 2)
            tp3 = round(entry + risk * 3, 2)

            if tp3 <= tp2:
                tp3 = round(tp2 + risk, 2)

            if tp2 <= tp1:
                tp2 = round(tp1 + risk, 2)
                tp3 = round(tp2 + risk, 2)

            targets = [tp1, tp2, tp3]

    elif bias == "bearish" and levels_data.get("nearest_resistance"):
        entry = round(current_price, 2)
        stop_loss = round(levels_data["nearest_resistance"] + 5, 2)
        risk = stop_loss - entry

        if risk > 0:
            tp1 = round(entry - risk * 1, 2)
            tp2 = round(entry - risk * 2, 2)
            tp3 = round(entry - risk * 3, 2)

            if tp3 >= tp2:
                tp3 = round(tp2 - risk, 2)

            if tp2 >= tp1:
                tp2 = round(tp1 - risk, 2)
                tp3 = round(tp2 - risk, 2)

            targets = [tp1, tp2, tp3]

    if entry and targets:
        levels_data["entry"] = entry
        levels_data["stop_loss"] = stop_loss
        levels_data["targets"] = targets

    # ========================================================
    # السيناريوهات
    # ========================================================
    scenarios = []
    if levels_data.get("nearest_resistance"):
        r = levels_data["nearest_resistance"]
        scenarios.append({
            "condition": f"إذا كسر السعر {r} صعوداً",
            "action": "BUY",
            "entry": r,
            "stop_loss": round(r - 20, 2),
            "targets": [round(r + 20, 2), round(r + 40, 2), round(r + 60, 2)],
        })
    if levels_data.get("nearest_support"):
        s = levels_data["nearest_support"]
        scenarios.append({
            "condition": f"إذا كسر السعر {s} هبوطاً",
            "action": "SELL",
            "entry": s,
            "stop_loss": round(s + 20, 2),
            "targets": [round(s - 20, 2), round(s - 40, 2), round(s - 60, 2)],
        })

    # ========================================================
    # تحليل الأخبار
    # ========================================================
    news_analysis = get_news_analysis()

    # ========================================================
    # الأسباب
    # ========================================================
    reasoning = [f"الاتجاه المرجّح: {bias} (score: {weighted_score:.2f})"]
    warnings = []
    if confidence < MIN_CONFIDENCE:
        warnings.append(f"ثقة منخفضة ({confidence:.1f}%)")

    # تعديل الإشارة بناءً على الأخبار
    news_sentiment = news_analysis.get("sentiment", "neutral")
    news_score = news_analysis.get("score", 0)

    if bias == "bullish" and news_sentiment == "bearish" and news_score <= -3:
        warnings.append(f"⚠️ أخبار سلبية (score: {news_score}) قد تعارض الاتجاه الصاعد")
        confidence = max(confidence - 15, 0)
        if confidence < MIN_CONFIDENCE:
            signal = "WAIT"
    elif bias == "bearish" and news_sentiment == "bullish" and news_score >= 3:
        warnings.append(f"⚠️ أخبار إيجابية (score: {news_score}) قد تعارض الاتجاه الهابط")
        confidence = max(confidence - 15, 0)
        if confidence < MIN_CONFIDENCE:
            signal = "WAIT"
    elif news_sentiment == "bullish" and bias == "bullish":
        confidence = min(confidence + 10, CONFIDENCE_CAP)
        reasoning.append(f"📰 أخبار إيجابية (score: {news_score}) تدعم الاتجاه")
    elif news_sentiment == "bearish" and bias == "bearish":
        confidence = min(confidence + 10, CONFIDENCE_CAP)
        reasoning.append(f"📰 أخبار سلبية (score: {news_score}) تدعم الاتجاه")

    # ========================================================
    # البناء النهائي
    # ========================================================
    final_signal = {
        "signal": signal,
        "confidence": round(confidence, 1),
        "bias": bias,
        "bias_score": round(weighted_score, 3),
        "consensus_ratio": round(abs(weighted_score), 3),
        "current_price": round(current_price, 2) if current_price else None,
        "reasoning": reasoning,
        "warnings": warnings,
        "levels": levels_data,
        "zones": zones,
        "conditional_scenarios": scenarios,
        "timeframes": {
            tf: {
                "trend": d["trend"],
                "weight": d["weight"],
                "last_close": d["price"],
            }
            for tf, d in timeframes_data.items()
        },
        "news_analysis": news_analysis,
        "updated_at": datetime.now().isoformat(),
    }

    SIGNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SIGNAL_PATH, "w", encoding="utf-8") as f:
        json.dump(final_signal, f, indent=2, ensure_ascii=False, default=str)

    log(f"✅ الإشارة: {signal} | الثقة: {confidence:.1f}% | السعر: {current_price}")
    return final_signal


# ============================================================
# إرسال ntfy
# ============================================================
def send_ntfy(signal: dict) -> bool:
    if not signal or not NTFY_TOPIC:
        return False

    lines = [
        f"🎯 الإشارة: {signal.get('signal', 'N/A')}",
        f"📈 الاتجاه: {signal.get('bias', 'N/A').upper()}",
        f"🎚️ الثقة: {signal.get('confidence', 0)}%",
        f"💰 السعر: {signal.get('current_price', 'N/A')}",
    ]

    news = signal.get("news_analysis", {})
    if news:
        lines.append(f"📰 الأخبار: {news.get('sentiment', 'N/A')} ({news.get('score', 0)})")

    message = "\n".join(lines)
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"

    try:
        r = requests.post(
            url,
            data=message.encode("utf-8"),
            headers={
                "Title": f"XAUUSD: {signal.get('signal', 'N/A')}",
                "Priority": "high",
                "Tags": "chart_with_upwards_trend,gold",
            },
            timeout=10,
        )
        r.raise_for_status()
        log("   ✅ تم إرسال الإشعار")
        return True
    except Exception as e:
        log(f"   ❌ خطأ: {e}")
        return False


# ============================================================
# دورة واحدة
# ============================================================
def run_once():
    log("=" * 60)
    log("🚀 دورة جديدة")
    log("=" * 60)
    update_data()
    signal = generate_signal()
    if signal:
        log(f"📊 {signal['signal']} | السعر: {signal.get('current_price', 'N/A')}")
        send_ntfy(signal)
    log("=" * 60)


# ============================================================
# التشغيل المستمر
# ============================================================
def run_scheduler(interval_minutes: int = UPDATE_INTERVAL_MINUTES, max_cycles: int = None):
    global _scheduler_running, _stop_event
    import threading

    _stop_event = threading.Event()
    _scheduler_running = True

    log(f"🕐 بدء Scheduler (كل {interval_minutes} دقيقة)")
    log(f"   الأطر: {', '.join(ACTIVE_TIMEFRAMES)}")

    cycle = 0
    while _scheduler_running:
        cycle += 1
        log(f"\n🔁 الدورة #{cycle}")
        try:
            run_once()
        except KeyboardInterrupt:
            log("\n⏹️ تم الإيقاف")
            break
        except Exception as e:
            log(f"❌ خطأ: {e}")

        if max_cycles and cycle >= max_cycles:
            break

        log(f"⏳ انتظار {interval_minutes} دقيقة...")
        for _ in range(interval_minutes * 60):
            if _stop_event.is_set() or not _scheduler_running:
                break
            time.sleep(1)

    _scheduler_running = False


def start_scheduler(interval_minutes: int = UPDATE_INTERVAL_MINUTES) -> bool:
    global _scheduler_running, _scheduler_thread
    import threading
    if _scheduler_running:
        return False
    _scheduler_thread = threading.Thread(
        target=run_scheduler,
        args=(interval_minutes,),
        daemon=True,
    )
    _scheduler_thread.start()
    return True


def stop_scheduler() -> bool:
    global _scheduler_running, _stop_event
    if not _scheduler_running:
        return False
    if _stop_event:
        _stop_event.set()
    _scheduler_running = False
    return True


# ============================================================
# Main
# ============================================================
def main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        run_once()
    else:
        run_scheduler()


if __name__ == "__main__":
    main()