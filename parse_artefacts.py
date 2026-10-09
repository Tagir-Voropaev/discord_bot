import os
import json

# Путь к базе данных
DB_PATH = "stalzone-database-main/ru/items/artefact"

# Куда сохранить результат
OUTPUT_FILE = "all_artefacts.json"


# Расшифровка color → качество
COLOR_TO_QUALITY = {
    "DEFAULT": "Обычный",
    "GREEN": "Необычный",
    "BLUE": "Особый",
    "PURPLE": "Редкий",
    "YELLOW": "Исключительный",
    "ORANGE": "Легендарный",
    "RED": "Мифический",
}


def parse_artefacts():
    artefacts = []

    if not os.path.exists(DB_PATH):
        print(f"❌ Папка не найдена: {DB_PATH}")
        print("Убедитесь, что скрипт запускается из корня discord_bot,")
        print("и что рядом лежит папка stalzone-database-main/")
        return

    for root, dirs, files in os.walk(DB_PATH):
        # Пропускаем папки с вариациями заточки
        if "_variants" in root:
            continue

        for filename in files:
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(root, filename)
            item_id = filename[:-5]  # убираем .json

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                print(f"⚠️ Ошибка чтения {filepath}: {e}")
                continue

            # Название (русское)
            name = None
            name_block = data.get("name", {})
            if "lines" in name_block:
                name = name_block["lines"].get("ru")
            if not name:
                continue

            # Цвет / качество
            color = data.get("color", "DEFAULT")
            quality_ru = COLOR_TO_QUALITY.get(color, color)

            # Категория (последняя часть пути)
            relative = os.path.relpath(root, DB_PATH)
            category = relative.replace(os.sep, "/")

            artefacts.append({
                "id": item_id,
                "name": name,
                "color": color,
                "quality": quality_ru,
                "category": category,
            })

    # Сортировка по имени
    artefacts.sort(key=lambda x: x["name"])

    # Сохраняем
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(artefacts, f, ensure_ascii=False, indent=2)

    # Статистика
    print(f"✅ Найдено артефактов: {len(artefacts)}")
    print(f"📁 Файл сохранён: {OUTPUT_FILE}")
    print()

    # Разбивка по категориям
    print("=" * 60)
    print("По категориям:")
    print("=" * 60)
    by_cat: dict = {}
    for a in artefacts:
        by_cat.setdefault(a["category"], []).append(a)
    for cat in sorted(by_cat.keys()):
        print(f"  {cat}: {len(by_cat[cat])} шт.")

    # Разбивка по качеству
    print()
    print("=" * 60)
    print("По качеству:")
    print("=" * 60)
    by_q: dict = {}
    for a in artefacts:
        by_q.setdefault(a["quality"], []).append(a)
    for q in sorted(by_q.keys()):
        print(f"  {q}: {len(by_q[q])} шт.")

    # Полный список — на экран
    print()
    print("=" * 60)
    print("Полный список артефактов:")
    print("=" * 60)
    for a in artefacts:
        print(f"  [{a['id']:>5}] {a['name']:<35} | {a['quality']:<15} | {a['category']}")


if __name__ == "__main__":
    parse_artefacts()