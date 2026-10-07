"""
smc/engine.py
محرك SMC — يربط كل وحدات التحليل ويستخرج ملخصاً موحداً.
"""

import pandas as pd

from smc.structure import detect_bos_choch
from smc.fvg import detect_fvg
from smc.order_blocks import detect_order_blocks
from smc.liquidity import detect_liquidity


def analyze(df):
    """
    يُشغّل كل وحدات التحليل بالترتيب الصحيح على DataFrame.
    يُرجع DataFrame مُثرى بكل الأعمدة المُكتشفة.
    """
    # 1) البنية أولاً (لأن Order Blocks تعتمد على bos + trend)
    df = detect_bos_choch(df)

    # 2) الفجوات
    df = detect_fvg(df)

    # 3) Order Blocks (تعتمد على bos + trend من الخطوة 1)
    df = detect_order_blocks(df)

    # 4) السيولة
    df = detect_liquidity(df)

    return df


def summarize(df):
    """يستخرج ملخص آخر حالة من DataFrame"""
    if df.empty:
        return {"error": "empty_dataframe"}

    last = df.iloc[-1]

    # ========== الأعداد الكلية ==========
    total_events = int((df["bos"] | df["choch"]).sum())
    total_fvgs = int((df["bullish_fvg"] | df["bearish_fvg"]).sum())
    total_obs = int((df["bullish_ob"] | df["bearish_ob"]).sum())
    total_liqs = int((df["buy_liquidity"] | df["sell_liquidity"]).sum())

    # ========== آخر 5 أحداث BOS/CHOCH ==========
    events = df[df["bos"] | df["choch"]].tail(5)
    events_list = [
        {
            "timestamp": str(row["timestamp"]),
            "type": "CHOCH" if row["choch"] else "BOS",
            "direction": row["break_direction"],
            "level": float(row["bos_choch_level"]) if pd.notna(row["bos_choch_level"]) else None,
        }
        for _, row in events.iterrows()
    ]

    # ========== آخر 5 FVG ==========
    fvgs = df[df["bullish_fvg"] | df["bearish_fvg"]].tail(5)
    fvg_list = [
        {
            "timestamp": str(row["timestamp"]),
            "type": "bullish" if row["bullish_fvg"] else "bearish",
            "top": float(row["fvg_top"]),
            "bottom": float(row["fvg_bottom"]),
            "size": float(row["fvg_size"]),
        }
        for _, row in fvgs.iterrows()
    ]

    # ========== آخر 5 Order Blocks ==========
    obs = df[df["bullish_ob"] | df["bearish_ob"]].tail(5)
    ob_list = [
        {
            "timestamp": str(row["timestamp"]),
            "type": "bullish_ob" if row["bullish_ob"] else "bearish_ob",
            "top": float(row["ob_high"]),
            "bottom": float(row["ob_low"]),
        }
        for _, row in obs.iterrows()
    ]

    # ========== آخر 5 مناطق سيولة ==========
    liqs = df[df["buy_liquidity"] | df["sell_liquidity"]].tail(5)
    liq_list = [
        {
            "timestamp": str(row["timestamp"]),
            "type": "buy_side" if row["buy_liquidity"] else "sell_side",
            "level": float(row["liq_level"]),
        }
        for _, row in liqs.iterrows()
    ]

    return {
        "current_trend": str(last["trend"]),
        "last_close": float(last["close"]),
        "last_timestamp": str(last["timestamp"]),
        # الأعداد الكلية
        "totals": {
            "events": total_events,
            "fvgs": total_fvgs,
            "order_blocks": total_obs,
            "liquidity": total_liqs,
        },
        # آخر 5 من كل نوع
        "events": events_list,
        "fvgs": fvg_list,
        "order_blocks": ob_list,
        "liquidity": liq_list,
    }