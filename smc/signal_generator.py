"""
smc/signal_generator.py
محرك توليد إشارات التداول (Signal Generation) - النسخة المحسّنة.

التحسينات:
1. تحذير "اتجاه ضعيف" عندما |bias_score| < 0.4
2. سيناريوهات شرطية (إذا كسر X → BUY، إذا كسر Y → SELL)
3. شرح شرط التحول إلى إشارة فعلية
4. عرض مستويات التداول حتى في حالة WAIT
5. [جديد] تجاهل الأطر الغائبة أو الفارغة في _calculate_bias
         (كانت تُحسب كـ neutral بأوزانها الكاملة، مما يُشوّه النتيجة)
"""

from typing import Optional


# ============================================================
# إعدادات
# ============================================================
TIMEFRAME_WEIGHTS = {
    "D1": 3.0,
    "H4": 3.0,
    "H1": 2.0,
    "M30": 2.0,
    "M15": 1.0,
    "M5": 1.0,
}

MIN_CONFIDENCE_FOR_SIGNAL = 60
STRONG_CONSENSUS_RATIO = 0.70
WEAK_TREND_THRESHOLD = 0.40


# ============================================================
# الدوال المساعدة
# ============================================================

def _trend_score(trend: str) -> float:
    if trend == "bullish":
        return 1.0
    elif trend == "bearish":
        return -1.0
    return 0.0


def _calculate_bias(snapshot: dict) -> dict:
    """
    حساب الاتجاه العام المرجّح.
    
    ✅ إصلاح مهم:
    كان الكود السابق يمر على كل الأطر في TIMEFRAME_WEIGHTS، ويحسب
    الأطر الغائبة (غير الموجودة في snapshot) كـ "neutral" بأوزانها
    الكاملة، مما يُخفّض النتيجة بشكل كبير.
    
    مثال:
        snapshot يحتوي فقط على H1 (bullish, وزن 2)
        total_weight كان يصبح 12 (كل الأطر)
        weighted_sum كان يصبح +2.0 (H1 فقط)
        weighted_score = 2/12 = 0.167 (ضعيف جداً، رغم أن H1 صاعد بوضوح!)
    
    الآن: نتجاهل الأطر الغائبة، فيصبح:
        total_weight = 2.0 (H1 فقط)
        weighted_sum = +2.0
        weighted_score = +1.0 (قوي وواضح)
    """
    total_weight = 0.0
    weighted_sum = 0.0
    bullish_weight = 0.0
    bearish_weight = 0.0

    for tf, weight in TIMEFRAME_WEIGHTS.items():
        tf_data = snapshot.get(tf, {})

        # ✅ الإصلاح: تجاهل الأطر الغائبة أو الفارغة أو التي فشلت
        if not tf_data or "error" in tf_data:
            continue

        # نتأكد من وجود current_trend
        if "current_trend" not in tf_data:
            continue

        trend = tf_data.get("current_trend", "neutral")
        score = _trend_score(trend)

        total_weight += weight
        weighted_sum += score * weight

        if trend == "bullish":
            bullish_weight += weight
        elif trend == "bearish":
            bearish_weight += weight

    # لا توجد أطر صالحة
    if total_weight == 0:
        return {
            "weighted_score": 0.0,
            "bias": "neutral",
            "total_weight": 0.0,
            "consensus_ratio": 0.0,
            "bullish_weight": 0.0,
            "bearish_weight": 0.0,
            "valid_timeframes": 0,
        }

    weighted_score = weighted_sum / total_weight

    # تحديد الاتجاه
    if weighted_score >= 0.3:
        bias = "bullish"
    elif weighted_score <= -0.3:
        bias = "bearish"
    else:
        bias = "neutral"

    # نسبة الإجماع
    if bias == "bullish":
        consensus = bullish_weight / total_weight
    elif bias == "bearish":
        consensus = bearish_weight / total_weight
    else:
        consensus = 0.0

    return {
        "weighted_score": weighted_score,
        "bias": bias,
        "total_weight": total_weight,
        "consensus_ratio": consensus,
        "bullish_weight": bullish_weight,
        "bearish_weight": bearish_weight,
        "valid_timeframes": sum(
            1 for tf in TIMEFRAME_WEIGHTS
            if snapshot.get(tf) and "error" not in snapshot.get(tf, {})
        ),
    }


def _detect_conflict(snapshot: dict) -> dict:
    large_tfs = ["D1", "H4", "H1"]
    small_tfs = ["M15", "M5"]

    large_scores = []
    small_scores = []

    for tf in large_tfs:
        tf_data = snapshot.get(tf, {})
        if tf_data and "error" not in tf_data and "current_trend" in tf_data:
            large_scores.append(_trend_score(tf_data["current_trend"]))

    for tf in small_tfs:
        tf_data = snapshot.get(tf, {})
        if tf_data and "error" not in tf_data and "current_trend" in tf_data:
            small_scores.append(_trend_score(tf_data["current_trend"]))

    if not large_scores or not small_scores:
        return {"conflict": False, "large_trend": "neutral", "small_trend": "neutral"}

    large_avg = sum(large_scores) / len(large_scores)
    small_avg = sum(small_scores) / len(small_scores)

    conflict = (large_avg > 0.5 and small_avg < -0.5) or (large_avg < -0.5 and small_avg > 0.5)

    def avg_to_str(v):
        if v > 0.3: return "bullish"
        if v < -0.3: return "bearish"
        return "neutral"

    return {
        "conflict": conflict,
        "large_trend": avg_to_str(large_avg),
        "small_trend": avg_to_str(small_avg),
    }


def _calculate_confidence(bias_info: dict, conflict_info: dict) -> float:
    base_confidence = abs(bias_info["weighted_score"]) * 50
    consensus_bonus = bias_info["consensus_ratio"] * 50
    confidence = base_confidence + consensus_bonus

    if conflict_info["conflict"]:
        confidence -= 20

    confidence = max(0.0, min(100.0, confidence))
    return round(confidence, 1)


def _find_nearest_levels(snapshot: dict, bias: str) -> dict:
    all_obs = []
    all_fvgs = []
    all_liqs = []

    for tf in TIMEFRAME_WEIGHTS.keys():
        tf_data = snapshot.get(tf, {})
        if not tf_data or "error" in tf_data:
            continue

        for ob in tf_data.get("order_blocks", []):
            all_obs.append({
                "top": ob.get("top"), "bottom": ob.get("bottom"),
                "type": ob.get("type"), "tf": tf,
            })

        for fvg in tf_data.get("fvgs", []):
            all_fvgs.append({
                "top": fvg.get("top"), "bottom": fvg.get("bottom"),
                "type": fvg.get("type"), "tf": tf,
            })

        for liq in tf_data.get("liquidity", []):
            all_liqs.append({
                "level": liq.get("level"),
                "type": liq.get("type"), "tf": tf,
            })

    last_prices = []
    for tf in TIMEFRAME_WEIGHTS.keys():
        tf_data = snapshot.get(tf, {})
        if tf_data and "error" not in tf_data and "last_close" in tf_data:
            last_prices.append(tf_data["last_close"])

    current_price = sum(last_prices) / len(last_prices) if last_prices else 0.0

    levels = {
        "current_price": round(current_price, 2),
        "entry": None,
        "stop_loss": None,
        "targets": [],
        "nearest_support": None,
        "nearest_resistance": None,
    }

    # مقاومة
    resistances = [
        ob["bottom"] for ob in all_obs
        if ob["type"] == "bearish_ob" and ob["bottom"] and ob["bottom"] > current_price
    ]
    if resistances:
        levels["nearest_resistance"] = round(min(resistances), 2)

    # دعم
    supports = [
        ob["top"] for ob in all_obs
        if ob["type"] == "bullish_ob" and ob["top"] and ob["top"] < current_price
    ]
    if supports:
        levels["nearest_support"] = round(max(supports), 2)

    # سيناريو البيع
    if bias == "bearish":
        sell_liqs = [liq["level"] for liq in all_liqs
                     if liq["type"] == "sell_side" and liq["level"]
                     and liq["level"] < current_price]
        entry = max(sell_liqs) if sell_liqs else current_price - (current_price * 0.001)
        levels["entry"] = round(entry, 2)

        sl = levels["nearest_resistance"] or (entry + (current_price * 0.003))
        levels["stop_loss"] = round(sl, 2)

        risk = sl - entry
        levels["targets"] = [
            round(entry - risk * 1.0, 2),
            round(entry - risk * 2.0, 2),
            round(entry - risk * 3.0, 2),
        ]

    # سيناريو الشراء
    elif bias == "bullish":
        buy_liqs = [liq["level"] for liq in all_liqs
                    if liq["type"] == "buy_side" and liq["level"]
                    and liq["level"] > current_price]
        entry = min(buy_liqs) if buy_liqs else current_price + (current_price * 0.001)
        levels["entry"] = round(entry, 2)

        sl = levels["nearest_support"] or (entry - (current_price * 0.003))
        levels["stop_loss"] = round(sl, 2)

        risk = entry - sl
        levels["targets"] = [
            round(entry + risk * 1.0, 2),
            round(entry + risk * 2.0, 2),
            round(entry + risk * 3.0, 2),
        ]

    return levels


def _generate_conditional_scenarios(snapshot: dict, levels: dict, bias: str) -> list:
    scenarios = []
    current = levels.get("current_price", 0)
    resistance = levels.get("nearest_resistance")
    support = levels.get("nearest_support")

    if resistance and resistance > current:
        entry_buy = resistance
        sl_buy = support if support else (entry_buy - (entry_buy * 0.003))
        risk_buy = entry_buy - sl_buy
        scenarios.append({
            "condition": f"إذا كسر السعر {resistance} صعوداً",
            "action": "BUY",
            "entry": round(entry_buy, 2),
            "stop_loss": round(sl_buy, 2),
            "targets": [
                round(entry_buy + risk_buy * 1.0, 2),
                round(entry_buy + risk_buy * 2.0, 2),
                round(entry_buy + risk_buy * 3.0, 2),
            ],
        })

    if support and support < current:
        entry_sell = support
        sl_sell = resistance if resistance else (entry_sell + (entry_sell * 0.003))
        risk_sell = sl_sell - entry_sell
        scenarios.append({
            "condition": f"إذا كسر السعر {support} هبوطاً",
            "action": "SELL",
            "entry": round(entry_sell, 2),
            "stop_loss": round(sl_sell, 2),
            "targets": [
                round(entry_sell - risk_sell * 1.0, 2),
                round(entry_sell - risk_sell * 2.0, 2),
                round(entry_sell - risk_sell * 3.0, 2),
            ],
        })

    return scenarios


# ============================================================
# الدالة الرئيسية
# ============================================================

def generate_signal(snapshot: dict) -> dict:
    bias_info = _calculate_bias(snapshot)
    conflict_info = _detect_conflict(snapshot)
    confidence = _calculate_confidence(bias_info, conflict_info)

    bias = bias_info["bias"]
    is_weak_trend = abs(bias_info["weighted_score"]) < WEAK_TREND_THRESHOLD

    # قرار الإشارة
    if bias == "neutral" or confidence < MIN_CONFIDENCE_FOR_SIGNAL:
        signal = "WAIT"
    elif conflict_info["conflict"]:
        signal = "WAIT"
    elif bias == "bullish":
        signal = "BUY"
    elif bias == "bearish":
        signal = "SELL"
    else:
        signal = "WAIT"

    levels = _find_nearest_levels(snapshot, bias)
    conditional_scenarios = _generate_conditional_scenarios(snapshot, levels, bias)

    # الأسباب
    reasoning = []
    reasoning.append(f"الاتجاه المرجّح: {bias} (score: {bias_info['weighted_score']:.2f})")
    reasoning.append(f"الإجماع: {bias_info['consensus_ratio']*100:.0f}%")

    if conflict_info["conflict"]:
        reasoning.append(
            f"⚠️ تضارب: الأطر الكبيرة {conflict_info['large_trend']} "
            f"والأطر الصغيرة {conflict_info['small_trend']}"
        )

    # التحذيرات
    warnings = []

    if is_weak_trend:
        warnings.append(
            f"اتجاه عام ضعيف (score = {bias_info['weighted_score']:.2f}) — "
            f"السوق في حالة تذبذب"
        )

    if conflict_info["conflict"]:
        warnings.append("تضارب بين الأطر الكبيرة والصغيرة — يُنصح بالانتظار")

    if confidence < MIN_CONFIDENCE_FOR_SIGNAL:
        warnings.append(
            f"ثقة منخفضة ({confidence}%) — أقل من الحد الأدنى ({MIN_CONFIDENCE_FOR_SIGNAL}%)"
        )

    # شرط التحول
    switch_condition = None
    if signal == "WAIT":
        if conflict_info["conflict"]:
            switch_condition = (
                "انتظر حتى يتفق الاتجاه بين الأطر الكبيرة والصغيرة، "
                "أو انتظر اختراق أحد المستويات المهمة (انظر السيناريوهات)"
            )
        elif is_weak_trend:
            switch_condition = (
                "انتظر اتجاه عام أقوى (score > 0.4 أو < -0.4) "
                "قبل اتخاذ قرار"
            )
        elif confidence < MIN_CONFIDENCE_FOR_SIGNAL:
            switch_condition = (
                f"انتظر حتى تصل الثقة إلى {MIN_CONFIDENCE_FOR_SIGNAL}% على الأقل"
            )

    # تفصيل الأطر
    timeframes = {}
    for tf, weight in TIMEFRAME_WEIGHTS.items():
        tf_data = snapshot.get(tf, {})
        if not tf_data or "error" in tf_data:
            timeframes[tf] = {"trend": "missing", "weight": weight}
        else:
            timeframes[tf] = {
                "trend": tf_data.get("current_trend", "neutral"),
                "weight": weight,
                "last_close": tf_data.get("last_close"),
            }

    return {
        "signal": signal,
        "confidence": confidence,
        "bias": bias,
        "bias_score": round(bias_info["weighted_score"], 3),
        "consensus_ratio": round(bias_info["consensus_ratio"], 3),
        "is_weak_trend": is_weak_trend,
        "valid_timeframes": bias_info.get("valid_timeframes", 0),
        "conflict": conflict_info,
        "reasoning": reasoning,
        "warnings": warnings,
        "switch_condition": switch_condition,
        "levels": levels,
        "conditional_scenarios": conditional_scenarios,
        "timeframes": timeframes,
    }