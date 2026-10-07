"""
test_bot.py
اختبار إرسال الإشارة إلى تلغرام.
"""

from bot.telegram_bot import send_signal_sync

print("🚀 إرسال إشارة اختبار إلى تلغرام...")
send_signal_sync()
print("✅ انتهى")