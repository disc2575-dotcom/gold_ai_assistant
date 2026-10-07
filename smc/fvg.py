"""
smc/fvg.py
كشف Fair Value Gaps (FVG) - فجوات القيمة العادلة.

التحسينات:
- يستخدم متوسط حجم الشمعة (ATR-like) كمرجع للفلترة بدل نسبة من السعر.
- هذا يجعل الفلتر متسقاً عبر الأطر الزمنية المختلفة.
"""

import pandas as pd
import numpy as np


# الحد الأدنى لحجم FVG كمضاعف من متوسط حجم الشمعة (high - low)
# 0.8 يعني: الفجوة يجب أن تكون >= 80% من متوسط حجم الشمعة
DEFAULT_MIN_SIZE_RATIO = 0.8


def detect_fvg(df: pd.DataFrame, min_size_ratio: float = DEFAULT_MIN_SIZE_RATIO) -> pd.DataFrame:
    """
    كشف Fair Value Gaps (FVG) مع فلتر الحجم الأدنى.

    المعاملات:
        df: DataFrame يحتوي على OHLCV.
        min_size_ratio: الحد الأدنى لحجم FVG كمضاعف من متوسط حجم الشمعة.
                        الافتراضي 0.8 (80% من متوسط حجم الشمعة).
                        - على D1 حيث متوسط حجم الشمعة ~50$: الحد الأدنى = 40$
                        - على M5 حيث متوسط حجم الشمعة ~3$: الحد الأدنى = 2.4$
                        هذا يجعل الفلتر متسقاً عبر الأطر الزمنية.

    الإرجاع:
        DataFrame مع أعمدة: bullish_fvg, bearish_fvg, fvg_top, fvg_bottom, fvg_size.
    """
    df = df.copy()
    df["bullish_fvg"] = False
    df["bearish_fvg"] = False
    df["fvg_top"] = np.nan
    df["fvg_bottom"] = np.nan
    df["fvg_size"] = np.nan

    if len(df) < 3:
        return df

    # متوسط حجم الشمعة (high - low)
    avg_candle_range = (df["high"] - df["low"]).mean()
    min_size = avg_candle_range * min_size_ratio

    for i in range(2, len(df)):
        prev2 = df.iloc[i - 2]
        current = df.iloc[i]

        # Bullish FVG
        if current["low"] > prev2["high"]:
            gap_size = current["low"] - prev2["high"]
            if gap_size >= min_size:
                df.iloc[i, df.columns.get_loc("bullish_fvg")] = True
                df.iloc[i, df.columns.get_loc("fvg_top")] = current["low"]
                df.iloc[i, df.columns.get_loc("fvg_bottom")] = prev2["high"]
                df.iloc[i, df.columns.get_loc("fvg_size")] = gap_size

        # Bearish FVG
        elif current["high"] < prev2["low"]:
            gap_size = prev2["low"] - current["high"]
            if gap_size >= min_size:
                df.iloc[i, df.columns.get_loc("bearish_fvg")] = True
                df.iloc[i, df.columns.get_loc("fvg_top")] = prev2["low"]
                df.iloc[i, df.columns.get_loc("fvg_bottom")] = current["high"]
                df.iloc[i, df.columns.get_loc("fvg_size")] = gap_size

    return df