"""
data_pipeline/validator.py
التحقق من سلامة بيانات OHLCV قبل استخدامها.
"""

import pandas as pd


EXPECTED_DELTA = {
    "D1": pd.Timedelta(days=1),
    "H4": pd.Timedelta(hours=4),
    "H1": pd.Timedelta(hours=1),
    "M30": pd.Timedelta(minutes=30),
    "M15": pd.Timedelta(minutes=15),
    "M5": pd.Timedelta(minutes=5),
}


def validate_ohlcv(df: pd.DataFrame, timeframe: str) -> dict:
    """
    التحقق من سلامة البيانات وإرجاع تقرير مفصل.
    """
    report = {"timeframe": timeframe, "passed": True, "issues": []}

    if df.empty:
        report["passed"] = False
        report["issues"].append("❌ لا توجد بيانات إطلاقاً")
        return report

    # 1. فحص أسعار سالبة
    if df["close"].min() <= 0:
        report["passed"] = False
        report["issues"].append("❌ توجد أسعار إغلاق غير منطقية (<= 0)")

    # 2. فحص high < low
    if (df["high"] < df["low"]).any():
        report["passed"] = False
        report["issues"].append("❌ توجد شموع فيها high أقل من low")

    # 3. فحص التوقيتات المكررة
    duplicated = df["timestamp"].duplicated().sum()
    if duplicated > 0:
        report["passed"] = False
        report["issues"].append(f"❌ توجد {duplicated} توقيتات مكررة")

    # 4. فحص الفجوات الزمنية
    gaps = df["timestamp"].diff().dropna()
    expected = EXPECTED_DELTA[timeframe]
    abnormal_gaps = (gaps > expected * 3).sum()
    if abnormal_gaps > 0:
        report["issues"].append(
            f"⚠ تحذير: {abnormal_gaps} فجوة زمنية أكبر من المتوقع"
        )

    # 5. معلومات إضافية
    report["bars_count"] = len(df)
    report["date_range"] = f"{df.timestamp.min()} → {df.timestamp.max()}"

    return report