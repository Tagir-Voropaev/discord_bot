import json
import os

FILE = "subscriptions.json"


def load_subs() -> dict:
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_subs(subs: dict):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def add_sub(user_id: int, item_id: str, name: str,
            max_price: int | None = None,
            rarity=None, refinement=None,
            mode: str = "smart"):
    """
    mode: "smart" — умный режим (любая редкость, порог относительно качества)
          "fixed" — фиксированный порог цены
    """
    subs = load_subs()
    uid = str(user_id)
    subs.setdefault(uid, [])
    subs[uid] = [s for s in subs[uid] if s["item_id"] != item_id]
    subs[uid].append({
        "item_id": item_id,
        "name": name,
        "max_price": max_price,
        "rarity": rarity,
        "refinement": refinement,
        "mode": mode,
    })
    save_subs(subs)


def remove_sub(user_id: int, item_id: str):
    subs = load_subs()
    uid = str(user_id)
    if uid in subs:
        subs[uid] = [s for s in subs[uid] if s["item_id"] != item_id]
        if not subs[uid]:
            del subs[uid]
        save_subs(subs)


def get_user_subs(user_id: int) -> list:
    return load_subs().get(str(user_id), [])