import requests
import time
import sqlite3
import os
import subprocess
from datetime import datetime
from config import WEBHOOK_URL

# ---------- ตั้งค่า ----------
check_type = "http"                 # "http" สำหรับเว็บ, "ping" สำหรับเซิร์ฟเวอร์
target = "https://oreg3.rmutt.ac.th/"   # ถ้าเป็น ping ใส่แค่ชื่อเครื่อง/IP เช่น "8.8.8.8"
interval = 60                      # เช็กทุกกี่วินาที

# ---------- ฐานข้อมูล ----------
base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
os.makedirs(data_dir, exist_ok=True)

db_path = os.path.join(data_dir, "monitor.db")
conn = sqlite3.connect(db_path)

conn.execute("""
    CREATE TABLE IF NOT EXISTS checks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        checked_at TEXT,
        url TEXT,
        status TEXT
    )
""")
conn.commit()


# ---------- ฟังก์ชันเช็ก ----------
def check_http(url):
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def check_ping(host):
    result = subprocess.run(
        ["ping", "-n", "1", "-w", "2000", host],
        capture_output=True, text=True, errors="ignore"
    )
    return "TTL=" in result.stdout


def check(target):
    if check_type == "ping":
        return check_ping(target)
    return check_http(target)


# ---------- แจ้งเตือน + บันทึก ----------
def send_discord(message):
    try:
        requests.post(WEBHOOK_URL, json={"content": message}, timeout=5)
    except requests.RequestException:
        print("ส่ง Discord ไม่ได้ (เน็ตอาจหลุด)")


def save_result(target, is_up):
    status = "UP" if is_up else "DOWN"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO checks (checked_at, url, status) VALUES (?, ?, ?)",
        (now, target, status)
    )
    conn.commit()


# ---------- เริ่มทำงาน ----------
last_status = True
send_discord(f"▶️ เริ่มเฝ้าดู {target} ({check_type})")

while True:
    is_up = check(target)
    save_result(target, is_up)

    if is_up:
        print("UP ✅", target)
    else:
        print("DOWN ❌", target)

    if is_up != last_status:
        if is_up:
            send_discord(f"✅ {target} กลับมาใช้งานได้แล้ว")
        else:
            send_discord(f"🚨 {target} ล่ม!")

    last_status = is_up
    time.sleep(interval)