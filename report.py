import sqlite3
import os
import requests
from config import WEBHOOK_URL

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "data", "monitor.db")


def send_report(hours, send_to_discord=True):
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
    conn.close()

    if not rows:
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

    if send_to_discord:
        try:
            requests.post(WEBHOOK_URL, json={"content": report}, timeout=5)
        except requests.RequestException:
            print("ส่งรายงานเข้า Discord ไม่ได้")


# รันไฟล์นี้ตรง ๆ = สรุป 24 ชม. ทันที
if __name__ == "__main__":
    send_report(24)