import json
from config import MAIN_CATEGORIES

with open("items.json", "r", encoding="utf-8") as f:
    ALL_ITEMS = json.load(f)


def get_main_category(internal_cat: str) -> str:
    """Преобразует внутреннюю категорию (weapon/pistol) в основную (weapon)."""
    if internal_cat.startswith("weapon/"):
        return "weapon"
    if internal_cat.startswith("attachment/"):
        return "attachment"
    if internal_cat.startswith("armor/"):
        return "armor"
    if internal_cat.startswith("other/skins") or "cosmetic" in internal_cat:
        return "cosmetics"
    if internal_cat.startswith("artefact/"):
        return "artefact"
    if "medicine" in internal_cat:
        return "medicine"
    if "food" in internal_cat or "drink" in internal_cat or "consumable" in internal_cat:
        return "consumable"
    if "craft" in internal_cat or "resource" in internal_cat or "container" in internal_cat:
        return "craft"
    return "other"


def is_artifact(item) -> bool:
    return item["category"].startswith("artefact/")


# Группировка предметов по основным категориям с дедупликацией
GROUPED_ITEMS = {key: [] for key in MAIN_CATEGORIES}
seen_ids = set()

for item in ALL_ITEMS:
    if "_variants" in item["category"]:
        continue
    if item["id"] in seen_ids:
        continue
    seen_ids.add(item["id"])
    main_cat = get_main_category(item["category"])
    GROUPED_ITEMS[main_cat].append(item)