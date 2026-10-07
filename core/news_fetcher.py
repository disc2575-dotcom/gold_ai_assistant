"""
core/news_fetcher.py
جلب الأخبار المالية من مصادر متعددة (Google News RSS + GDELT).
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime


# ============================================================
# إعدادات
# ============================================================
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
QUERY_KEYWORDS = "XAUUSD OR Gold OR Federal Reserve"
MAX_RECORDS = 15


# ============================================================
# المصدر 1: Google News RSS (موصى به)
# ============================================================
def fetch_google_news() -> list:
    """جلب الأخبار من Google News RSS (مجاني، بدون حدود)."""
    params = {
        "q": "gold price OR XAUUSD OR Federal Reserve interest rates",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }

    try:
        response = requests.get(GOOGLE_NEWS_RSS, params=params, timeout=15)
        response.raise_for_status()

        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        results = []
        for item in items[:MAX_RECORDS]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "")

            results.append({
                "title": title.strip(),
                "url": link,
                "date": pub_date,
                "source": source or "Google News",
            })

        return results

    except Exception as e:
        print(f"⚠️ فشل جلب Google News: {e}")
        return []


# ============================================================
# المصدر 2: GDELT (احتياطي)
# ============================================================
def fetch_gdelt_news() -> list:
    """جلب الأخبار من GDELT (احتياطي)."""
    params = {
        "query": QUERY_KEYWORDS,
        "mode": "artlist",
        "maxrecords": MAX_RECORDS,
        "format": "json",
        "sort": "DateDesc",
    }

    try:
        response = requests.get(GDELT_API_URL, params=params, timeout=15)
        if response.status_code == 429:
            print("⚠️ GDELT: طلبات كثيرة، سيتم التخطي")
            return []
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        results = []
        for a in articles:
            results.append({
                "title": a.get("title", "").strip(),
                "url": a.get("url", ""),
                "date": a.get("seendate", ""),
                "source": a.get("domain", ""),
            })
        return results

    except Exception as e:
        print(f"⚠️ فشل جلب GDELT: {e}")
        return []


# ============================================================
# الواجهة الموحدة
# ============================================================
def fetch_latest_news() -> list:
    """
    جلب الأخبار من المصادر المتاحة (Google News أولاً، ثم GDELT).
    """
    # حاول Google News أولاً
    news = fetch_google_news()
    if news:
        print(f"   ✅ Google News: {len(news)} خبر")
        return news

    # إذا فشل، جرب GDELT
    news = fetch_gdelt_news()
    if news:
        print(f"   ✅ GDELT: {len(news)} خبر")
        return news

    print("   ⚠️ لم يتم جلب أي أخبار من المصادر المتاحة")
    return []


# ============================================================
# اختبار
# ============================================================
if __name__ == "__main__":
    print("📰 جلب الأخبار...")
    news = fetch_latest_news()
    print(f"✅ عدد الأخبار: {len(news)}")
    print()
    for i, n in enumerate(news[:5], 1):
        print(f"{i}. {n['title']}")
        print(f"   المصدر: {n['source']}")
        print(f"   التاريخ: {n['date']}")
        print()