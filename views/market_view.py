import discord
import statistics
from datetime import datetime, timezone
from config import RARITIES, RARITY_EMOJI

AUCTION_FEE = 0.05
RECENT_SALES_COUNT = 5
OUTLIER_IQR_MULT = 2.0
MIN_PRICE_FOR_ANALYSIS = 500_000

LOWER_FALLBACK_MULT = 0.3
UPPER_FALLBACK_MULT = 3.0

DIVIDER = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"


def _group_key(lot):
    return (lot.get("qlt"), lot.get("ptn"))


def _group_name(key):
    qlt, ptn = key
    if qlt is None:
        q_part = "📦 Без редкости"
    else:
        emoji = RARITY_EMOJI.get(qlt, "?")
        name = RARITIES.get(qlt, f"qlt={qlt}")
        q_part = f"{emoji} {name}"
    if ptn is None:
        return q_part
    return f"{q_part} +{ptn}"


def _format_time(t) -> str:
    """Превращает time (datetime или str) в компактный формат 'DD.MM HH:MM'."""
    if t is None:
        return "?"

    dt = None
    if isinstance(t, datetime):
        dt = t
    elif isinstance(t, str):
        # Форматы: '2026-10-09T14:55:14Z' или '2026-10-09 14:55:14+00:00'
        s = t.replace("Z", "+00:00")
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue

    if dt is None:
        return "?"

    # Переводим в UTC+3 (МСК)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    msk = dt.astimezone(timezone.utc).astimezone(
        timezone(offset=__import__("datetime").timedelta(hours=3))
    )
    return msk.strftime("%d.%m %H:%M")


def _filter_group_keys(group_stats: dict) -> list:
    by_rarity: dict = {}
    for (qlt, ptn) in group_stats.keys():
        by_rarity.setdefault(qlt, []).append(ptn)

    kept = set()
    for qlt, ptns in by_rarity.items():
        cheapest = min(group_stats[(qlt, ptn)]["min_price"] for ptn in ptns)
        if cheapest < MIN_PRICE_FOR_ANALYSIS:
            continue

        for ptn_check in (0, 15):
            if ptn_check in ptns:
                kept.add((qlt, ptn_check))

        min_p = min(group_stats[(qlt, ptn)]["min_price"] for ptn in ptns)
        for ptn in ptns:
            if group_stats[(qlt, ptn)]["min_price"] == min_p:
                kept.add((qlt, ptn))

    return list(kept)


def _remove_outliers(records: list) -> tuple[list, list]:
    """records — список dict с 'price'. Возвращает (cleaned, outliers)."""
    if len(records) < 4:
        return list(records), []

    sorted_r = sorted(records, key=lambda r: r["price"])
    prices = [r["price"] for r in sorted_r]

    q1 = prices[len(prices) // 4]
    q3 = prices[(3 * len(prices)) // 4]
    iqr = q3 - q1

    if iqr == 0:
        return sorted_r, []

    low = q1 - OUTLIER_IQR_MULT * iqr
    high = q3 + OUTLIER_IQR_MULT * iqr
    cleaned = [r for r in sorted_r if low <= r["price"] <= high]
    outliers = [r for r in sorted_r if r["price"] < low or r["price"] > high]
    return cleaned, outliers


def _build_price_bounds(group_min_prices: dict) -> dict:
    items = sorted(group_min_prices.items(), key=lambda kv: kv[1])
    n = len(items)
    bounds = {}

    for i, (key, price) in enumerate(items):
        if i == 0:
            low = price * LOWER_FALLBACK_MULT
        else:
            prev_price = items[i - 1][1]
            low = (prev_price + price) / 2

        if i == n - 1:
            high = price * UPPER_FALLBACK_MULT
        else:
            next_price = items[i + 1][1]
            high = (price + next_price) / 2

        bounds[key] = (low, high)

    return bounds


def analyze_market(lots, history=None):
    valid = [l for l in lots if l.get("buyout_price", 0) > 0]
    if not valid:
        return {"ok": False, "reason": "Нет активных лотов",
                "by_group": {}, "group_stats": {}, "deals": []}

    by_group: dict = {}
    for lot in valid:
        by_group.setdefault(_group_key(lot), []).append(lot)
    for key in by_group:
        by_group[key].sort(key=lambda x: x["buyout_price"])

    group_min = {key: lots_g[0]["buyout_price"] for key, lots_g in by_group.items()}
    bounds = _build_price_bounds(group_min)

    # Сохраняем полные записи истории (price + time)
    all_hist = []
    for h in (history or []):
        p = h.get("price", 0)
        if p <= 0:
            continue
        all_hist.append({
            "price": p,
            "time": h.get("time"),
            "amount": h.get("amount", 1),
        })

    group_stats = {}
    deals = []

    for key, g_lots in by_group.items():
        min_active = g_lots[0]["buyout_price"]
        low, high = bounds.get(key, (min_active * 0.5, min_active * 2))

        cluster = [r for r in all_hist if low <= r["price"] <= high]
        cleaned, outliers = _remove_outliers(cluster)

        # Сортируем по времени (сначала старые, потом новые)
        # Так как в API записи идут от старых к новым — берём последние N
        last_N = cleaned[-RECENT_SALES_COUNT:] if cleaned else []

        avg_sold = (
            int(sum(r["price"] for r in last_N) / len(last_N))
            if last_N else None
        )

        profit = None
        profit_pct = None
        if avg_sold is not None:
            after_fee = int(avg_sold * (1 - AUCTION_FEE))
            profit = after_fee - min_active
            profit_pct = profit / min_active * 100 if min_active > 0 else 0

        group_stats[key] = {
            "count": len(g_lots),
            "min_price": min_active,
            "avg_sold": avg_sold,
            "last_5": last_N,   # список dict'ов с price/time
            "removed_outliers": len(outliers),
            "profit": profit,
            "profit_pct": profit_pct,
            "top3": g_lots[:3],
            "max_price": g_lots[-1]["buyout_price"],
            "bounds": (int(low), int(high)),
        }

        if profit is not None and profit > 0:
            deals.append({
                "key": key,
                "min_price": min_active,
                "avg_sold": avg_sold,
                "profit": profit,
                "profit_pct": profit_pct,
            })

    deals.sort(key=lambda x: x["profit"], reverse=True)

    return {
        "ok": True, "valid_count": len(valid),
        "by_group": by_group, "group_stats": group_stats, "deals": deals,
    }


def _build_group_value(s):
    lines = []
    for i, lot in enumerate(s["top3"], 1):
        p = lot["buyout_price"]
        lines.append(f"`#{i}` **{p:,} ₽**")
    if s["count"] > 3:
        lines.append(f"*…до {s['max_price']:,} ₽*")

    low, high = s["bounds"]
    lines.append(f"\n📏 Диапазон истории: **{low:,}** – **{high:,}** ₽")

    if s["last_5"]:
        avg = s["avg_sold"]
        lines.append(f"\n📜 Последние {len(s['last_5'])} продаж в диапазоне:")
        # Показываем от новых к старым (переворачиваем)
        for r in reversed(s["last_5"]):
            time_str = _format_time(r.get("time"))
            lines.append(f"  • **{r['price']:,} ₽** — {time_str}")

        if s["removed_outliers"] > 0:
            lines.append(f"\n🧹 Удалено выбросов: **{s['removed_outliers']}**")
        lines.append(f"➡️ Средняя: **{avg:,} ₽**")
    else:
        lines.append("\n📜 Нет продаж в этом диапазоне")

    if s["profit"] is not None:
        if s["profit"] > 0:
            lines.append(
                f"\n✅ **Выгодно!** Купить за {s['min_price']:,} ₽ "
                f"→ средняя {s['avg_sold']:,} ₽\n"
                f"💰 **Прибыль: +{s['profit']:,} ₽** ({s['profit_pct']:+.1f}%)"
            )
        else:
            lines.append(
                f"\n❌ **Невыгодно** · убыток **{s['profit']:,} ₽** "
                f"({s['profit_pct']:+.1f}%)"
            )
    else:
        lines.append("\n⚠️ Нет данных для расчёта")

    return "\n".join(lines)


def build_analysis_embed(item, lots, history=None):
    a = analyze_market(lots, history)
    embed = discord.Embed(title=f"📊 Анализ рынка: {item['name']}",
                          color=discord.Color.blurple())

    if not a["ok"]:
        embed.description = f"❌ {a['reason']}"
        return embed

    kept_keys = set(_filter_group_keys(a["group_stats"]))
    hist_count = len(history) if history else 0

    embed.description = (
        f"📦 **{a['valid_count']}** лотов · групп: **{len(kept_keys)}**\n"
        f"📜 История продаж: **{hist_count}** записей\n"
        f"🕒 Время указано в МСК (UTC+3)"
    )

    def sort_key(k):
        qlt, ptn = k
        if ptn == 0:
            ptn_order = 0
        elif ptn == 15:
            ptn_order = 1
        elif ptn is None:
            ptn_order = 2
        else:
            ptn_order = 3
        return (
            qlt is None,
            qlt if qlt is not None else 999,
            ptn_order,
            ptn if ptn is not None else 0,
        )

    sorted_keys = sorted(kept_keys, key=sort_key)
    MAX_GROUP_FIELDS = 22
    selected = sorted_keys[:MAX_GROUP_FIELDS]
    hidden = len(sorted_keys) - len(selected)

    if not selected:
        embed.add_field(
            name="😕 Нет групп с ценой ≥ 500 000 ₽",
            value="Все активные лоты дешевле указанного порога.",
            inline=False,
        )

    for idx, key in enumerate(selected):
        s = a["group_stats"][key]
        name = _group_name(key)
        value = _build_group_value(s)

        if idx < len(selected) - 1:
            value += f"\n\n{DIVIDER}"

        embed.add_field(
            name=f"───── {name} — {s['count']} шт. ─────"[:256],
            value=value[:1024],
            inline=False,
        )

    footer = (
        f"Комиссия: 5% · Границы групп · "
        f"Мин. порог {MIN_PRICE_FOR_ANALYSIS:,} ₽"
    )
    if hidden > 0:
        footer += f" · Показано {len(selected)} из {len(sorted_keys)}"
    embed.set_footer(text=footer)
    return embed


class MarketAnalysisView(discord.ui.View):
    def __init__(self, item, lots, history=None):
        super().__init__(timeout=300)
        self.item = item
        self.lots = lots
        self.history = history
        self.analysis = analyze_market(lots, history)

        smart_btn = discord.ui.Button(
            label="Ловить выгодные",
            style=discord.ButtonStyle.success,
            emoji="🔥",
            row=0,
        )
        smart_btn.callback = self.on_smart
        self.add_item(smart_btn)

        custom_btn = discord.ui.Button(
            label="Своя цена",
            style=discord.ButtonStyle.primary,
            emoji="✏️",
            row=0,
        )
        custom_btn.callback = self.on_custom
        self.add_item(custom_btn)

        back_btn = discord.ui.Button(
            label="← Назад",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_btn.callback = self.on_back
        self.add_item(back_btn)

    async def on_smart(self, interaction: discord.Interaction):
        import subscriptions as subs_db
        subs_db.add_sub(
            user_id=interaction.user.id,
            item_id=self.item["id"],
            name=self.item["name"],
            max_price=None,
            mode="smart",
        )
        embed = discord.Embed(
            title="✅ Умное отслеживание включено",
            description=(
                f"Бот будет присылать уведомления, когда лот «{self.item['name']}» "
                f"будет дешевле средней цены последних продаж на **10%+**. "
                f"Учитываются только лоты дороже {MIN_PRICE_FOR_ANALYSIS:,} ₽."
            ),
            color=discord.Color.green(),
        )
        embed.set_footer(text="Уведомление придёт при появлении выгодного лота.")
        from views.subscription_created import SubscriptionCreatedView
        await interaction.response.edit_message(embed=embed, view=SubscriptionCreatedView())

    async def on_custom(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomPriceModal(self.item, self.analysis))

    async def on_back(self, interaction: discord.Interaction):
        from views.navigation import CategoryView
        embed = discord.Embed(
            title="📂 Выберите действие",
            description="Выберите категорию:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())


class CustomPriceModal(discord.ui.Modal, title="Своя цена"):
    def __init__(self, item, analysis):
        super().__init__()
        self.item = item
        self.analysis = analysis
        if analysis.get("ok") and analysis.get("group_stats"):
            all_mins = [s["min_price"] for s in analysis["group_stats"].values()]
            min_price = min(all_mins) if all_mins else 0
            placeholder = f"Мин. по всем группам: {min_price:,}"
        else:
            placeholder = "Например: 7500000"
        self.price_input = discord.ui.TextInput(
            label=f"Порог для «{item['name']}»",
            placeholder=placeholder[:100],
            required=True,
            max_length=20,
        )
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.price_input.value.replace(" ", "").replace(",", "").replace(".", "")
        try:
            price = int(raw)
        except ValueError:
            await interaction.response.send_message("❌ Только цифры.", ephemeral=True)
            return

        import subscriptions as subs_db
        subs_db.add_sub(
            user_id=interaction.user.id,
            item_id=self.item["id"],
            name=self.item["name"],
            max_price=price,
            mode="fixed",
        )

        embed = discord.Embed(title="✅ Подписка создана", color=discord.Color.green())
        embed.add_field(name="Предмет", value=f"**{self.item['name']}**", inline=False)
        embed.add_field(name="Порог цены", value=f"**{price:,}** ₽", inline=True)
        embed.set_footer(text="Бот пришлёт уведомление, когда цена опустится ниже.")
        from views.subscription_created import SubscriptionCreatedView
        await interaction.response.send_message(
            embed=embed, view=SubscriptionCreatedView(), ephemeral=True
        )