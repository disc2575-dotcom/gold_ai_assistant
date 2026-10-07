"""
ai/analyzer.py
تحليل السوق والأخبار باستخدام Groq AI.
+ ترجمة العناوين إلى العربية.
"""

import os
import json
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# إعدادات
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL = "openai/gpt-oss-120b"


# ============================================================
# إنشاء عميل Groq
# ============================================================
def get_client():
    """إنشاء عميل Groq."""
    if not GROQ_API_KEY:
        raise ValueError("❌ لم يتم العثور على GROQ_API_KEY في ملف .env")
    return Groq(api_key=GROQ_API_KEY)


# ============================================================
# استخراج JSON من نص
# ============================================================
def extract_json(content: str) -> str:
    """استخراج JSON من نص (يتعامل مع ``` و markdown)."""
    content = content.strip()

    # إزالة ```json ... ```
    if "```" in content:
        parts = content.split("```")
        for part in parts:
            if "{" in part and "}" in part:
                content = part
                if content.startswith("json"):
                    content = content[4:]
                break

    # البحث عن أول { وآخر }
    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        content = content[start:end]

    return content.strip()


# ============================================================
# تحليل الإشارة
# ============================================================
def analyze_signal(signal_data: dict) -> dict:
    """تحليل الإشارة باستخدام Groq AI."""
    client = get_client()

    prompt = f"""
أنت محلل تداول خبير في الذهب (XAUUSD) ومتخصص في Smart Money Concepts (SMC).

لديك الإشارة التالية:

📊 تحليل الأطر الزمنية:
{json.dumps(signal_data.get('timeframes', {}), indent=2, ensure_ascii=False)}

🎯 التوصية الحالية: {signal_data.get('signal', 'N/A')}
📈 الاتجاه المرجّح: {signal_data.get('bias', 'N/A')}
🎚️ الثقة: {signal_data.get('confidence', 0)}%

💰 المستويات:
- السعر الحالي: {signal_data.get('current_price', 'N/A')}
- أقرب مقاومة: {signal_data.get('levels', {}).get('nearest_resistance', 'N/A')}
- أقرب دعم: {signal_data.get('levels', {}).get('nearest_support', 'N/A')}

المطلوب:
1. هل تؤيد هذه الإشارة أم لا؟ (verdict: "approve" / "reject" / "wait")
2. ما مستوى الثقة في قرارك؟ (0-100)
3. اشرح السبب في 2-3 جمل.
4. ما المخاطر المحتملة؟
5. ما السيناريو الأفضل للدخول؟

أجب بصيغة JSON فقط:
{{
    "verdict": "approve|reject|wait",
    "confidence": 50,
    "reasoning": "الشرح هنا",
    "warnings": ["تحذير 1"],
    "best_entry": "وصف أفضل نقطة دخول"
}}
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "أنت محلل تداول خبير. أجب بصيغة JSON فقط."},
                {"role": "user", "content": prompt},
            ],
            model=MODEL,
            temperature=0.3,
            max_tokens=1500,
        )

        content = response.choices[0].message.content
        content = extract_json(content)
        result = json.loads(content)

        result.setdefault("verdict", "wait")
        result.setdefault("confidence", 0)
        result.setdefault("reasoning", "")
        result.setdefault("warnings", [])
        result.setdefault("best_entry", "N/A")

        return result

    except json.JSONDecodeError as e:
        return {
            "verdict": "error",
            "confidence": 0,
            "reasoning": f"فشل JSON: {str(e)[:150]}",
            "warnings": [],
            "best_entry": "N/A",
        }
    except Exception as e:
        return {
            "verdict": "error",
            "confidence": 0,
            "reasoning": f"خطأ: {str(e)[:150]}",
            "warnings": [],
            "best_entry": "N/A",
        }


# ============================================================
# تحليل مشاعر الأخبار
# ============================================================
def analyze_news_sentiment(news_articles: list) -> dict:
    """تحليل مشاعر الأخبار باستخدام Groq."""
    if not news_articles:
        return {
            "sentiment": "neutral",
            "score": 0,
            "reasoning": "لا توجد أخبار متاحة.",
            "key_topics": [],
        }

    client = get_client()

    headlines = "\n".join([
        f"- {a['title']}"
        for a in news_articles[:8]
        if a.get("title")
    ])

    if not headlines:
        return {
            "sentiment": "neutral",
            "score": 0,
            "reasoning": "لا توجد عناوين صالحة.",
            "key_topics": [],
        }

    prompt = f"""Analyze the following news headlines for XAUUSD (Gold) sentiment.

Headlines:
{headlines}

Respond ONLY with a valid JSON object. No markdown. No explanation.

{{
    "sentiment": "bullish" or "bearish" or "neutral",
    "score": -10 to 10,
    "reasoning": "brief explanation in Arabic",
    "key_topics": ["topic1", "topic2"]
}}"""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a financial analyst. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            model=MODEL,
            temperature=0.2,
            max_tokens=1000,
        )

        content = response.choices[0].message.content
        content = extract_json(content)
        result = json.loads(content)

        result.setdefault("sentiment", "neutral")
        result.setdefault("score", 0)
        result.setdefault("reasoning", "")
        result.setdefault("key_topics", [])

        if result["sentiment"] not in ["bullish", "bearish", "neutral"]:
            result["sentiment"] = "neutral"

        try:
            result["score"] = int(result["score"])
        except (ValueError, TypeError):
            result["score"] = 0

        return result

    except json.JSONDecodeError as e:
        return {
            "sentiment": "neutral",
            "score": 0,
            "reasoning": f"فشل JSON: {str(e)[:150]}",
            "key_topics": [],
        }
    except Exception as e:
        return {
            "sentiment": "neutral",
            "score": 0,
            "reasoning": f"خطأ: {str(e)[:150]}",
            "key_topics": [],
        }


# ============================================================
# ترجمة العناوين إلى العربية
# ============================================================
def translate_headlines(headlines: list) -> list:
    """ترجمة العناوين إلى العربية باستخدام Groq."""
    if not headlines:
        return []

    client = get_client()

    # قائمة مرقمة
    numbered = "\n".join([f"{i+1}. {h}" for i, h in enumerate(headlines)])

    prompt = f"""Translate each of the following English news headlines into Arabic.
Keep the meaning accurate and natural in Arabic.
Do not add explanations.
Return ONLY the translations, one per line, numbered (1. 2. 3. ...).

Headlines:
{numbered}
"""

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a professional translator. Output ONLY the translations, numbered, one per line."},
                {"role": "user", "content": prompt},
            ],
            model=MODEL,
            temperature=0.1,
            max_tokens=1500,
        )

        content = response.choices[0].message.content.strip()

        # تقسيم الأسطر
        lines = [l.strip() for l in content.split("\n") if l.strip()]

        translations = []
        for line in lines:
            # إزالة الأرقام والرموز في البداية
            cleaned = re.sub(r"^\d+[\.\)\-]\s*", "", line).strip()
            if cleaned:
                translations.append(cleaned)

        # إذا فشل (عدد أقل)، أرجع الأصلية
        if len(translations) < len(headlines):
            return headlines

        return translations[:len(headlines)]

    except Exception as e:
        print(f"⚠️ فشل الترجمة: {e}")
        return headlines


# ============================================================
# تحليل سريع
# ============================================================
def quick_analysis(text: str) -> str:
    """تحليل سريع لأي نص."""
    client = get_client()
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": text}],
        model=MODEL,
        temperature=0.3,
        max_tokens=500,
    )
    return response.choices[0].message.content