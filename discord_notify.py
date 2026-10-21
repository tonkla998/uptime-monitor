import json
import requests
from datetime import datetime, timezone
from config import WEBHOOK_URL

COLORS = {
    "UP": 0x2ECC71,     # เขียว
    "SLOW": 0xF1C40F,   # เหลือง
    "DOWN": 0xE74C3C,   # แดง
    "INFO": 0x3498DB,   # ฟ้า
}


def send_embed(title, color, fields=None, description="", image_path=None):
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "fields": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "Uptime Monitor"},
    }

    for name, value, inline in fields or []:
        embed["fields"].append({"name": name, "value": value, "inline": inline})

    payload = {"embeds": [embed]}

    try:
        if image_path:
            # แนบรูปไว้ในการ์ด
            embed["image"] = {"url": "attachment://chart.png"}
            with open(image_path, "rb") as f:
                requests.post(
                    WEBHOOK_URL,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": ("chart.png", f, "image/png")},
                    timeout=10,
                )
        else:
            requests.post(WEBHOOK_URL, json=payload, timeout=5)
    except requests.RequestException:
        print("ส่ง Discord ไม่ได้ (เน็ตอาจหลุด)")