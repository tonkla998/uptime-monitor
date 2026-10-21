import sqlite3
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "data", "monitor.db")
conn = sqlite3.connect(db_path)

remove = ["https://abc.invalid", "https://abc.invalid/", "gg"] #จะลบอะไรก็ก็อปลิ้งมาวางไว้หรือ ip แล้วค่อยรัน

for url in remove:
    cur = conn.execute("DELETE FROM checks WHERE url = ?", (url,))
    print(f"ลบ {url}: {cur.rowcount} แถว")

conn.commit()
conn.close()