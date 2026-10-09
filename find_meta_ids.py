import os
import json

# Список мета-артефактов (как вы прислали)
META_ARTEFACTS = [
    "Атом", "Браслет", "Бубльгум", "Ветка Калины", "Виток", "Вихрь",
    "Гантель", "Гелий", "Ершик", "Жабры", "Жвачка", "Желе", "Жильник",
    "Звено", "Змеиный глаз", "Изюм", "Каблук", "Катушка", "Ледяной ежик",
    "Магма", "Многогранник", "Морозец", "Нервяк", "Обруч", "Опал",
    "Осколок", "Остов", "Петля", "Полено", "Призма", "Проклятая роза",
    "Протоцибуля", "Радиатор", "Роза Изнанки", "Рубик", "Сетчатка",
    "Силки", "Смольник", "Солнце", "Смалец", "Спираль", "Стальной Ежик",
    "Статик", "Темная калина", "Трансформатор", "Тыква", "Улитка",
    "Фаренгейт", "Харя", "Черная дыра", "Чертов еж", "Шишка", "Юла",
]

DB_PATH = "stalzone-database-main/ru/items/artefact"
OUTPUT_FILE = "meta_artefacts.json"


def parse_all_artefacts():
    """Собирает ВСЕ базовые артефакты (без _variants)."""
    artefacts = []
    if not os.path.exists(DB_PATH):
        print(f"❌ Не найдена папка: {DB_PATH}")
        return []

    for root, dirs, files in os.walk(DB_PATH):
        if "_variants" in root:
            continue
        for filename in files:
            if not filename.endswith(".json"):
                continue
            filepath = os.path.join(root, filename)
            item_id = filename[:-5]
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue

            name_block = data.get("name", {})
            name = name_block.get("lines", {}).get("ru")
            if not name:
                continue

            relative = os.path.relpath(root, DB_PATH).replace(os.sep, "/")
            artefacts.append({
                "id": item_id,
                "name": name,
                "category": relative,
            })
    return artefacts


def find_matches(all_artefacts):
    """Ищет ID для каждого мета-артефакта."""
    found = []
    not_found = []
    ambiguous = []

    # Нормализуем имя
    def norm(s):
        return s.lower().strip().replace("ё", "е")

    for meta_name in META_ARTEFACTS:
        meta_norm = norm(meta_name)
        matches = [
            a for a in all_artefacts
            if norm(a["name"]) == meta_norm
        ]

        if len(matches) == 1:
            found.append({
                "id": matches[0]["id"],
                "name": matches[0]["name"],
                "category": matches[0]["category"],
            })
        elif len(matches) > 1:
            ambiguous.append({
                "query": meta_name,
                "matches": matches,
            })
        else:
            # Пробуем частичное совпадение
            partial = [
                a for a in all_artefacts
                if meta_norm in norm(a["name"])
            ]
            if len(partial) == 1:
                found.append({
                    "id": partial[0]["id"],
                    "name": partial[0]["name"],
                    "category": partial[0]["category"],
                })
            elif len(partial) > 1:
                ambiguous.append({
                    "query": meta_name,
                    "matches": partial,
                })
            else:
                not_found.append(meta_name)

    return found, not_found, ambiguous


def main():
    print("🔍 Парсим базу…")
    all_artefacts = parse_all_artefacts()
    print(f"📦 Всего базовых артефактов: {len(all_artefacts)}\n")

    found, not_found, ambiguous = find_matches(all_artefacts)

    # ==== Найденные ====
    print("=" * 70)
    print(f"✅ НАЙДЕНО ({len(found)} из {len(META_ARTEFACTS)})")
    print("=" * 70)
    for a in found:
        print(f"  {a['id']:>6} | {a['name']:<25} | {a['category']}")

    # ==== Неоднозначные ====
    if ambiguous:
        print()
        print("=" * 70)
        print(f"⚠️ НЕОДНОЗНАЧНЫЕ ({len(ambiguous)}) — несколько вариантов:")
        print("=" * 70)
        for item in ambiguous:
            print(f"\n  Запрос: «{item['query']}»")
            for m in item["matches"]:
                print(f"    → {m['id']:>6} | {m['name']:<25} | {m['category']}")

    # ==== Не найдено ====
    if not_found:
        print()
        print("=" * 70)
        print(f"❌ НЕ НАЙДЕНО ({len(not_found)}):")
        print("=" * 70)
        for name in not_found:
            print(f"  {name}")

    # ==== Сохраняем найденные ====
    if found:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(found, f, ensure_ascii=False, indent=2)
        print()
        print(f"💾 Сохранено в {OUTPUT_FILE} — {len(found)} артефактов")


if __name__ == "__main__":
    main()