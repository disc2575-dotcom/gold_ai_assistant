"""
run_day4.py
تشغيل واجهة Streamlit.
"""

import subprocess
import sys


def main():
    print("=" * 70)
    print("🚀 اليوم الرابع: الذكاء الاصطناعي + الواجهة")
    print("=" * 70)
    print()
    print("🌐 جاري تشغيل واجهة Streamlit...")
    print("   افتح المتصفح على: http://localhost:8501")
    print()
    print("⏹️  لإيقاف الخادم: اضغط Ctrl+C")
    print("=" * 70)

    subprocess.run([
        sys.executable, "-m", "streamlit", "run", "ui/app.py",
        "--server.port", "8501",
    ])


if __name__ == "__main__":
    main()