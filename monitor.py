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
slow_ms = 2000      # ถ้าช้ากว่านี้ (มิลลิวินาที) ถือว่า SLOW
retries = 3         # ลองกี่ครั้งก่อนตัดสินว่า DOWN
retry_delay = 3     # รอกี่วินาทีระหว่างลองแต่ละครั้ง

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

# เพิ่มคอลัมน์ response_ms ให้ตารางเดิม (ถ้ามีแล้วจะข้ามไป)
try:
    conn.execute("ALTER TABLE checks ADD COLUMN response_ms INTEGER")
except sqlite3.OperationalError:
    pass

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
    for attempt in range(retries):
        start = time.perf_counter()

        if item["type"] == "ping":
            ok = check_ping(item["target"])
        else:
            ok = check_http(item["target"])

        ms = int((time.perf_counter() - start) * 1000)

        if ok:
            break                     # ผ่านแล้ว ไม่ต้องลองต่อ

        if attempt < retries - 1:
            print(f"   ลองใหม่ ({attempt + 2}/{retries}) {item['target']}")
            time.sleep(retry_delay)

    if not ok:
        return "DOWN", None
    if ms > slow_ms:
        return "SLOW", ms
    return "UP", ms


# ---------- แจ้งเตือน + บันทึก ----------
def send_discord(message):
    try:
        requests.post(WEBHOOK_URL, json={"content": message}, timeout=5)
    except requests.RequestException:
        print("ส่ง Discord ไม่ได้ (เน็ตอาจหลุด)")


def save_result(target, status, ms):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO checks (checked_at, url, status, response_ms) VALUES (?, ?, ?, ?)",
        (now, target, status, ms)
    )
    conn.commit()


# ---------- เริ่มทำงาน ----------
icons = {"UP": "✅", "SLOW": "🐢", "DOWN": "❌"}

last_status = {}
for item in targets:
    last_status[item["target"]] = "UP"

send_discord(f"▶️ เริ่มเฝ้าดู {len(targets)} เป้าหมาย")

while True:
    for item in targets:
        name = item["target"]
        status, ms = check(item)
        save_result(name, status, ms)

        print(icons[status], status, name, f"{ms} ms" if ms else "")

        if status != last_status[name]:
            if status == "UP":
                send_discord(f"✅ {name} กลับมาปกติ ({ms} ms)")
            elif status == "SLOW":
                send_discord(f"🐢 {name} ตอบช้า ({ms} ms)")
            else:
                send_discord(f"🚨 {name} ล่ม!")

        last_status[name] = status

    print("---")
    time.sleep(interval)