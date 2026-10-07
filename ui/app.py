"""
ui/app.py
واجهة Streamlit شاملة:
- الإشارات والتحليل.
- تحليل الأخبار (عربي + إنجليزي).
- مناطق OB/FVG على الرسم.
- مستويات فيبوناتشي.
- مؤشر ATR (تقلب السوق).
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# ✅ إضافة مسار المشروع إلى sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.analyzer import analyze_signal


# ============================================================
# إعدادات الصفحة
# ============================================================
st.set_page_config(
    page_title="XAUUSD Assistant",
    page_icon="🥇",
    layout="wide",
)

SIGNAL_PATH = Path("data/signal.json")


# ============================================================
# دوال مساعدة
# ============================================================
def signal_color(signal: str) -> str:
    s = str(signal).upper()
    if s == "BUY":
        return "🟢"
    if s == "SELL":
        return "🔴"
    return "⏸️"


def signal_badge(signal: str) -> str:
    s = str(signal).upper()
    if s == "BUY":
        return "background-color:#4caf50;color:white;padding:8px 16px;border-radius:8px;font-size:24px;font-weight:bold;"
    if s == "SELL":
        return "background-color:#f44336;color:white;padding:8px 16px;border-radius:8px;font-size:24px;font-weight:bold;"
    return "background-color:#ff9800;color:white;padding:8px 16px;border-radius:8px;font-size:24px;font-weight:bold;"


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def calculate_fibonacci(df: pd.DataFrame, lookback: int = 100) -> dict:
    """حساب مستويات فيبوناتشي من آخر Swing High/Low."""
    recent = df.tail(lookback)
    if recent.empty:
        return {}

    swing_high = float(recent["high"].max())
    swing_low = float(recent["low"].min())
    diff = swing_high - swing_low

    return {
        "0.0%": swing_high,
        "23.6%": swing_high - diff * 0.236,
        "38.2%": swing_high - diff * 0.382,
        "50.0%": swing_high - diff * 0.5,
        "61.8%": swing_high - diff * 0.618,
        "78.6%": swing_high - diff * 0.786,
        "100.0%": swing_low,
    }


# ============================================================
# تحميل الإشارة
# ============================================================
@st.cache_data(ttl=60)
def load_signal():
    if not SIGNAL_PATH.exists():
        return None
    with open(SIGNAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


signal = load_signal()

if signal is None:
    st.error("⚠️ لم يتم العثور على ملف signal.json")
    st.info("شغّل `python run_scheduler.py --once` أولاً لإنشاء الإشارة.")
    st.stop()


# ============================================================
# العنوان
# ============================================================
st.title("🥇 XAUUSD Trading Assistant")
st.markdown(f"**آخر تحديث:** {signal.get('updated_at', 'N/A')[:19]}")
st.markdown("---")


# ============================================================
# الشريط الجانبي
# ============================================================
with st.sidebar:
    st.header("⚙️ الإعدادات")
    show_ai = st.checkbox("تفعيل تحليل AI", value=False)
    show_chart = st.checkbox("عرض الرسم البياني", value=True)
    show_fib = st.checkbox("عرض مستويات فيبوناتشي", value=True)
    show_ob = st.checkbox("عرض مناطق OB/FVG", value=True)
    show_atr = st.checkbox("عرض مخطط ATR", value=True)
    st.markdown("---")
    st.caption("XAUUSD Assistant v3.0")


# ============================================================
# التوصية الرئيسية
# ============================================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    sig = signal.get("signal", "N/A")
    st.markdown(
        f'<div style="{signal_badge(sig)}">{signal_color(sig)} {sig}</div>',
        unsafe_allow_html=True,
    )
    st.caption("الإشارة")

with col2:
    bias = signal.get("bias", "N/A").upper()
    st.metric("الاتجاه", bias)

with col3:
    conf = signal.get("confidence", 0)
    st.metric("الثقة", f"{conf}%")

with col4:
    price = signal.get("current_price", "N/A")
    st.metric("السعر الحالي", price)


st.markdown("---")


# ============================================================
# التحليل والتحذيرات
# ============================================================
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("🔍 التحليل")
    reasoning = signal.get("reasoning", [])
    if reasoning:
        for r in reasoning:
            st.write(f"• {r}")
    else:
        st.caption("لا يوجد تحليل متاح.")

with col_b:
    st.subheader("⚠️ تحذيرات")
    warnings = signal.get("warnings", [])
    if warnings:
        for w in warnings:
            st.warning(w)
    else:
        st.success("لا توجد تحذيرات.")


switch = signal.get("switch_condition", "")
if switch:
    st.info(f"🔄 **شرط التحول:** {switch}")


st.markdown("---")


# ============================================================
# الأطر الزمنية
# ============================================================
st.subheader("📊 تحليل الأطر الزمنية")

timeframes = signal.get("timeframes", {})
if timeframes:
    tf_data = []
    for tf, data in timeframes.items():
        tf_data.append({
            "الإطار": tf,
            "الاتجاه": data.get("trend", "N/A"),
            "الوزن": data.get("weight", 0),
            "آخر سعر": data.get("last_close", 0),
        })
    st.dataframe(pd.DataFrame(tf_data), use_container_width=True, hide_index=True)


st.markdown("---")


# ============================================================
# المستويات المهمة
# ============================================================
st.subheader("💰 المستويات المهمة")

levels = signal.get("levels", {})

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("السعر الحالي", levels.get("current_price", signal.get("current_price", "N/A")))

with col2:
    st.metric("المقاومة", levels.get("nearest_resistance", "N/A"))

with col3:
    st.metric("الدعم", levels.get("nearest_support", "N/A"))


# ============================================================
# خطة الدخول
# ============================================================
if levels.get("entry"):
    st.markdown("#### 🎯 خطة الدخول المقترحة")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("الدخول", levels.get("entry", "N/A"))
    with col2:
        st.metric("الوقف", levels.get("stop_loss", "N/A"))
    with col3:
        targets = levels.get("targets", [])
        if targets:
            st.metric("TP1", targets[0] if len(targets) > 0 else "N/A")
            st.metric("TP2", targets[1] if len(targets) > 1 else "N/A")
    with col4:
        if targets and len(targets) > 2:
            st.metric("TP3", targets[2])
        st.metric("R:R", "1:2")


st.markdown("---")


# ============================================================
# السيناريوهات
# ============================================================
st.subheader("🎬 السيناريوهات الشرطية")

scenarios = signal.get("conditional_scenarios", [])
if scenarios:
    for scenario in scenarios:
        with st.expander(f"📌 {scenario.get('condition', 'N/A')}"):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**الإجراء:** {scenario.get('action', 'N/A')}")
                st.write(f"**الدخول:** {scenario.get('entry', 'N/A')}")
                st.write(f"**الوقف:** {scenario.get('stop_loss', 'N/A')}")
            with col2:
                targets = scenario.get("targets", [])
                for i, tp in enumerate(targets, 1):
                    st.write(f"**TP{i}:** {tp}")
else:
    st.caption("لا توجد سيناريوهات محددة.")


st.markdown("---")


# ============================================================
# تحليل الأخبار (News Filter)
# ============================================================
news = signal.get("news_analysis", {})
if news:
    st.subheader("📰 تحليل الأخبار (News Filter)")

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        sentiment = news.get("sentiment", "neutral")
        score = news.get("score", 0)
        if sentiment == "bullish":
            st.success(f"🟢 إيجابي ({score})")
        elif sentiment == "bearish":
            st.error(f"🔴 سلبي ({score})")
        else:
            st.info(f"⚪ محايد ({score})")

    with col2:
        topics = news.get("key_topics", [])
        if topics:
            st.write("**المواضيع:**")
            for t in topics[:5]:
                st.caption(f"• {t}")

    with col3:
        st.write(f"**التحليل:** {news.get('reasoning', 'N/A')}")

    # العناوين بالعربية + الإنجليزية
    headlines_ar = news.get("headlines", [])
    headlines_en = news.get("headlines_en", [])
    sources = news.get("sources", [])

    if headlines_ar or headlines_en:
        with st.expander("📋 عناوين الأخبار الأخيرة (عربي + إنجليزي)"):
            max_len = max(len(headlines_ar), len(headlines_en))
            for i in range(max_len):
                ar = headlines_ar[i] if i < len(headlines_ar) else ""
                en = headlines_en[i] if i < len(headlines_en) else ""
                src = sources[i] if i < len(sources) else ""

                st.markdown(f"**{i+1}.** {ar}")
                st.caption(f"↳ {en}  {f'— {src}' if src else ''}")

    st.markdown("---")


# ============================================================
# الرسم البياني الرئيسي
# ============================================================
if show_chart:
    st.subheader("📈 الرسم البياني (H1)")

    try:
        import sqlite3
        from core.config import DB_PATH, SYMBOL_DB

        conn = sqlite3.connect(str(DB_PATH))
        df = pd.read_sql(
            f'SELECT * FROM (SELECT * FROM "{SYMBOL_DB}_H1" ORDER BY timestamp DESC LIMIT 200) ORDER BY timestamp ASC',
            conn, parse_dates=["timestamp"],
        )
        conn.close()

        if not df.empty:
            fig = go.Figure()

            # شموع
            fig.add_trace(go.Candlestick(
                x=df["timestamp"],
                open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                increasing_line_color="#26a69a",
                decreasing_line_color="#ef5350",
                name="XAUUSD",
            ))

            # فيبوناتشي
            fib_levels = calculate_fibonacci(df, lookback=100)
            if show_fib and fib_levels:
                fib_colors = {
                    "0.0%": "#e91e63",
                    "23.6%": "#9c27b0",
                    "38.2%": "#3f51b5",
                    "50.0%": "#03a9f4",
                    "61.8%": "#009688",
                    "78.6%": "#8bc34a",
                    "100.0%": "#cddc39",
                }
                for label, price in fib_levels.items():
                    fig.add_hline(
                        y=price,
                        line_dash="dot",
                        line_color=fib_colors.get(label, "gray"),
                        line_width=1,
                        annotation_text=f"Fib {label}: {price:.2f}",
                        annotation_position="left",
                        annotation_font_size=9,
                    )

            # OB/FVG
            zones = signal.get("zones", [])
            if show_ob:
                for zone in zones:
                    z_type = zone.get("type", "")
                    z_top = zone.get("top")
                    z_bottom = zone.get("bottom")
                    if z_top is None or z_bottom is None:
                        continue

                    if "bullish" in z_type:
                        color = "rgba(76,175,80,0.25)"
                        line_color = "rgba(76,175,80,0.9)"
                    elif "bearish" in z_type:
                        color = "rgba(244,67,54,0.25)"
                        line_color = "rgba(244,67,54,0.9)"
                    else:
                        continue

                    x_start = df["timestamp"].iloc[-50]
                    x_end = df["timestamp"].iloc[-1]

                    fig.add_shape(
                        type="rect",
                        xref="x", yref="y",
                        x0=x_start, x1=x_end,
                        y0=z_bottom, y1=z_top,
                        fillcolor=color,
                        line=dict(color=line_color, width=1),
                        layer="below",
                    )

                    fig.add_annotation(
                        x=x_end, y=z_top,
                        text=zone.get("label", ""),
                        showarrow=False,
                        font=dict(size=9, color=line_color),
                        xanchor="right",
                        yanchor="bottom",
                    )

            # المستويات
            current_price = levels.get("current_price", signal.get("current_price"))
            if current_price:
                fig.add_hline(y=current_price, line_dash="dot", line_color="#2196f3",
                              annotation_text=f"السعر: {current_price}",
                              annotation_position="right")

            resistance = levels.get("nearest_resistance")
            if resistance:
                fig.add_hline(y=resistance, line_dash="dash", line_color="#f44336",
                              annotation_text=f"مقاومة: {resistance}",
                              annotation_position="right")

            support = levels.get("nearest_support")
            if support:
                fig.add_hline(y=support, line_dash="dash", line_color="#4caf50",
                              annotation_text=f"دعم: {support}",
                              annotation_position="right")

            entry = levels.get("entry")
            stop_loss = levels.get("stop_loss")
            targets = levels.get("targets", [])

            if entry:
                fig.add_hline(y=entry, line_dash="solid", line_color="#ff9800",
                              annotation_text=f"دخول: {entry}",
                              annotation_position="right")

            if stop_loss:
                fig.add_hline(y=stop_loss, line_dash="dot", line_color="#d32f2f",
                              annotation_text=f"وقف: {stop_loss}",
                              annotation_position="right")

            for i, tp in enumerate(targets, 1):
                fig.add_hline(y=tp, line_dash="dot", line_color="#388e3c",
                              annotation_text=f"TP{i}: {tp}",
                              annotation_position="right")

            fig.update_layout(
                height=650,
                xaxis_rangeslider_visible=False,
                template="plotly_dark",
                margin=dict(l=10, r=140, t=30, b=10),
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
                showlegend=True,
            )

            st.plotly_chart(fig, use_container_width=True)

            # ============================================
            # جدول OB/FVG
            # ============================================
            if show_ob:
                st.markdown("#### 📋 مناطق OB/FVG المكتشفة")
                if zones:
                    zones_df = pd.DataFrame(zones)
                    zones_df = zones_df.rename(columns={
                        "label": "النوع",
                        "top": "أعلى",
                        "bottom": "أسفل",
                        "timestamp": "التوقيت",
                    })
                    cols = [c for c in ["النوع", "أعلى", "أسفل", "التوقيت"] if c in zones_df.columns]
                    st.dataframe(zones_df[cols], use_container_width=True, hide_index=True)
                else:
                    st.caption("لا توجد مناطق OB/FVG حالياً.")

            # ============================================
            # جدول فيبوناتشي
            # ============================================
            if show_fib and fib_levels:
                st.markdown("#### 📐 مستويات فيبوناتشي")
                fib_df = pd.DataFrame([
                    {"المستوى": k, "السعر": round(v, 2)}
                    for k, v in fib_levels.items()
                ])
                st.dataframe(fib_df, use_container_width=True, hide_index=True)

            # ============================================
            # مخطط ATR
            # ============================================
            if show_atr:
                st.markdown("#### 📊 مؤشر تقلب السوق (ATR)")

                df["atr"] = calculate_atr(df, period=14)
                atr_df = df.dropna(subset=["atr"]).tail(100)

                if not atr_df.empty:
                    atr_avg = float(atr_df["atr"].mean())
                    current_atr = float(atr_df["atr"].iloc[-1])

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("ATR الحالي", f"{current_atr:.2f}")
                    with col2:
                        st.metric("متوسط ATR", f"{atr_avg:.2f}")
                    with col3:
                        if current_atr > atr_avg * 1.2:
                            st.metric("الحالة", "🔴 تقلب عالي")
                        elif current_atr < atr_avg * 0.8:
                            st.metric("الحالة", "🟢 تقلب منخفض")
                        else:
                            st.metric("الحالة", "🟡 تقلب عادي")

                    fig_atr = go.Figure()
                    fig_atr.add_trace(go.Scatter(
                        x=atr_df["timestamp"],
                        y=atr_df["atr"],
                        mode="lines",
                        name="ATR",
                        line=dict(color="#ff9800", width=2),
                        fill="tozeroy",
                        fillcolor="rgba(255,152,0,0.15)",
                    ))
                    fig_atr.add_hline(
                        y=atr_avg,
                        line_dash="dash",
                        line_color="#2196f3",
                        annotation_text=f"المتوسط: {atr_avg:.2f}",
                        annotation_position="right",
                    )
                    fig_atr.update_layout(
                        height=250,
                        template="plotly_dark",
                        margin=dict(l=10, r=10, t=20, b=10),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_atr, use_container_width=True)

        else:
            st.warning("لا توجد بيانات لعرض الرسم البياني.")
    except Exception as e:
        st.error(f"خطأ في تحميل الرسم البياني: {e}")


st.markdown("---")


# ============================================================
# تحليل AI
# ============================================================
if show_ai:
    st.subheader("🤖 تحليل الذكاء الاصطناعي")

    if st.button("🔍 تحليل الإشارة بـ AI"):
        with st.spinner("جاري التحليل..."):
            result = analyze_signal(signal)

        verdict = result.get("verdict", "error")
        confidence = result.get("confidence", 0)
        reasoning_ai = result.get("reasoning", "")
        warnings_ai = result.get("warnings", [])
        best_entry = result.get("best_entry", "")

        if verdict == "approve":
            st.success(f"✅ موافقة (ثقة: {confidence}%)")
        elif verdict == "reject":
            st.error(f"❌ رفض (ثقة: {confidence}%)")
        elif verdict == "wait":
            st.warning(f"⏸️ انتظار (ثقة: {confidence}%)")
        else:
            st.info(f"ℹ️ {verdict}")

        st.markdown(f"**التحليل:** {reasoning_ai}")
        st.markdown(f"**أفضل دخول:** {best_entry}")

        if warnings_ai:
            st.markdown("**⚠️ تحذيرات:**")
            for w in warnings_ai:
                st.write(f"- {w}")


# ============================================================
# الفوتر
# ============================================================
st.markdown("---")
st.caption("© 2026 XAUUSD Assistant | Powered by SMC + AI")