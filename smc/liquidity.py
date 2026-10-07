"""
smc/liquidity.py
كشف مناطق السيولة (Liquidity Zones) - نسخة محسّنة.

التحسينات:
1. window يتناسب مع الإطار الزمني (أوسع للأطر الكبيرة)
2. فلتر حجم الشمعة (لا نعتبر القمم الضعيفة سيولة)
3. دمج المناطق المتقاربة
4. تعليم المناطق المكسورة كـ "مسحوبة" (swept)
"""

import pandas as pd
import numpy as np


# ============================================================
# إعدادات
# ============================================================
DEFAULT_WINDOW = 8           # شموع للتحقق من القمة/القاع
MERGE_TOLERANCE_PCT = 0.001  # 0.1% لدمج المناطق المتقاربة
MIN_SWING_SIZE_RATIO = 0.5   # حجم الشمعة المحيطة >= 50% من المتوسط


def _merge_close_liquidity(zones: list, tolerance: float) -> list:
    """
    دمج مناطق السيولة المتقاربة من نفس النوع.
    """
    if not zones:
        return zones

    merged = []
    for new_zone in sorted(zones, key=lambda x: x["index"]):
        found_merge = False
        for existing in merged:
            if existing["type"] != new_zone["type"]:
                continue

            ref = max(abs(existing["level"]), abs(new_zone["level"]), 1e-9)
            diff = abs(existing["level"] - new_zone["level"]) / ref

            if diff <= tolerance:
                # دمج: نأخذ أحدث مستوى
                existing["level"] = new_zone["level"]
                existing["merged_count"] = existing.get("merged_count", 1) + 1
                existing["last_timestamp"] = new_zone["timestamp"]
                found_merge = True
                break

        if not found_merge:
            new_zone["merged_count"] = 1
            new_zone["last_timestamp"] = new_zone["timestamp"]
            merged.append(new_zone)

    return merged


def detect_liquidity(
    df: pd.DataFrame,
    window: int = DEFAULT_WINDOW,
    merge_tolerance: float = MERGE_TOLERANCE_PCT,
    min_swing_ratio: float = MIN_SWING_SIZE_RATIO,
) -> pd.DataFrame:
    """
    كشف مناطق السيولة محسّن.

    المنطق:
    - Buy-side Liquidity (BSL): قمم محلية (بيع عليها)
    - Sell-side Liquidity (SSL): قيعان محلية (شراء عندها)
    - نستخدم window متغير حسب الإطار
    - نفلتر القمم/القيعان الضعيفة (بدون حجم كافٍ)
    - ندمج المتقاربة
    - نعلّم المكسورة كـ swept

    المعاملات:
        df: DataFrame مع OHLCV
        window: عدد الشموع للتحقق من القمة/القاع
        merge_tolerance: نسبة التقارب لدمج المناطق
        min_swing_ratio: أدنى حجم للشمعة المحيطة

    الإرجاع:
        DataFrame مع أعمدة:
        - buy_liquidity, sell_liquidity (bool)
        - liq_level (float)
        - liq_swept (bool) - هل تم مسح المنطقة؟
    """
    df = df.copy()
    df["buy_liquidity"] = False
    df["sell_liquidity"] = False
    df["liq_level"] = np.nan
    df["liq_swept"] = False
    df["liq_merged_count"] = 0

    if len(df) < window * 2 + 1:
        return df

    highs = df["high"].values
    lows = df["low"].values

    # فلتر الحجم
    avg_range = (df["high"] - df["low"]).mean()
    min_range = avg_range * min_swing_ratio

    candidate_zones = []

    for i in range(window, len(df) - window):
        # التحقق من حجم الشمعة المحيطة
        candle_range = highs[i] - lows[i]
        if candle_range < min_range:
            continue

        # Buy-side Liquidity (قمة محلية)
        local_high = highs[i]
        is_high = all(
            local_high >= highs[j]
            for j in range(i - window, i + window + 1)
            if j != i
        )
        if is_high:
            candidate_zones.append({
                "type": "buy",
                "index": i,
                "level": local_high,
                "timestamp": df.iloc[i]["timestamp"],
            })

        # Sell-side Liquidity (قاع محلي)
        local_low = lows[i]
        is_low = all(
            local_low <= lows[j]
            for j in range(i - window, i + window + 1)
            if j != i
        )
        if is_low:
            candidate_zones.append({
                "type": "sell",
                "index": i,
                "level": local_low,
                "timestamp": df.iloc[i]["timestamp"],
            })

    # دمج المتقاربة
    merged_zones = _merge_close_liquidity(candidate_zones, merge_tolerance)

    # كتابة النتائج في DataFrame
    for zone in merged_zones:
        i = zone["index"]
        if zone["type"] == "buy":
            df.iloc[i, df.columns.get_loc("buy_liquidity")] = True
        else:
            df.iloc[i, df.columns.get_loc("sell_liquidity")] = True

        df.iloc[i, df.columns.get_loc("liq_level")] = zone["level"]
        df.iloc[i, df.columns.get_loc("liq_merged_count")] = zone["merged_count"]

    # تعليم المناطق المكسورة
    for i, row in df.iterrows():
        if not (row["buy_liquidity"] or row["sell_liquidity"]):
            continue

        level = row["liq_level"]
        is_buy = row["buy_liquidity"]

        future = df.iloc[i + 1:]
        if future.empty:
            continue

        if is_buy:
            # Buy-side liquidity تُمسَح إذا تجاوزها السعر لأعلى
            swept = (future["high"] > level).any()
        else:
            # Sell-side liquidity تُمسَح إذا تجاوزها السعر لأسفل
            swept = (future["low"] < level).any()

        df.iloc[i, df.columns.get_loc("liq_swept")] = bool(swept)

    return df