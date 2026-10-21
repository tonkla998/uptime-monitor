import requests
import time
import sqlite3
import os
import subprocess
import platform
from datetime import datetime
from report import send_report
from discord_notify import send_embed, COLORS

# ---------- ตั้งค่า ----------
targets = [
    {"type": "http", "target": "https://www.google.com"},
    {"type": "http", "target": "https://www.rmutt.ac.th"},
    {"type": "http", "target": "https://oreg3.rmutt.ac.th/"},
    {"type": "ping", "target": "8.8.8.8"},
]
interval = 60         # เช็กทุกกี่วินาที
slow_ms = 2000        # ช้ากว่านี้ (ms) ถือว่า SLOW
retries = 3           # ลองกี่ครั้งก่อนตัดสินว่า DOWN
retry_delay = 3       # รอกี่วินาทีระหว่างลองใหม่
report_every = 360   # ส่งรายงาน+กราฟทุกกี่วินาที (3600 = 1 ชั่วโมง)
report_hours = 1      # รายงาน+กราฟ ย้อนหลังกี่ชั่วโมง

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

for column in ["response_ms INTEGER", "reason TEXT"]:
    try:
        conn.execute(f"ALTER TABLE checks ADD COLUMN {column}")
    except sqlite3.OperationalError:
        pass

conn.commit()


# ---------- ฟังก์ชันเช็ก (คืนค่า: ผ่านไหม, สาเหตุ) ----------
def check_http(url):
    try:
        response = requests.get(url, timeout=5)
    except requests.Timeout:
        return False, "Timeout (ไม่ตอบภายใน 5 วินาที)"
    except requests.ConnectionError:
        return False, "เชื่อมต่อไม่ได้ (หาเว็บไม่เจอ / เซิร์ฟเวอร์ปิด / เน็ตหลุด)"
    except requests.RequestException as e:
        return False, f"Error: {type(e).__name__}"

    if response.status_code == 200:
        return True, None
    return False, f"HTTP {response.status_code} {response.reason}"


def check_ping(host):
    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", "2000", host]
    else:
        cmd = ["ping", "-c", "1", "-W", "2", host]

    result = subprocess.run(cmd, capture_output=True, text=True, errors="ignore")

    if "TTL=" in result.stdout.upper():
        return True, None
    return False, "Ping ไม่ตอบกลับ"


def check(item):
    for attempt in range(retries):
        start = time.perf_counter()

        if item["type"] == "ping":
            ok, reason = check_ping(item["target"])
        else:
            ok, reason = check_http(item["target"])

        ms = int((time.perf_counter() - start) * 1000)

        if ok:
            break

        if attempt < retries - 1:
            print(f"   ลองใหม่ ({attempt + 2}/{retries}) {item['target']} - {reason}")
            time.sleep(retry_delay)

    if not ok:
        return "DOWN", None, reason
    if ms > slow_ms:
        return "SLOW", ms, None
    return "UP", ms, None


# ---------- ตัวช่วย ----------
def save_result(target, status, ms, reason):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO checks (checked_at, url, status, response_ms, reason) VALUES (?, ?, ?, ?, ?)",
        (now, target, status, ms, reason)
    )
    conn.commit()


def format_duration(seconds):
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if h:
        return f"{h} ชม. {m} นาที"
    if m:
        return f"{m} นาที {s} วินาที"
    return f"{s} วินาที"


def notify_change(item, status, ms, reason, downtime):
    name = item["target"]
    kind = item["type"].upper()

    if status == "DOWN":
        send_embed("🚨 ระบบล่ม!", COLORS["DOWN"], [
            ("เป้าหมาย", name, False),
            ("สาเหตุ", reason or "ไม่ทราบ", False),
            ("ประเภท", kind, True),
            ("ลองแล้ว", f"{retries} ครั้ง ล้มทั้งหมด", True),
        ])

    elif status == "SLOW":
        fields = [
            ("เป้าหมาย", name, False),
            ("ความเร็ว", f"{ms} ms", True),
            ("เกณฑ์", f"{slow_ms} ms", True),
        ]
        if downtime:
            fields.append(("ล่มไปนาน", downtime, True))
        send_embed("🐢 ตอบสนองช้า", COLORS["SLOW"], fields)

    else:
        fields = [
            ("เป้าหมาย", name, False),
            ("ประเภท", kind, True),
            ("ความเร็ว", f"{ms} ms", True),
        ]
        if downtime:
            fields.append(("ล่มไปนาน", downtime, True))
        send_embed("✅ กลับมาปกติ", COLORS["UP"], fields)


# ---------- เริ่มทำงาน ----------
icons = {"UP": "✅", "SLOW": "🐢", "DOWN": "❌"}

last_status = {}
down_since = {}
for item in targets:
    last_status[item["target"]] = "UP"

target_list = "\n".join(f"• `{t['type'].upper()}` {t['target']}" for t in targets)
send_embed("▶️ เริ่มเฝ้าดูระบบ", COLORS["INFO"], [
    ("จำนวนเป้าหมาย", str(len(targets)), True),
    ("เช็กทุก", format_duration(interval), True),
    ("รายงานทุก", format_duration(report_every), True),
], description=target_list)

last_report = time.time()

while True:
    for item in targets:
        name = item["target"]
        status, ms, reason = check(item)
        save_result(name, status, ms, reason)

        print(icons[status], status, name, f"{ms} ms" if ms else reason)

        if status != last_status[name]:
            downtime = None

            if status == "DOWN":
                down_since[name] = time.time()
            elif name in down_since:
                downtime = format_duration(time.time() - down_since.pop(name))

            notify_change(item, status, ms, reason, downtime)

        last_status[name] = status

    # ครบเวลาส่งรายงานหรือยัง
    if time.time() - last_report >= report_every:
        send_report(report_hours, slow_ms=slow_ms)
        last_report = time.time()

    print("---")
    time.sleep(interval)