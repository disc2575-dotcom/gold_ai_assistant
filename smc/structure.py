"""
smc/structure.py
Market Structure V2
- Swing High / Swing Low
- BOS (Break of Structure)
- CHOCH (Change of Character)

ملاحظة:
يتم تأكيد الـ Swing بعد ظهور عدد محدد من الشموع اللاحقة
(right_bars). لذلك لا يتم اعتبار النقطة مؤكدة لحظيًا قبل اكتمال
هذه الشموع.
"""

import numpy as np
import pandas as pd


def find_swing_points(
    df: pd.DataFrame,
    left_bars: int = 5,
    right_bars: int = 5,
) -> pd.DataFrame:
    """
    تحديد Swing High / Swing Low.

    Swing High:
        high الحالية أعلى من جميع highs ضمن النافذة.

    Swing Low:
        low الحالية أدنى من جميع lows ضمن النافذة.

    right_bars تعني أن النقطة لا تصبح مؤكدة إلا بعد مرور
    right_bars شموع بعدها.
    """
    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars و right_bars يجب أن يكونا أكبر من صفر.")

    required = {"high", "low"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"الأعمدة المطلوبة غير موجودة: {sorted(missing)}")

    out = df.copy()
    out["swing_high"] = False
    out["swing_low"] = False

    highs = out["high"].to_numpy(dtype=float)
    lows = out["low"].to_numpy(dtype=float)

    start = left_bars
    end = len(out) - right_bars

    for i in range(start, end):
        high_window = highs[i - left_bars:i + right_bars + 1]
        low_window = lows[i - left_bars:i + right_bars + 1]

        # نستخدم القيمة القصوى/الدنيا مع منع NaN من توليد إشارات خاطئة.
        if np.isfinite(highs[i]) and highs[i] == np.max(high_window):
            # للتعامل مع القمم المتساوية: نسمح بأول قمة فقط داخل النافذة.
            if np.sum(high_window == highs[i]) == 1:
                out.iloc[i, out.columns.get_loc("swing_high")] = True

        if np.isfinite(lows[i]) and lows[i] == np.min(low_window):
            if np.sum(low_window == lows[i]) == 1:
                out.iloc[i, out.columns.get_loc("swing_low")] = True

    return out


def detect_bos_choch(
    df: pd.DataFrame,
    swing_left: int = 5,
    swing_right: int = 5,
) -> pd.DataFrame:
    """
    كشف BOS و CHOCH اعتمادًا على Swing High / Swing Low المؤكدة.

    تعريف مبسط ومتسق مع بنية المشروع:
    - إغلاق فوق آخر Swing High => كسر صاعد.
    - إغلاق تحت آخر Swing Low  => كسر هابط.
    - أول كسر في اتجاه جديد بعد اتجاه معاكس => CHOCH.
    - استمرار الكسر في الاتجاه نفسه => BOS.

    يتم تسجيل مستوى الكسر في bos_choch_level.
    """
    out = find_swing_points(df, swing_left, swing_right)

    out["trend"] = "neutral"
    out["bos"] = False
    out["choch"] = False
    out["bos_choch_level"] = np.nan
    out["break_direction"] = pd.Series(pd.NA, index=out.index, dtype="string")

    last_swing_high = None
    last_swing_low = None
    current_trend = "neutral"

    # لتجنب تكرار كسر نفس المستوى على عدة شموع متتالية.
    broken_high = None
    broken_low = None

    for i in range(len(out)):
        row = out.iloc[i]
        close = row["close"]

        # لا نستخدم swing النقطة نفسها كمرجع كسر في نفس اللحظة.
        if bool(row["swing_high"]):
            last_swing_high = float(row["high"])
            broken_high = None

        if bool(row["swing_low"]):
            last_swing_low = float(row["low"])
            broken_low = None

        break_up = (
            last_swing_high is not None
            and pd.notna(close)
            and close > last_swing_high
            and broken_high != last_swing_high
        )

        break_down = (
            last_swing_low is not None
            and pd.notna(close)
            and close < last_swing_low
            and broken_low != last_swing_low
        )

        # في حالة نادرة يستطيع فيها نفس الإغلاق كسر المستويين،
        # نترك الاتجاه دون إشارة مزدوجة.
        if break_up and not break_down:
            if current_trend == "bearish":
                out.iloc[i, out.columns.get_loc("choch")] = True
            else:
                out.iloc[i, out.columns.get_loc("bos")] = True

            out.iloc[i, out.columns.get_loc("bos_choch_level")] = last_swing_high
            out.iloc[i, out.columns.get_loc("break_direction")] = "bullish"
            current_trend = "bullish"
            broken_high = last_swing_high

        elif break_down and not break_up:
            if current_trend == "bullish":
                out.iloc[i, out.columns.get_loc("choch")] = True
            else:
                out.iloc[i, out.columns.get_loc("bos")] = True

            out.iloc[i, out.columns.get_loc("bos_choch_level")] = last_swing_low
            out.iloc[i, out.columns.get_loc("break_direction")] = "bearish"
            current_trend = "bearish"
            broken_low = last_swing_low

        out.iloc[i, out.columns.get_loc("trend")] = current_trend

    return out
