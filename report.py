import sqlite3
import os
from datetime import datetime

import requests
import matplotlib
matplotlib.use("Agg")              # วาดกราฟแบบไม่เปิดหน้าต่าง (ใช้กับ pythonw ได้)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import WEBHOOK_URL

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "data", "monitor.db")
chart_path = os.path.join(base_dir, "data", "chart.png")


def make_chart(conn, hours, slow_ms):
    rows = conn.execute(f"""
        SELECT checked_at, url, status, response_ms
        FROM checks
        WHERE checked_at >= datetime('now', 'localtime', '-{hours} hours')
        ORDER BY checked_at
    """).fetchall()

    # แยกข้อมูลของแต่ละเว็บ: {url: {"times": [...], "ms": [...], "down": [...]}}
    data = {}
    for checked_at, url, status, ms in rows:
        t = datetime.strptime(checked_at, "%Y-%m-%d %H:%M:%S")
        d = data.setdefault(url, {"times": [], "ms": [], "down": []})
        if status == "DOWN":
            d["down"].append(t)
        elif ms is not None:
            d["times"].append(t)
            d["ms"].append(ms)

    fig, ax = plt.subplots(figsize=(10, 5))

    for url, d in data.items():
        line, = ax.plot(d["times"], d["ms"], marker=".", label=url)
        if d["down"]:
            # จุดที่ล่ม: กากบาทสีเดียวกับเส้น วางไว้ที่ 0 ms
            ax.scatter(d["down"], [0] * len(d["down"]),
                       marker="x", s=60, color=line.get_color())

    ax.axhline(slow_ms, color="red", linestyle="--", linewidth=1, label=f"SLOW ({slow_ms} ms)")

    ax.set_title(f"Response time - last {hours} hour(s)   (x = DOWN)")
    ax.set_ylabel("ms")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()

    fig.savefig(chart_path)
    plt.close(fig)                 # ปิดกราฟ คืนหน่วยความจำ (สำคัญเมื่อรันทั้งวัน)
    return chart_path


def send_report(hours, send_to_discord=True, slow_ms=2000):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"""
        SELECT
            url,
            COUNT(*),
            SUM(CASE WHEN status != 'DOWN' THEN 1 ELSE 0 END),
            AVG(response_ms)
        FROM checks
        WHERE checked_at >= datetime('now', 'localtime', '-{hours} hours')
        GROUP BY url
    """).fetchall()

    if not rows:
        conn.close()
        print("ยังไม่มีข้อมูลในช่วงเวลานี้")
        return

    lines = [f"📊 สรุป {hours} ชั่วโมงที่ผ่านมา"]

    for url, total, up, avg_ms in rows:
        uptime = up / total * 100
        avg_text = f"{avg_ms:.0f} ms" if avg_ms else "-"
        icon = "🟢" if uptime >= 99 else "🟡" if uptime >= 90 else "🔴"
        lines.append(f"{icon} {url}: {uptime:.1f}% ({up}/{total}) เฉลี่ย {avg_text}")

    report = "\n".join(lines)
    print(report)

    chart = make_chart(conn, hours, slow_ms)
    conn.close()
    print("บันทึกกราฟที่:", chart)

    if send_to_discord:
        try:
            with open(chart, "rb") as f:
                requests.post(
                    WEBHOOK_URL,
                    data={"content": report},
                    files={"file": ("chart.png", f, "image/png")},
                    timeout=10,
                )
        except requests.RequestException:
            print("ส่งรายงานเข้า Discord ไม่ได้")


# รันไฟล์นี้ตรง ๆ = สรุป 24 ชม. ทันที
if __name__ == "__main__":
    send_report(24)