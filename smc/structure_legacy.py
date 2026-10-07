"""
smc/structure.py
كشف BOS (Break of Structure) و CHOCH (Change of Character).
"""

import pandas as pd
import numpy as np


def find_swing_points(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    تحديد نقاط الانعكاس (Swing Highs و Swing Lows).
    """
    df = df.copy()
    df["swing_high"] = False
    df["swing_low"] = False

    highs = df["high"].values
    lows = df["low"].values

    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i - window:i + window + 1]):
            df.iloc[i, df.columns.get_loc("swing_high")] = True

        if lows[i] == min(lows[i - window:i + window + 1]):
            df.iloc[i, df.columns.get_loc("swing_low")] = True

    return df


def detect_bos_choch(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """
    كشف BOS و CHOCH بناءً على نقاط الانعكاس.
    """
    df = find_swing_points(df, window)
    df["trend"] = "neutral"
    df["bos"] = False
    df["choch"] = False
    df["bos_choch_level"] = np.nan

    last_swing_high = None
    last_swing_low = None
    current_trend = "neutral"

    for i in range(len(df)):
        row = df.iloc[i]

        if row["swing_high"]:
            last_swing_high = row["high"]
        if row["swing_low"]:
            last_swing_low = row["low"]

        if last_swing_high is not None and last_swing_low is not None:
            close = row["close"]

            if close > last_swing_high:
                if current_trend == "bullish":
                    df.iloc[i, df.columns.get_loc("bos")] = True
                    df.iloc[i, df.columns.get_loc("bos_choch_level")] = last_swing_high
                else:
                    df.iloc[i, df.columns.get_loc("choch")] = True
                    df.iloc[i, df.columns.get_loc("bos_choch_level")] = last_swing_high
                    current_trend = "bullish"

                last_swing_high = None

            elif close < last_swing_low:
                if current_trend == "bearish":
                    df.iloc[i, df.columns.get_loc("bos")] = True
                    df.iloc[i, df.columns.get_loc("bos_choch_level")] = last_swing_low
                else:
                    df.iloc[i, df.columns.get_loc("choch")] = True
                    df.iloc[i, df.columns.get_loc("bos_choch_level")] = last_swing_low
                    current_trend = "bearish"

                last_swing_low = None

        df.iloc[i, df.columns.get_loc("trend")] = current_trend

    return df