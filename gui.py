import os
import sys
import sqlite3
import subprocess
import threading
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from targets_store import load_targets, save_targets
from discord_notify import send_embed, COLORS as EMBED_COLORS

base_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(base_dir, "data")
db_path = os.path.join(data_dir, "monitor.db")

REFRESH_MS = 5000          # รีเฟรชหน้าจอทุกกี่มิลลิวินาที
FRESH_MINUTES = 2          # ข้อมูลใหม่กว่านี้ ถือว่า monitor ยังทำงานอยู่
FONT = "Leelawadee UI" if sys.platform == "win32" else "Loma"

COLORS = {
    "UP": "#2ECC71",
    "SLOW": "#F1C40F",
    "DOWN": "#E74C3C",
    "WAIT": "#7F8C8D",
}
STATUS_TEXT = {"UP": "ปกติ", "SLOW": "ช้า", "DOWN": "ล่ม", "WAIT": "รอเช็ก"}


# ---------- อ่านข้อมูล ----------
def get_latest():
    """ผลเช็กล่าสุดของแต่ละเป้าหมาย: {url: (status, ms, reason, checked_at)}"""
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("""
            SELECT url, status, response_ms, reason, checked_at
            FROM checks
            WHERE id IN (SELECT MAX(id) FROM checks GROUP BY url)
        """).fetchall()
    except sqlite3.OperationalError:
        rows = []          # ยังไม่มีตาราง (monitor ยังไม่เคยรัน)
    conn.close()
    return {url: (st, ms, reason, at) for url, st, ms, reason, at in rows}


def last_check_time():
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT MAX(checked_at) FROM checks").fetchone()
    except sqlite3.OperationalError:
        row = (None,)
    conn.close()
    if row[0] is None:
        return None
    return datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")


def notify(title, color, fields):
    """ส่งการ์ดเข้า Discord ในเธรดแยก หน้าต่างจะได้ไม่ค้างระหว่างรอ"""
    threading.Thread(target=send_embed, args=(title, color, fields), daemon=True).start()


def monitor_is_fresh():
    last = last_check_time()
    return last is not None and (datetime.now() - last).total_seconds() < FRESH_MINUTES * 60


# ---------- หน้าต่างโปรแกรม ----------
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Mini Project")
        self.geometry("900x620")
        self.minsize(760, 500)
        ctk.set_appearance_mode("dark")

        self.procs = {"monitor": None, "bot": None}
        self.logs = {}
        self.stopped_at = {}       # เวลาที่กดหยุดล่าสุด

        self.font = ctk.CTkFont(family=FONT, size=14)
        self.font_bold = ctk.CTkFont(family=FONT, size=14, weight="bold")
        self.font_small = ctk.CTkFont(family=FONT, size=12)
        self.font_title = ctk.CTkFont(family=FONT, size=22, weight="bold")

        self.build_header()
        self.build_list()
        self.build_add_form()

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh()

    # ----- ส่วนบน: ชื่อโปรแกรม + ปุ่มเปิด/ปิด -----
    def build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(header, text="Mini Project", font=self.font_title).pack(side="left")

        self.controls = {}
        for name, label in [("bot", "Discord Bot"), ("monitor", "Monitor")]:
            box = ctk.CTkFrame(header, corner_radius=10)
            box.pack(side="right", padx=(8, 0))

            dot = ctk.CTkLabel(box, text="●", font=self.font, text_color=COLORS["WAIT"])
            dot.pack(side="left", padx=(12, 4), pady=8)
            text = ctk.CTkLabel(box, text=label, font=self.font, width=150, anchor="w")
            text.pack(side="left")
            button = ctk.CTkButton(box, text="เริ่ม", width=70, font=self.font,
                                   command=lambda n=name: self.toggle(n))
            button.pack(side="left", padx=(4, 10), pady=8)

            self.controls[name] = (dot, text, button, label)

        self.summary = ctk.CTkLabel(self, text="", font=self.font_small, anchor="w")
        self.summary.pack(fill="x", padx=22)

    # ----- ส่วนกลาง: รายการเป้าหมาย -----
    def build_list(self):
        self.list_frame = ctk.CTkScrollableFrame(self, corner_radius=10)
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=10)
        self.list_frame.grid_columnconfigure(1, weight=1)

    # ----- ส่วนล่าง: ฟอร์มเพิ่มเป้าหมาย -----
    def build_add_form(self):
        form = ctk.CTkFrame(self, corner_radius=10)
        form.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkLabel(form, text="เพิ่มเป้าหมาย", font=self.font_bold).pack(side="left", padx=12, pady=12)

        self.type_menu = ctk.CTkOptionMenu(form, values=["HTTP", "Ping"], width=90, font=self.font)
        self.type_menu.pack(side="left", padx=4)

        self.entry = ctk.CTkEntry(form, placeholder_text="https://example.com หรือ 8.8.8.8", font=self.font)
        self.entry.pack(side="left", fill="x", expand=True, padx=4)
        self.entry.bind("<Return>", lambda e: self.add_target())

        ctk.CTkButton(form, text="เพิ่ม", width=80, font=self.font,
                      command=self.add_target).pack(side="left", padx=(4, 12))

    # ---------- เปิด/ปิด monitor และบอท ----------
    def is_running(self, name):
        proc = self.procs[name]
        return proc is not None and proc.poll() is None

    def toggle(self, name):
        if self.is_running(name):
            self.stop(name)
        else:
            self.start(name)
        self.refresh(reschedule=False)

    def start(self, name):
        if name == "monitor" and monitor_is_fresh():
            ok = messagebox.askyesno(
                "monitor อาจรันอยู่แล้ว",
                "มีข้อมูลใหม่เข้ามาภายใน 2 นาที แปลว่าอาจมี monitor รันอยู่แล้ว\n"
                "(เช่น เปิดจาก run_monitor.bat หรือ Terminal)\n\n"
                "ถ้าเปิดเพิ่ม การแจ้งเตือนจะเด้งซ้ำ ต้องการเปิดต่อไหม?")
            if not ok:
                return

        os.makedirs(data_dir, exist_ok=True)
        log = open(os.path.join(data_dir, f"gui_{name}.log"), "w", encoding="utf-8")
        self.logs[name] = log

        env = dict(os.environ, PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

        self.procs[name] = subprocess.Popen(
            [sys.executable, f"{name}.py"],
            cwd=base_dir, stdout=log, stderr=subprocess.STDOUT,
            env=env, creationflags=flags,
        )

    def stop(self, name):
        proc = self.procs[name]
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        self.procs[name] = None
        self.stopped_at[name] = datetime.now()
        if name in self.logs:
            self.logs.pop(name).close()

    def on_close(self):
        running = [n for n in self.procs if self.is_running(n)]
        if running:
            ok = messagebox.askyesno("ปิดโปรแกรม",
                                     "monitor/บอทที่เปิดจากโปรแกรมนี้จะหยุดทำงานด้วย ต้องการปิดไหม?")
            if not ok:
                return
        for name in self.procs:
            self.stop(name)
        self.destroy()

    # ---------- เพิ่ม/ลบเป้าหมาย ----------
    def add_target(self):
        kind = self.type_menu.get().lower()
        target = self.entry.get().strip()

        if not target:
            return
        if kind == "http" and not target.startswith(("http://", "https://")):
            messagebox.showwarning("รูปแบบไม่ถูกต้อง", "HTTP ต้องขึ้นต้นด้วย http:// หรือ https://")
            return
        if kind == "ping" and "://" in target:
            messagebox.showwarning("รูปแบบไม่ถูกต้อง", "Ping ใส่แค่ชื่อเครื่องหรือ IP เช่น 8.8.8.8")
            return

        targets = load_targets()
        if any(t["target"] == target for t in targets):
            messagebox.showinfo("มีอยู่แล้ว", f"{target} อยู่ในรายการแล้ว")
            return

        targets.append({"type": kind, "target": target})
        save_targets(targets)
        self.entry.delete(0, "end")

        notify("➕ เพิ่มเป้าหมายแล้ว (จากโปรแกรม)", EMBED_COLORS["UP"], [
            ("เป้าหมาย", target, False),
            ("ประเภท", kind.upper(), True),
            ("ทั้งหมด", f"{len(targets)} เป้าหมาย", True),
        ])
        self.refresh(reschedule=False)

    def remove_target(self, target):
        if not messagebox.askyesno("ลบเป้าหมาย", f"ต้องการลบ\n{target}\nออกจากการเฝ้าดูไหม?"):
            return
        new_targets = [t for t in load_targets() if t["target"] != target]
        save_targets(new_targets)

        notify("🗑️ ลบเป้าหมายแล้ว (จากโปรแกรม)", EMBED_COLORS["DOWN"], [
            ("เป้าหมาย", target, False),
            ("เหลือ", f"{len(new_targets)} เป้าหมาย", True),
        ])
        self.refresh(reschedule=False)

    # ---------- อัปเดตหน้าจอ ----------
    def refresh(self, reschedule=True):
        self.update_controls()
        self.update_list()
        if reschedule:
            self.after(REFRESH_MS, self.refresh)

    def update_controls(self):
        fresh = monitor_is_fresh()

        # เพิ่งกดหยุดเอง ข้อมูลเก่ายังดูสด ไม่ต้องนับว่ามีตัวอื่นรันอยู่
        stopped = self.stopped_at.get("monitor")
        if stopped and (datetime.now() - stopped).total_seconds() < FRESH_MINUTES * 60:
            fresh = False

        for name, (dot, text, button, label) in self.controls.items():
            proc = self.procs[name]

            if self.is_running(name):
                color, status, btn = COLORS["UP"], "ทำงานอยู่", "หยุด"
            elif proc is not None:
                # เปิดจากโปรแกรมนี้ แต่ตายไปเอง
                color, status, btn = COLORS["DOWN"], "พัง (ดู log)", "เริ่ม"
            elif name == "monitor" and fresh:
                color, status, btn = COLORS["UP"], "ทำงาน (ที่อื่น)", "เริ่ม"
            else:
                color, status, btn = COLORS["WAIT"], "หยุดอยู่", "เริ่ม"

            dot.configure(text_color=color)
            text.configure(text=f"{label}: {status}")
            button.configure(text=btn,
                             fg_color=COLORS["DOWN"] if btn == "หยุด" else ("#3B8ED0", "#1F6AA5"))

    def update_list(self):
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        targets = load_targets()
        latest = get_latest()
        fresh = monitor_is_fresh()
        counts = {"UP": 0, "SLOW": 0, "DOWN": 0, "WAIT": 0}

        if not targets:
            ctk.CTkLabel(self.list_frame, text="ยังไม่มีเป้าหมาย เพิ่มได้จากช่องด้านล่าง",
                         font=self.font).grid(row=0, column=0, padx=12, pady=20)

        for row, item in enumerate(targets):
            name = item["target"]
            st, ms, reason, at = latest.get(name, ("WAIT", None, None, None))
            if not fresh:
                st = st if at else "WAIT"
            counts[st] = counts.get(st, 0) + 1

            if st == "DOWN":
                detail = reason or "ไม่ทราบสาเหตุ"
            elif ms is not None:
                detail = f"{ms} ms"
            else:
                detail = "ยังไม่มีข้อมูล"
            when = f"เช็กล่าสุด {at[11:19]}" if at else ""

            card = ctk.CTkFrame(self.list_frame, corner_radius=8)
            card.grid(row=row, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
            card.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(card, text="●", font=ctk.CTkFont(size=22),
                         text_color=COLORS[st], width=30).grid(row=0, column=0, rowspan=2, padx=(10, 6))
            ctk.CTkLabel(card, text=name, font=self.font_bold, anchor="w").grid(
                row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(card, text=f"{item['type'].upper()}  ·  {STATUS_TEXT[st]}  ·  {detail}",
                         font=self.font_small, anchor="w", text_color=COLORS[st] if st == "DOWN" else None
                         ).grid(row=1, column=1, sticky="w", pady=(0, 8))
            ctk.CTkLabel(card, text=when, font=self.font_small, text_color="gray").grid(
                row=0, column=2, rowspan=2, padx=10)
            ctk.CTkButton(card, text="ลบ", width=50, font=self.font_small,
                          fg_color="transparent", border_width=1, text_color=("gray20", "gray80"),
                          command=lambda n=name: self.remove_target(n)
                          ).grid(row=0, column=3, rowspan=2, padx=(0, 10))

        self.summary.configure(
            text=f"ปกติ {counts['UP']}   ·   ช้า {counts['SLOW']}   ·   ล่ม {counts['DOWN']}   ·   "
                 f"ทั้งหมด {len(targets)} เป้าหมาย   ·   อัปเดตหน้าจอ {datetime.now():%H:%M:%S}")


if __name__ == "__main__":
    App().mainloop()