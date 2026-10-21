import sqlite3
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, "data", "monitor.db")

conn = sqlite3.connect(db_path)
rows = conn.execute("SELECT * FROM checks ORDER BY id DESC LIMIT 10")

for row in rows:
    print(row)