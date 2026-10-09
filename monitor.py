import asyncio
import time
import statistics
from datetime import datetime, timezone, timedelta
from discord.ext import tasks
import discord

from bot_instance import bot
import subscriptions as subs_db
import user_settings
import api_client
import notification_state
from config import RARITIES, RARITY_EMOJI
from items_db import ALL_ITEMS

# ================== НАСТРОЙКИ ==================
CHECK_INTERVAL_SECONDS = 30
COOLDOWN_SECONDS = 30
TOP_N = 5
DEAL_DISCOUNT = 0.10
SMART_TOP_N_FOR_MEDIAN = 5
NOTIFIED_TTL_HOURS = 24
LOG_CHEAPEST_N = 3
# ================================================

_notified = set()
_last_notified: dict = {}
_last_cleanup = 0.0
_sub_state: dict = {}
_id_cache: dict = {}


def _is_valid_id(item_id: str) -> bool:
    """Реальные ID аукциона — 4+ символа, содержат буквы и цифры.
    Исключаем варианты заточки типа '1', '10', '15'.
    """
    if not item_id:
        return False
    if item_id.isdigit():
        return False  # это вариант заточки (1.json, 10.json)
    return len(item_id) >= 3


def _norm_name(s: str) -> str:
    return (s.lower()
             .replace("«", "")
             .replace("»", "")
             .replace("ё", "е")
             .replace("-", " ")
             .replace("  ", " ")
             .strip())


def _find_all_ids_by_name(name: str) -> list:
    """Находит все реальные ID с таким же названием (без вариантов заточки)."""
    if name in _id_cache:
        return _id_cache[name]

    target = _norm_name(name)
    ids = []
    for it in ALL_ITEMS:
        # Пропускаем варианты заточки
        if "_variants" in it.get("category", ""):
            continue
        if not _is_valid_id(it["id"]):
            continue
        if _norm_name(it["name"]) == target:
            ids.append(it["id"])

    _id_cache[name] = ids
    return ids


async def _delete_old_notification(uid: int):
    channel_id, message_id = notification_state.get_last_message(uid)
    if not channel_id or not message_id:
        return
    try:
        channel = bot.get_channel(channel_id)
        if not channel:
            notification_state.clear_last_message(uid)
            return
        msg = await channel.fetch_message(message_id)
        await msg.delete()
    except discord.NotFound:
        pass
    except Exception as e:
        print(f"[monitor] Не удалось удалить старое: {e}")
    finally:
        notification_state.clear_last_message(uid)


def _cleanup_notified():
    global _notified, _last_cleanup

    now = time.time()
    if now - _last_cleanup < 3600:
        return
    _last_cleanup = now

    cutoff = datetime.now(timezone.utc) - timedelta(hours=NOTIFIED_TTL_HOURS)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    before = len(_notified)
    _notified = {
        k for k in _notified
        if len(k) >= 3 and str(k[2]) >= cutoff_str
    }
    removed = before - len(_notified)
    if removed > 0:
        print(f"[monitor] Очищено старых записей: {removed}")


def _check_subscription_changes(subs: dict):
    global _notified

    changed = []
    current_keys = set()

    for uid, user_subs in subs.items():
        for s in user_subs:
            key = (uid, s["item_id"])
            current_keys.add(key)
            param_hash = (
                s.get("mode", "smart"),
                s.get("max_price"),
                s.get("rarity"),
                s.get("refinement"),
            )
            if key in _sub_state and _sub_state[key] != param_hash:
                changed.append(key)
            _sub_state[key] = param_hash

    for key in list(_sub_state.keys()):
        if key not in current_keys:
            del _sub_state[key]

    if changed:
        before = len(_notified)
        changed_set = set(changed)
        _notified = {
            k for k in _notified
            if (k[0], k[1]) not in changed_set
        }
        removed = before - len(_notified)
        if removed:
            print(
                f"[monitor] Изменились параметры {len(changed)} подписок — "
                f"очищено {removed} записей из кэша"
            )


def _find_smart_deals(lots, history=None):
    by_group: dict = {}
    for lot in lots:
        p = lot.get("buyout_price", 0)
        if p <= 0:
            continue
        key = (lot.get("qlt"), lot.get("ptn"))
        by_group.setdefault(key, []).append(lot)

    hist_by_group: dict = {}
    if history:
        for h in history:
            key = (h.get("qlt"), h.get("ptn"))
            hist_by_group.setdefault(key, []).append(h["price"])
        for key in hist_by_group:
            hist_by_group[key].sort()

    deals = []
    for key, g_lots in by_group.items():
        sold_prices = hist_by_group.get(key, [])
        if sold_prices:
            top_sold = sold_prices[-min(10, len(sold_prices)):]
            baseline = int(statistics.median(top_sold))
            source = "sold"
        else:
            prices = sorted(l["buyout_price"] for l in g_lots)
            if len(prices) < 2:
                continue
            top = prices[: min(SMART_TOP_N_FOR_MEDIAN, len(prices))]
            baseline = int(statistics.median(top))
            source = "active"

        threshold = baseline * (1 - DEAL_DISCOUNT)
        for lot in g_lots:
            if lot["buyout_price"] <= threshold:
                deals.append({
                    "lot": lot,
                    "baseline": baseline,
                    "discount": (baseline - lot["buyout_price"]) / baseline,
                    "source": source,
                })
    return deals


def _find_fixed_matches(lots, max_price: int):
    return [
        {"lot": lot}
        for lot in lots
        if 0 < lot.get("buyout_price", 0) <= max_price
    ]


async def run_check_once():
    _cleanup_notified()

    subs = subs_db.load_subs()
    if not subs:
        return 0

    _check_subscription_changes(subs)

    # Группируем по НАЗВАНИЮ
    names_map: dict[str, list] = {}
    for uid, user_subs in subs.items():
        for s in user_subs:
            names_map.setdefault(s["name"], []).append((uid, s))

    print(f"[monitor] ─── Проверка {len(names_map)} уникальных названий ───")
    now = time.time()
    sent_count = 0

    for name, sub_list in names_map.items():
        ids = _find_all_ids_by_name(name)
        if not ids:
            ids = [sub_list[0][1]["item_id"]]

        # Запрашиваем лоты по всем ID
        all_lots = []
        per_id_counts = []
        for id_ in ids:
            # Пропускаем невалидные ID
            if not _is_valid_id(id_):
                continue
            id_lots = await api_client.get_lots(id_)
            if id_lots:
                all_lots.extend(id_lots)
                per_id_counts.append(f"{id_}:{len(id_lots)}")

        if not all_lots:
            print(f"[monitor] {name}: лотов нет ({len(ids)} ID)")
            continue

        # Дедупликация
        seen = set()
        deduped = []
        for lot in all_lots:
            key = (lot.get("start_time"), lot.get("buyout_price"), lot.get("amount"))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(lot)
        all_lots = deduped

        prices = sorted(l["buyout_price"] for l in all_lots if l["buyout_price"] > 0)
        cheapest = prices[:LOG_CHEAPEST_N] if prices else []
        cheapest_str = " · ".join(f"{p:,} ₽" for p in cheapest)
        ids_str = " · ".join(per_id_counts)
        print(
            f"[monitor] {name}: {len(all_lots)} лотов · {ids_str} · "
            f"дешёвые: {cheapest_str}"
        )

        needs_history = any(s.get("mode", "smart") == "smart" for _, s in sub_list)
        history = None
        if needs_history:
            valid_ids = [i for i in ids if _is_valid_id(i)]
            if valid_ids:
                history = await api_client.get_price_history(valid_ids[0], limit=100)

        for uid, sub in sub_list:
            channel_id = user_settings.get_channel(int(uid))
            if not channel_id:
                continue
            channel = bot.get_channel(channel_id)
            if not channel:
                continue

            cd_key = (uid, sub["item_id"])
            elapsed = int(now - _last_notified.get(cd_key, 0))
            if elapsed < COOLDOWN_SECONDS:
                print(f"[monitor]   {uid}: кулдаун {elapsed}/{COOLDOWN_SECONDS}s")
                continue

            mode = sub.get("mode", "smart")
            if mode == "smart":
                candidates = _find_smart_deals(all_lots, history)
            else:
                candidates = _find_fixed_matches(all_lots, sub.get("max_price") or 0)

            if not candidates:
                if mode == "fixed":
                    print(
                        f"[monitor]   {uid}: 0 кандидатов "
                        f"(все лоты дороже порога {sub.get('max_price', 0):,} ₽)"
                    )
                else:
                    print(f"[monitor]   {uid}: 0 кандидатов (smart-фильтр)")
                continue

            fresh = []
            already = 0
            for c in candidates:
                lot = c["lot"]
                key = (uid, sub["item_id"], lot["start_time"],
                       lot["buyout_price"], lot["amount"])
                if key in _notified:
                    already += 1
                    continue
                fresh.append((c, key))

            if not fresh:
                print(
                    f"[monitor]   {uid}: {already} кандидатов, "
                    f"уже отправлены"
                )
                continue

            fresh.sort(key=lambda x: x[0]["lot"]["buyout_price"])
            top = fresh[:TOP_N]
            for _, key in top:
                _notified.add(key)
            _last_notified[cd_key] = now

            await _delete_old_notification(uid)

            if mode == "smart":
                title = f"🔥 Выгодный лот: {sub['name']}"
                desc = (
                    f"Найдено **{len(fresh)}** лотов на "
                    f"{int(DEAL_DISCOUNT * 100)}%+ ниже медианы продаж."
                )
            else:
                title = f"🔔 Новые лоты: {sub['name']}"
                desc = (
                    f"Найдено **{len(fresh)}** лотов дешевле "
                    f"**{sub.get('max_price', 0):,} ₽**."
                )

            embed = discord.Embed(
                title=title, description=desc,
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc),
            )

            for i, (c, _) in enumerate(top, 1):
                lot = c["lot"]
                q = lot.get("qlt")
                q_emoji = RARITY_EMOJI.get(q, "?") if q is not None else "📦"
                q_name = RARITIES.get(q, "Без редкости") if q is not None else "Без редкости"
                ptn = lot.get("ptn")
                ptn_str = f" +{ptn}" if ptn is not None else ""

                if mode == "smart" and "discount" in c:
                    discount_pct = int(c["discount"] * 100)
                    source_str = "продаж" if c.get("source") == "sold" else "активных"
                    value = (
                        f"{q_emoji} **{q_name}{ptn_str}**\n"
                        f"💰 **{lot['buyout_price']:,} ₽** "
                        f"(-{discount_pct}% от медианы {source_str} "
                        f"{c['baseline']:,} ₽)\n"
                        f"📦 ×{lot['amount']}"
                    )
                else:
                    value = (
                        f"{q_emoji} {q_name}{ptn_str}\n"
                        f"💰 **{lot['buyout_price']:,} ₽**\n"
                        f"📦 ×{lot['amount']}"
                    )

                embed.add_field(
                    name=f"#{i} · {lot['buyout_price']:,} ₽",
                    value=value, inline=False,
                )

            try:
                new_msg = await channel.send(content=f"<@{uid}>", embed=embed)
                notification_state.set_last_message(uid, channel.id, new_msg.id)
                sent_count += 1
                print(f"[monitor]   ✅ Отправлено {uid} — {len(top)} лотов")
            except Exception as e:
                print(f"[monitor]   ❌ Ошибка отправки: {e}")

        await asyncio.sleep(0.3)

    print(f"[monitor] ─── Итог: {sent_count} уведомлений ───")
    return sent_count


def reset_cache():
    global _notified, _last_notified, _sub_state
    _notified.clear()
    _last_notified.clear()
    _sub_state.clear()
    print("[monitor] Кэш сброшен.")


@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def monitor_auction():
    await run_check_once()


@monitor_auction.before_loop
async def before_monitor():
    await bot.wait_until_ready()