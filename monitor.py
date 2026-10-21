import requests
import time
import sqlite3
import os
from datetime import datetime
from config import WEBHOOK_URL     # 👈 ดึงมาจาก config.py

url = "https://www.google.com"
webhook_url = WEBHOOK_URL          # 👈 แทนลิงก์ที่เคยเขียนตรง ๆ

# ---------- ตั้งค่าฐานข้อมูล ----------
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
os.makedirs(data_dir, exist_ok=True)

db_path = os.path.join(data_dir, "monitor.db")
conn = sqlite3.connect(db_path)
print("ฐานข้อมูลอยู่ที่:", db_path)

conn.execute("""
    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checked_at TEXT,
        url TEXT,
        status TEXT
    )
""")
conn.commit()


# ---------- ฟังก์ชัน ----------
def check_site(url):
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def send_discord(message):
    requests.post(webhook_url, json={"content": message})


def save_result(url, is_up):
    status = "UP" if is_up else "DOWN"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO checks (checked_at, url, status) VALUES (?, ?, ?)",
        (now, url, status)
    )
    conn.commit()


# ---------- เริ่มทำงาน ----------
last_status = True
send_discord(f"▶️ เริ่มเฝ้าดู {url}")

while True:
    is_up = check_site(url)
    save_result(url, is_up)

    if is_up:
        print("UP ✅", url)
    else:
        print("DOWN ❌", url)

    if is_up != last_status:
        if is_up:
            send_discord(f"✅ {url} กลับมาใช้งานได้แล้ว")
        else:
            send_discord(f"🚨 {url} ล่ม!")

    last_status = is_up
    time.sleep(5)  # ทดสอบ 5 วิ ใช้จริงเปลี่ยนเป็น 60