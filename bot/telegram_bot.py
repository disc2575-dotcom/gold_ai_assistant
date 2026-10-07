"""
bot/telegram_bot.py
إرسال الإشارات إلى تلغرام.
"""

import os
import json
import asyncio
from pathlib import Path

from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SIGNAL_PATH = Path("data/signal.json")


def load_signal() -> dict:
    """تحميل الإشارة من signal.json."""
    if not SIGNAL_PATH.exists():
        return None
    with open(SIGNAL_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_signal_message(signal: dict) -> str:
    """تنسيق الإشارة كرسالة تلغرام."""
    if not signal:
        return "⚠️ لا توجد إشارة."

    lines = []
    lines.append("🥇 *إشارة XAUUSD*")
    lines.append("")
    lines.append(f"🎯 *الإشارة:* {signal.get('signal', 'N/A')}")
    lines.append(f"📈 *الاتجاه:* {signal.get('bias', 'N/A').upper()}")
    lines.append(f"🎚️ *الثقة:* {signal.get('confidence', 0)}%")
    lines.append("")

    # المستويات
    levels = signal.get("levels", {})
    lines.append("💰 *المستويات:*")
    lines.append(f"• السعر الحالي: {levels.get('current_price', 'N/A')}")
    lines.append(f"• المقاومة: {levels.get('nearest_resistance', 'N/A')}")
    lines.append(f"• الدعم: {levels.get('nearest_support', 'N/A')}")
    lines.append("")

    # السيناريوهات
    scenarios = signal.get("conditional_scenarios", [])
    if scenarios:
        lines.append("🎬 *السيناريوهات:*")
        for s in scenarios:
            lines.append(f"• {s.get('condition', 'N/A')}")
            lines.append(f"  → {s.get('action', 'N/A')} @ {s.get('entry', 'N/A')}")
        lines.append("")

    # التحذيرات
    warnings = signal.get("warnings", [])
    if warnings:
        lines.append("⚠️ *تحذيرات:*")
        for w in warnings:
            lines.append(f"• {w}")

    return "\n".join(lines)


async def send_signal(signal: dict = None):
    """إرسال الإشارة إلى تلغرام."""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN غير موجود في .env")
        return

    if not TELEGRAM_CHAT_ID:
        print("❌ TELEGRAM_CHAT_ID غير موجود في .env")
        return

    if signal is None:
        signal = load_signal()

    if signal is None:
        print("❌ لا توجد إشارة في signal.json")
        return

    message = format_signal_message(signal)

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown",
        )
        print("✅ تم إرسال الإشارة إلى تلغرام")
    except Exception as e:
        print(f"❌ خطأ في الإرسال: {e}")


def send_signal_sync(signal: dict = None):
    """نسخة متزامنة (للاستخدام من سكربتات عادية)."""
    asyncio.run(send_signal(signal))