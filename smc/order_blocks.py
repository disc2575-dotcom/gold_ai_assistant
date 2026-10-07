"""
smc/order_blocks.py
كشف Order Blocks (كتل الأوامر) - نسخة محسّنة.

التحسينات:
1. فلتر الحجم: الشمعة العكسية يجب أن تكون بحجم معقول (>= 0.8 من المتوسط)
2. كشف الكسر: OB يُعلَّم كـ invalid إذا كُسر لاحقاً
3. دمج OB المتقاربة: OB في نفس النطاق السعري تُدمج
4. توثيق كامل لكل قرار
"""

import pandas as pd
import numpy as np


# ============================================================
# إعدادات
# ============================================================
MIN_CANDLE_SIZE_RATIO = 0.8   # حجم الشمعة العكسية >= 80% من المتوسط
MERGE_TOLERANCE_PCT = 0.003   # 0.3% لتحديد OB المتقاربة
SEARCH_WINDOW = 5             # شموع للبحث عن شمعة عكسية قبل BOS


def _merge_close_obs(obs_list: list, tolerance_pct: float) -> list:
    """
    دمج OB المتقاربة من نفس النوع.
    إذا كانت OB جديدة داخل نطاق X% من OB موجودة، تُدمج (نأخذ الأوسع).
    """
    if not obs_list:
        return obs_list

    merged = []
    for new_ob in sorted(obs_list, key=lambda x: x["index"]):
        found_merge = False
        for existing in merged:
            if existing["type"] != new_ob["type"]:
                continue

            # حساب التقارب
            ref_price = max(abs(existing["top"]), abs(new_ob["top"]), 1e-9)
            diff_top = abs(existing["top"] - new_ob["top"]) / ref_price
            diff_bottom = abs(existing["bottom"] - new_ob["bottom"]) / ref_price

            if diff_top <= tolerance_pct and diff_bottom <= tolerance_pct:
                # دمج: نأخذ الأوسع
                existing["top"] = max(existing["top"], new_ob["top"])
                existing["bottom"] = min(existing["bottom"], new_ob["bottom"])
                existing["merged_count"] = existing.get("merged_count", 1) + 1
                found_merge = True
                break

        if not found_merge:
            new_ob["merged_count"] = 1
            merged.append(new_ob)

    return merged


def detect_order_blocks(
    df: pd.DataFrame,
    window: int = SEARCH_WINDOW,
    min_size_ratio: float = MIN_CANDLE_SIZE_RATIO,
    merge_tolerance: float = MERGE_TOLERANCE_PCT,
) -> pd.DataFrame:
    """
    كشف Order Blocks محسّن.

    المنطق:
    1. لكل حدث BOS، ابحث للخلف عن آخر شمعة عكسية.
    2. تحقق من أن الشمعة العكسية بحجم معقول.
    3. سجّل OB إذا اجتاز الفلتر.
    4. دمج OB المتقاربة.
    5. علّم OB كمبطلة إذا كسرها السعر لاحقاً.

    المعاملات:
        df: DataFrame مع بيانات OHLCV + أعمدة BOS/CHOCH من structure.py
        window: عدد الشموع للبحث عن الشمعة العكسية
        min_size_ratio: أدنى حجم للشمعة العكسية كمضاعف من المتوسط
        merge_tolerance: نسبة التقارب لدمج OB

    الإرجاع:
        DataFrame مع أعمدة جديدة:
        - bullish_ob, bearish_ob (bool)
        - ob_high, ob_low (float)
        - ob_valid (bool) - هل OB لا يزال صالحاً؟
    """
    df = df.copy()
    df["bullish_ob"] = False
    df["bearish_ob"] = False
    df["ob_high"] = np.nan
    df["ob_low"] = np.nan
    df["ob_valid"] = False  # هل OB صالح (لم يُكسر بعد)؟
    df["ob_merged_count"] = 0  # كم OB دُمجت في هذه؟

    if len(df) < window + 2:
        return df

    # متوسط حجم الشمعة
    avg_candle_range = (df["high"] - df["low"]).mean()
    min_candle_size = avg_candle_range * min_size_ratio

    # ========== المرحلة 1: جمع OB المرشّحة ==========
    candidate_obs = []

    for i in range(window, len(df) - 1):
        row = df.iloc[i]

        # هل هناك BOS في هذه الشمعة؟
        if not row.get("bos", False):
            continue

        current_trend = row.get("trend", "neutral")

        # ابحث للخلف عن آخر شمعة عكسية
        for j in range(i - 1, max(i - window, 0), -1):
            prev = df.iloc[j]
            candle_range = prev["high"] - prev["low"]

            # فلتر الحجم
            if candle_range < min_candle_size:
                continue

            is_bearish_candle = prev["close"] < prev["open"]
            is_bullish_candle = prev["close"] > prev["open"]

            if current_trend == "bullish" and is_bearish_candle:
                candidate_obs.append({
                    "type": "bullish",
                    "index": j,
                    "top": prev["high"],
                    "bottom": prev["low"],
                    "timestamp": prev["timestamp"],
                })
                break

            elif current_trend == "bearish" and is_bullish_candle:
                candidate_obs.append({
                    "type": "bearish",
                    "index": j,
                    "top": prev["high"],
                    "bottom": prev["low"],
                    "timestamp": prev["timestamp"],
                })
                break

    # ========== المرحلة 2: دمج OB المتقاربة ==========
    merged_obs = _merge_close_obs(candidate_obs, merge_tolerance)

    # ========== المرحلة 3: كتابة OB في DataFrame ==========
    for ob in merged_obs:
        j = ob["index"]
        if ob["type"] == "bullish":
            df.iloc[j, df.columns.get_loc("bullish_ob")] = True
        else:
            df.iloc[j, df.columns.get_loc("bearish_ob")] = True

        df.iloc[j, df.columns.get_loc("ob_high")] = ob["top"]
        df.iloc[j, df.columns.get_loc("ob_low")] = ob["bottom"]
        df.iloc[j, df.columns.get_loc("ob_merged_count")] = ob["merged_count"]

    # ========== المرحلة 4: تحديد صلاحية OB ==========
    # OB يُبطَل إذا كسر السعر حدوده لاحقاً
    for idx, ob in enumerate(merged_obs):
        j = ob["index"]
        ob_top = ob["top"]
        ob_bottom = ob["bottom"]
        ob_type = ob["type"]

        # نفحص الشموع بعد OB
        future = df.iloc[j + 1:]
        if future.empty:
            # لا يوجد مستقبل → OB صالح مؤقتاً
            df.iloc[j, df.columns.get_loc("ob_valid")] = True
            continue

        if ob_type == "bullish":
            # bullish OB يُبطَل إذا أُغلق السعر تحته
            invalidated = (future["close"] < ob_bottom).any()
        else:
            # bearish OB يُبطَل إذا أُغلق السعر فوقه
            invalidated = (future["close"] > ob_top).any()

        df.iloc[j, df.columns.get_loc("ob_valid")] = not invalidated

    return df