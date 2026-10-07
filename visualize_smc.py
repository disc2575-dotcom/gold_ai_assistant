"""
visualize_smc.py
رسم بياني احترافي لنتائج تحليل SMC.

يُرسم على آخر N شمعة:
- الشموع (Candlesticks)
- Fair Value Gaps (FVG) - مستطيلات ملونة
- Order Blocks (OB) - مستطيلات رمادية
- BOS/CHOCH - أسهم
- مناطق السيولة - خطوط أفقية
"""

import sqlite3
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle

from core.config import SYMBOL_DB as SYMBOL, DB_PATH
from smc.engine import analyze


# ============================================================
# إعدادات
# ============================================================
TIMEFRAME = "H1"        # الإطار الزمني للرسم
LAST_N_CANDLES = 200    # عدد الشموع الأخيرة للعرض
OUTPUT_PATH = "data/smc_chart.png"


# ============================================================
# تحميل البيانات
# ============================================================
def load_data(symbol: str, timeframe: str, db_path, drop_last: bool = True) -> pd.DataFrame:
    """تحميل الشموع من قاعدة البيانات."""
    table = f"{symbol}_{timeframe}"
    conn = sqlite3.connect(str(db_path))
    try:
        df = pd.read_sql(
            f'SELECT * FROM "{table}" ORDER BY timestamp ASC',
            conn,
            parse_dates=["timestamp"],
        )
    finally:
        conn.close()

    if drop_last and len(df) > 1:
        df = df.iloc[:-1].copy()

    return df


# ============================================================
# الرسم
# ============================================================
def plot_smc(df: pd.DataFrame, last_n: int = 200, output: str = "chart.png"):
    """رسم Chart احترافي."""
    # نأخذ آخر N شمعة فقط
    plot_df = df.tail(last_n).copy().reset_index(drop=True)

    if plot_df.empty:
        print("⚠️ لا توجد بيانات للرسم.")
        return

    # إعداد الشكل
    fig, ax = plt.subplots(figsize=(18, 10), facecolor="#0e1117")
    ax.set_facecolor("#0e1117")

    # ========== 1) رسم الشموع ==========
    for i, row in plot_df.iterrows():
        color = "#26a69a" if row["close"] >= row["open"] else "#ef5350"

        # الظل (wick)
        ax.plot([i, i], [row["low"], row["high"]],
                color=color, linewidth=0.8, zorder=2)

        # الجسم (body)
        body_bottom = min(row["open"], row["close"])
        body_height = abs(row["close"] - row["open"])
        if body_height == 0:
            body_height = 0.01  # شمعة doji

        rect = Rectangle(
            (i - 0.3, body_bottom), 0.6, body_height,
            facecolor=color, edgecolor=color, linewidth=0.5, zorder=3
        )
        ax.add_patch(rect)

    # ========== 2) رسم FVG ==========
    bullish_fvgs = plot_df[plot_df["bullish_fvg"]]
    bearish_fvgs = plot_df[plot_df["bearish_fvg"]]

    for i, row in bullish_fvgs.iterrows():
        rect = Rectangle(
            (i - 0.5, row["fvg_bottom"]), 5, row["fvg_top"] - row["fvg_bottom"],
            facecolor="#26a69a", alpha=0.15, edgecolor="#26a69a",
            linewidth=0.5, zorder=1
        )
        ax.add_patch(rect)

    for i, row in bearish_fvgs.iterrows():
        rect = Rectangle(
            (i - 0.5, row["fvg_bottom"]), 5, row["fvg_top"] - row["fvg_bottom"],
            facecolor="#ef5350", alpha=0.15, edgecolor="#ef5350",
            linewidth=0.5, zorder=1
        )
        ax.add_patch(rect)

    # ========== 3) رسم Order Blocks ==========
    bullish_obs = plot_df[plot_df["bullish_ob"]]
    bearish_obs = plot_df[plot_df["bearish_ob"]]

    for i, row in bullish_obs.iterrows():
        rect = Rectangle(
            (i - 0.5, row["ob_low"]), 10, row["ob_high"] - row["ob_low"],
            facecolor="#26a69a", alpha=0.25, edgecolor="#26a69a",
            linewidth=1.0, linestyle="--", zorder=1
        )
        ax.add_patch(rect)

    for i, row in bearish_obs.iterrows():
        rect = Rectangle(
            (i - 0.5, row["ob_low"]), 10, row["ob_high"] - row["ob_low"],
            facecolor="#ef5350", alpha=0.25, edgecolor="#ef5350",
            linewidth=1.0, linestyle="--", zorder=1
        )
        ax.add_patch(rect)

    # ========== 4) رسم BOS/CHOCH ==========
    events = plot_df[plot_df["bos"] | plot_df["choch"]]
    for i, row in events.iterrows():
        if row["choch"]:
            marker = "^" if row["break_direction"] == "bullish" else "v"
            color = "#ffd54f"  # أصفر للـ CHOCH
            label = "CHOCH"
        else:
            marker = "^" if row["break_direction"] == "bullish" else "v"
            color = "#2196f3"  # أزرق للـ BOS
            label = "BOS"

        ax.scatter(i, row["bos_choch_level"], marker=marker,
                   color=color, s=80, zorder=5, edgecolor="white", linewidth=0.5)

    # ========== 5) رسم مناطق السيولة ==========
    liqs = plot_df[plot_df["buy_liquidity"] | plot_df["sell_liquidity"]]
    for i, row in liqs.iterrows():
        color = "#ffeb3b" if row["buy_liquidity"] else "#ff9800"
        ax.axhline(y=row["liq_level"], color=color, alpha=0.4,
                   linestyle=":", linewidth=1, zorder=1)

    # ========== 6) إعدادات المحاور ==========
    ax.set_xlim(-1, len(plot_df))
    ax.set_ylim(plot_df["low"].min() * 0.999, plot_df["high"].max() * 1.001)

    # تنسيق المحور X بتواريخ حقيقية
    step = max(1, len(plot_df) // 10)
    ticks = list(range(0, len(plot_df), step))
    tick_labels = [plot_df.iloc[i]["timestamp"].strftime("%m-%d %H:%M") for i in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right",
                       color="white", fontsize=9)

    # تنسيق المحور Y
    ax.tick_params(axis="y", colors="white", labelsize=9)
    ax.tick_params(axis="x", colors="white")
    ax.grid(True, alpha=0.15, linestyle="--", color="white")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#444")
    ax.spines["left"].set_color("#444")

    # ========== 7) العنوان والمفاتيح ==========
    last_price = plot_df.iloc[-1]["close"]
    trend = plot_df.iloc[-1]["trend"]
    trend_emoji = "🟢" if trend == "bullish" else "🔴" if trend == "bearish" else "⚪"

    ax.set_title(
        f"{SYMBOL} - {TIMEFRAME}  |  آخر سعر: {last_price:.2f}  |  "
        f"الاتجاه: {trend_emoji} {trend}  |  آخر {len(plot_df)} شمعة",
        color="white", fontsize=14, pad=15, fontweight="bold"
    )

    # Legend يدوي
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#2196f3",
               markersize=10, label="BOS (كسر بنية)", linestyle="None"),
        Line2D([0], [0], marker="^", color="w", markerfacecolor="#ffd54f",
               markersize=10, label="CHOCH (تغيّر طابع)", linestyle="None"),
        Rectangle((0, 0), 1, 1, facecolor="#26a69a", alpha=0.3,
                  label="Bullish FVG / OB"),
        Rectangle((0, 0), 1, 1, facecolor="#ef5350", alpha=0.3,
                  label="Bearish FVG / OB"),
        Line2D([0], [0], color="#ffeb3b", linestyle=":", linewidth=2,
               label="مناطق السيولة"),
    ]
    ax.legend(handles=legend_elements, loc="upper left",
              facecolor="#1a1f2e", edgecolor="#444", labelcolor="white",
              fontsize=9, framealpha=0.9)

    # ========== 8) الحفظ ==========
    plt.tight_layout()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output, dpi=110, facecolor="#0e1117", bbox_inches="tight")
    plt.close()

    print(f"✅ تم حفظ الرسم في: {output}")


# ============================================================
# التشغيل الرئيسي
# ============================================================
def main():
    print(f"📊 تحميل بيانات {SYMBOL} على {TIMEFRAME}...")
    df = load_data(SYMBOL, TIMEFRAME, DB_PATH)

    if df.empty:
        print("⚠️ لا توجد بيانات.")
        return

    print(f"✅ عدد الشموع: {len(df)}")

    print("🔍 تشغيل التحليل الكامل...")
    df = analyze(df)

    print(f"🎨 رسم Chart على آخر {LAST_N_CANDLES} شمعة...")
    plot_smc(df, last_n=LAST_N_CANDLES, output=OUTPUT_PATH)


if __name__ == "__main__":
    main()