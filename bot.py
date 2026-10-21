import sqlite3
import os

import discord
from discord import app_commands

from config import BOT_TOKEN, GUILD_ID
from discord_notify import COLORS

from report import make_chart

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "data", "monitor.db")

icons = {"UP": "✅", "SLOW": "🐢", "DOWN": "❌"}

slow_ms = 2000   # ให้ตรงกับใน monitor.py


def get_latest():
    """ดึงผลเช็กล่าสุดของแต่ละเป้าหมาย (เฉพาะที่เช็กใน 10 นาทีล่าสุด)"""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT url, status, response_ms, reason, checked_at
        FROM checks
        WHERE id IN (SELECT MAX(id) FROM checks GROUP BY url)
          AND checked_at >= datetime('now', 'localtime', '-10 minutes')
        ORDER BY url
    """).fetchall()
    conn.close()
    return rows


# ---------- ตั้งค่าบอท ----------
intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)

    # ลงทะเบียนคำสั่งเฉพาะ Server ของเรา (ขึ้นทันที)
    tree.copy_global_to(guild=guild)
    synced = await tree.sync(guild=guild)

    # ล้างคำสั่งแบบ global ที่เคยลงไว้ กันคำสั่งขึ้นซ้ำ 2 อัน
    tree.clear_commands(guild=None)
    await tree.sync()

    print("บอทออนไลน์แล้ว:", client.user)
    print("คำสั่งที่ลงทะเบียน:", [c.name for c in synced])


# ---------- คำสั่ง /status ----------
@tree.command(name="status", description="ดูสถานะล่าสุดของทุกเป้าหมาย")
async def status(interaction: discord.Interaction):
    rows = get_latest()

    if not rows:
        await interaction.response.send_message(
            "ยังไม่มีข้อมูลล่าสุด 🤔 เช็กว่า monitor.py รันอยู่ไหม"
        )
        return

    down_count = sum(1 for r in rows if r[1] == "DOWN")
    if down_count:
        color = COLORS["DOWN"]
        title = f"📡 สถานะล่าสุด: ล่ม {down_count} จาก {len(rows)}"
    else:
        color = COLORS["UP"]
        title = f"📡 สถานะล่าสุด: ปกติทั้งหมด {len(rows)} เป้าหมาย"

    embed = discord.Embed(title=title, color=color)

    for url, st, ms, reason, checked_at in rows:
        if st == "DOWN":
            detail = reason or "ไม่ทราบสาเหตุ"
        else:
            detail = f"{ms} ms"
        embed.add_field(
            name=f"{icons.get(st, '❔')} {url}",
            value=f"{detail}\nเช็กล่าสุด {checked_at[11:16]} น.",
            inline=False,
        )

    await interaction.response.send_message(embed=embed)

# ---------- คำสั่ง /chart ----------
@tree.command(name="chart", description="ขอกราฟความเร็วย้อนหลัง")
@app_commands.describe(hours="ย้อนหลังกี่ชั่วโมง (1-48)")
async def chart(interaction: discord.Interaction, hours: app_commands.Range[int, 1, 48] = 6):
    # วาดกราฟอาจใช้เวลาเกิน 3 วินาที บอก Discord ก่อนว่า "กำลังทำอยู่"
    await interaction.response.defer()

    conn = sqlite3.connect(db_path)
    path = make_chart(conn, hours, slow_ms)
    conn.close()

    file = discord.File(path, filename="chart.png")
    embed = discord.Embed(title=f"📈 กราฟความเร็ว {hours} ชั่วโมงที่ผ่านมา", color=COLORS["INFO"])
    embed.set_image(url="attachment://chart.png")

    await interaction.followup.send(embed=embed, file=file)

client.run(BOT_TOKEN)