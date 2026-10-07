"""
risk/manager.py
إدارة المخاطر وحساب حجم الصفقة.
"""

import pandas as pd


# ============================================================
# إعدادات المخاطر
# ============================================================
DEFAULT_ACCOUNT_BALANCE = 10000  # رأس المال بالدولار
DEFAULT_RISK_PER_TRADE = 1.0     # % من رأس المال لكل صفقة
DEFAULT_RR = 2.0                 # نسبة الربح/الخسارة
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.5


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """حساب ATR (Average True Range)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_position_size(
    entry_price: float,
    stop_loss: float,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    risk_pct: float = DEFAULT_RISK_PER_TRADE,
) -> dict:
    """
    حساب حجم الصفقة بناءً على:
    - رأس المال
    - نسبة المخاطرة
    - المسافة بين الدخول و SL
    """
    # المبلغ المُخاطَر به
    risk_amount = account_balance * (risk_pct / 100)

    # المسافة بين الدخول و SL
    sl_distance = abs(entry_price - stop_loss)

    if sl_distance <= 0:
        return {"error": "SL غير صالح"}

    # حجم الصفقة (Lot Size)
    # للذهب: 1 لوت = 100 أونصة، والحركة 1$ = 100$ ربح/خسارة
    position_size = risk_amount / (sl_distance * 100)

    # الحد الأدنى والأقصى
    position_size = max(0.01, min(position_size, 10.0))

    return {
        "position_size": round(position_size, 2),
        "risk_amount": round(risk_amount, 2),
        "sl_distance": round(sl_distance, 2),
        "account_balance": account_balance,
        "risk_pct": risk_pct,
    }


def calculate_levels(
    entry_price: float,
    direction: str,
    atr: float,
    rr: float = DEFAULT_RR,
) -> dict:
    """
    حساب SL و TP بناءً على ATR.
    """
    if pd.isna(atr) or atr <= 0:
        atr = entry_price * 0.003

    sl_distance = atr * ATR_SL_MULTIPLIER

    if direction == "BUY":
        sl = entry_price - sl_distance
        tp = entry_price + (sl_distance * rr)
    else:  # SELL
        sl = entry_price + sl_distance
        tp = entry_price - (sl_distance * rr)

    return {
        "entry": round(entry_price, 2),
        "stop_loss": round(sl, 2),
        "target": round(tp, 2),
        "sl_distance": round(sl_distance, 2),
        "rr": rr,
    }


def manage_risk(
    df: pd.DataFrame,
    idx: int,
    direction: str,
    account_balance: float = DEFAULT_ACCOUNT_BALANCE,
    risk_pct: float = DEFAULT_RISK_PER_TRADE,
    rr: float = DEFAULT_RR,
) -> dict:
    """
    الواجهة الموحدة: تحسب SL/TP + Position Size.
    """
    row = df.iloc[idx]
    entry_price = row["close"]

    # حساب ATR
    atr_series = calculate_atr(df, ATR_PERIOD)
    atr = atr_series.iloc[idx]

    # حساب SL/TP
    levels = calculate_levels(entry_price, direction, atr, rr)

    # حساب حجم الصفقة
    sizing = calculate_position_size(
        entry_price,
        levels["stop_loss"],
        account_balance,
        risk_pct,
    )

    return {
        "direction": direction,
        "entry": levels["entry"],
        "stop_loss": levels["stop_loss"],
        "target": levels["target"],
        "rr": levels["rr"],
        "atr": round(atr, 2) if not pd.isna(atr) else None,
        **sizing,
    }