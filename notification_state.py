import json
import os

FILE = "notification_state.json"


def load_state() -> dict:
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_last_message(user_id: int):
    """Возвращает (channel_id, message_id) или (None, None)."""
    s = load_state()
    entry = s.get(str(user_id), {})
    return entry.get("channel_id"), entry.get("message_id")


def set_last_message(user_id: int, channel_id: int, message_id: int):
    s = load_state()
    s.setdefault(str(user_id), {})
    s[str(user_id)]["channel_id"] = channel_id
    s[str(user_id)]["message_id"] = message_id
    save_state(s)


def clear_last_message(user_id: int):
    s = load_state()
    if str(user_id) in s:
        del s[str(user_id)]
        save_state(s)