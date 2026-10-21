import requests
import time
import sqlite3
import os
import subprocess
from datetime import datetime
from config import WEBHOOK_URL

# ---------- ตั้งค่า ----------
targets = [
    {"type": "http", "target": "https://www.google.com"},
    {"type": "http", "target": "https://www.rmutt.ac.th"},
    {"type": "http", "target": "https://abc.invalid"},
]
interval = 60

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


def check(item):
    if item["type"] == "ping":
        return check_ping(item["target"])
    return check_http(item["target"])


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
last_status = {}
for item in targets:
    last_status[item["target"]] = True

send_discord(f"▶️ เริ่มเฝ้าดู {len(targets)} เป้าหมาย")

while True:
    for item in targets:
        name = item["target"]
        is_up = check(item)
        save_result(name, is_up)

        if is_up:
            print("UP ✅", name)
        else:
            print("DOWN ❌", name)

        if is_up != last_status[name]:
            if is_up:
                send_discord(f"✅ {name} กลับมาใช้งานได้แล้ว")
            else:
                send_discord(f"🚨 {name} ล่ม!")

        last_status[name] = is_up

    print("---")
    time.sleep(interval)