"""
signals/generator.py
توليد إشارات التداول النهائية بناءً على تحليل SMC.
"""

import pandas as pd
import numpy as np


# ============================================================
# إعدادات الإشارات
# ============================================================
MIN_CONFIDENCE = 40  # تم التعديل من 60 إلى 40


def calculate_confidence(row: pd.Series, direction: str) -> int:
    """
    حساب مستوى الثقة في الإشارة (0-100).

    كل عامل يضيف نقاطاً:
    - الاتجاه: +20
    - BOS: +20
    - OB: +20
    - FVG: +15
    - Liquidity: +15
    - تأكيد الشمعة: +10
    """
    confidence = 0

    # 1. الاتجاه
    trend = row.get("trend", "neutral")
    if (direction == "BUY" and trend == "bullish") or \
       (direction == "SELL" and trend == "bearish"):
        confidence += 20

    # 2. BOS
    if row.get("bos", False):
        break_dir = row.get("break_direction", None)
        if (direction == "BUY" and break_dir == "bullish") or \
           (direction == "SELL" and break_dir == "bearish"):
            confidence += 20

    # 3. OB
    if direction == "BUY" and row.get("bullish_ob", False):
        confidence += 20
    elif direction == "SELL" and row.get("bearish_ob", False):
        confidence += 20

    # 4. FVG
    if direction == "BUY" and row.get("bullish_fvg", False):
        confidence += 15
    elif direction == "SELL" and row.get("bearish_fvg", False):
        confidence += 15

    # 5. Liquidity Sweep
    if row.get("liq_swept", False):
        confidence += 15

    # 6. تأكيد الشمعة (Engulfing أو Pin Bar)
    body = abs(row["close"] - row["open"])
    candle_range = row["high"] - row["low"]
    if candle_range > 0:
        # Bullish Engulfing
        if direction == "BUY":
            lower_wick = min(row["open"], row["close"]) - row["low"]
            if lower_wick > body * 1.5:
                confidence += 10
        # Bearish Engulfing
        else:
            upper_wick = row["high"] - max(row["open"], row["close"])
            if upper_wick > body * 1.5:
                confidence += 10

    return min(confidence, 100)


def generate_signal(df: pd.DataFrame, idx: int) -> dict:
    """
    توليد إشارة تداول للشمعة idx.

    الإرجاع:
        dict مع:
        - action: "BUY", "SELL", أو None
        - confidence: 0-100
        - reasons: قائمة الأسباب
        - trend: الاتجاه
    """
    if idx < 25:
        return {"action": None, "confidence": 0, "reasons": []}

    row = df.iloc[idx]
    trend = row.get("trend", "neutral")

    # إذا كان الاتجاه محايداً، لا نولّد إشارة
    if trend == "neutral":
        return {"action": None, "confidence": 0, "reasons": []}

    # تحديد الاتجاه
    direction = "BUY" if trend == "bullish" else "SELL"

    # حساب الثقة
    confidence = calculate_confidence(row, direction)

    # جمع الأسباب
    reasons = []
    if trend:
        reasons.append(f"Trend: {trend}")
    if row.get("bos", False):
        reasons.append(f"BOS: {row.get('break_direction', 'N/A')}")
    if direction == "BUY" and row.get("bullish_ob", False):
        reasons.append("Bullish OB")
    if direction == "SELL" and row.get("bearish_ob", False):
        reasons.append("Bearish OB")
    if direction == "BUY" and row.get("bullish_fvg", False):
        reasons.append("Bullish FVG")
    if direction == "SELL" and row.get("bearish_fvg", False):
        reasons.append("Bearish FVG")
    if row.get("liq_swept", False):
        reasons.append("Liquidity Sweep")

    # القرار النهائي
    if confidence >= MIN_CONFIDENCE:
        return {
            "action": direction,
            "confidence": confidence,
            "reasons": reasons,
            "trend": trend,
            "timestamp": row["timestamp"],
            "price": row["close"],
        }

    return {"action": None, "confidence": confidence, "reasons": reasons}