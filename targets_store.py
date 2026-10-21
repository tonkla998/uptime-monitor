import json
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
targets_path = os.path.join(base_dir, "data", "targets.json")

# ใช้ตอนยังไม่มีไฟล์ targets.json (รันครั้งแรก)
DEFAULT_TARGETS = [
    {"type": "http", "target": "https://www.google.com"},
    {"type": "http", "target": "https://www.rmutt.ac.th"},
    {"type": "http", "target": "https://oreg3.rmutt.ac.th/"},
    {"type": "ping", "target": "8.8.8.8"},
]


def load_targets():
    if not os.path.exists(targets_path):
        save_targets(DEFAULT_TARGETS)
    with open(targets_path, encoding="utf-8") as f:
        return json.load(f)


def save_targets(targets):
    os.makedirs(os.path.dirname(targets_path), exist_ok=True)
    temp_path = targets_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=2)
    # เขียนลงไฟล์ชั่วคราวก่อน แล้วค่อยสลับ กัน monitor อ่านเจอไฟล์ที่เขียนไม่เสร็จ
    os.replace(temp_path, targets_path)