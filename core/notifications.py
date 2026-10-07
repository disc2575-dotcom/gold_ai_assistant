"""
core/notifications.py
التحكم في تفعيل/إيقاف الإشعارات.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
NOTIFICATIONS_FILE = BASE_DIR / "notifications.txt"


def is_notifications_enabled() -> bool:
    if not NOTIFICATIONS_FILE.exists():
        set_notifications(True)
        return True
    try:
        content = NOTIFICATIONS_FILE.read_text(encoding="utf-8").strip().upper()
        return content == "ON"
    except Exception:
        return False


def set_notifications(enabled: bool):
    NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    NOTIFICATIONS_FILE.write_text("ON" if enabled else "OFF", encoding="utf-8")


def get_status_text() -> str:
    return "🟢 مفعّلة" if is_notifications_enabled() else "🔴 معطّلة"


if __name__ == "__main__":
    print(f"حالة الإشعارات: {get_status_text()}")