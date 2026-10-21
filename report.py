import sqlite3
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")              # วาดกราฟแบบไม่เปิดหน้าต่าง (ใช้กับ pythonw ได้)
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from discord_notify import send_embed, COLORS

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
    plt.close(fig)
    return chart_path


def send_report(hours, send_to_discord=True, slow_ms=2000):
    conn = sqlite3.connect(db_path)
    rows = conn.execute(f"""
        SELECT
            url,
            COUNT(*),
            SUM(CASE WHEN status != 'DOWN' THEN 1 ELSE 0 END),
            AVG(response_ms),
            MAX(response_ms)
        FROM checks
        WHERE checked_at >= datetime('now', 'localtime', '-{hours} hours')
        GROUP BY url
    """).fetchall()

    if not rows:
        conn.close()
        print("ยังไม่มีข้อมูลในช่วงเวลานี้")
        return

    fields = []
    worst = 100

    for url, total, up, avg_ms, max_ms in rows:
        uptime = up / total * 100
        worst = min(worst, uptime)

        icon = "🟢" if uptime >= 99 else "🟡" if uptime >= 90 else "🔴"
        avg_text = f"{avg_ms:.0f} ms" if avg_ms else "-"
        max_text = f"{max_ms} ms" if max_ms else "-"

        value = (
            f"Uptime **{uptime:.1f}%** ({up}/{total})\n"
            f"เฉลี่ย {avg_text} · ช้าสุด {max_text}"
        )
        fields.append((f"{icon} {url}", value, False))
        print(f"{icon} {url}: {uptime:.1f}% เฉลี่ย {avg_text}")

    chart = make_chart(conn, hours, slow_ms)
    conn.close()

    # สีการ์ดตามเว็บที่แย่ที่สุด
    if worst >= 99:
        color = COLORS["UP"]
    elif worst >= 90:
        color = COLORS["SLOW"]
    else:
        color = COLORS["DOWN"]

    if send_to_discord:
        send_embed(f"📊 สรุป {hours} ชั่วโมงที่ผ่านมา", color, fields, image_path=chart)


# รันไฟล์นี้ตรง ๆ = สรุป 24 ชม. ทันที
if __name__ == "__main__":
    send_report(24)