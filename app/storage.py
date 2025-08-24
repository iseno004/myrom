import json
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

def now_iso():
    return datetime.utcnow().isoformat()

def _file(user_id: str):
    return DATA_DIR / f"{user_id}_comments.json"

def load_comments(user_id: str):
    f = _file(user_id)
    if f.exists():
        return json.loads(f.read_text())
    return []

def save_comment(user_id: str, item: dict):
    f = _file(user_id)
    items = load_comments(user_id)
    items.append(item)
    f.write_text(json.dumps(items, ensure_ascii=False, indent=2))
    return item
