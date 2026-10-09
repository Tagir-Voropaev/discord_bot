import discord
import asyncio
import json
import os

from config import RARITIES, RARITY_EMOJI
import api_client

AUCTION_FEE = 0.05
META_FILE = "meta_items.json"
CONCURRENCY = 5
BATCH_DELAY = 0.1
MAX_PRICE_RATIO = 3.0   # если sell > buy * 3 — считаем разными заточками


def _load_meta():
    if not os.path.exists(META_FILE):
        return {"artefacts": [], "gear": []}
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _find_best_deal(lots):
    """Ищет лучшую сделку, отсеивая пары с подозрительным разбросом цен."""
    by_group: dict = {}
    for lot in lots:
        p = lot.get("buyout_price", 0)
        if p <= 0:
            continue
        key = (lot.get("qlt"), lot.get("ptn"))
        by_group.setdefault(key, []).append(lot)

    best = None
    for key, g_lots in by_group.items():
        g_lots.sort(key=lambda x: x["buyout_price"])
        if len(g_lots) < 2:
            continue

        buy_lot = g_lots[0]
        buy = buy_lot["buyout_price"]

        # Ищем следующую "разумную" цену в группе
        sell = None
        for candidate in g_lots[1:]:
            cand_price = candidate["buyout_price"]
            if cand_price <= 0:
                continue
            ratio = cand_price / buy if buy > 0 else 0
            if ratio > MAX_PRICE_RATIO:
                # Слишком большой разброс — вероятно, разные заточки
                continue
            sell = cand_price
            break

        if sell is None:
            continue

        after_fee = int(sell * (1 - AUCTION_FEE))
        profit = after_fee - buy
        if profit <= 0:
            continue

        qlt, ptn = key
        candidate = {
            "qlt": qlt, "ptn": ptn,
            "buy": buy, "sell": sell, "after_fee": after_fee,
            "profit": profit,
            "profit_pct": profit / buy * 100 if buy > 0 else 0,
        }
        if best is None or candidate["profit"] > best["profit"]:
            best = candidate
    return best


async def _fetch_one(item):
    try:
        lots = await api_client.get_lots(item["id"])
    except Exception as e:
        print(f"[meta] Ошибка {item['id']} ({item['name']}): {e}")
        return item, None

    if not lots:
        return item, None

    best = _find_best_deal(lots)
    if best:
        best["id"] = item["id"]
        best["name"] = item["name"]
    return item, best


async def scan_meta_artefacts(progress_callback=None):
    meta = _load_meta()
    items = meta.get("artefacts", [])
    if not items:
        return []

    all_deals = []
    total = len(items)

    for i in range(0, total, CONCURRENCY):
        batch = items[i:i + CONCURRENCY]
        results = await asyncio.gather(
            *[_fetch_one(it) for it in batch],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                print(f"[meta] Исключение: {r}")
                continue
            item, best = r
            if best:
                all_deals.append(best)

        done = min(i + CONCURRENCY, total)
        print(f"[meta] Прогресс: {done}/{total} · найдено: {len(all_deals)}")

        if progress_callback:
            try:
                await progress_callback(done, total, len(all_deals))
            except Exception as e:
                print(f"[meta] progress_callback err: {e}")

        await asyncio.sleep(BATCH_DELAY)

    all_deals.sort(key=lambda x: x["profit"], reverse=True)
    return all_deals


def _rarity_label(qlt):
    if qlt is None:
        return "📦 Без редкости"
    emoji = RARITY_EMOJI.get(qlt, "?")
    name = RARITIES.get(qlt, f"qlt={qlt}")
    return f"{emoji} {name}"


def build_meta_embed(deals, title="🔥 Топ-10 мета-артефактов"):
    embed = discord.Embed(
        title=title,
        description=(
            "Самые выгодные сделки в **рублях** (после комиссии 5%).\n"
            f"Всего прибыльных предметов: **{len(deals)}**"
        ),
        color=discord.Color.orange(),
    )

    medals = ["🥇", "🥈", "🥉"]
    for i, d in enumerate(deals[:10]):
        rank = medals[i] if i < 3 else f"#{i+1}"
        ptn_str = f" +{d['ptn']}" if d["ptn"] is not None else ""
        name = f"{rank} {d['name']} — {_rarity_label(d['qlt'])}{ptn_str}"

        value = (
            f"💰 Купить за **{d['buy']:,} ₽**\n"
            f"📈 Продать за **{d['sell']:,} ₽** "
            f"(−5% = {d['after_fee']:,})\n"
            f"💎 **Прибыль: +{d['profit']:,} ₽** ({d['profit_pct']:+.1f}%)"
        )
        embed.add_field(name=name[:256], value=value[:1024], inline=False)

    embed.set_footer(text="Обновлено только что · Сортировка по прибыли в ₽")
    return embed


class MetaArtefactsView(discord.ui.View):
    def __init__(self, deals):
        super().__init__(timeout=300)
        self.deals = deals

        if deals:
            options = []
            for d in deals[:10]:
                ptn_str = f" +{d['ptn']}" if d["ptn"] is not None else ""
                options.append(
                    discord.SelectOption(
                        label=f"{d['name']} {_rarity_label(d['qlt'])}{ptn_str}"[:100],
                        value=d["id"],
                        description=f"+{d['profit']:,} ₽"[:100],
                    )
                )
            select = discord.ui.Select(
                placeholder="📦 Выбрать артефакт для анализа…",
                options=options,
                row=0,
            )
            select.callback = self.on_select
            self.add_item(select)

        back_btn = discord.ui.Button(
            label="← Назад",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_btn.callback = self.on_back
        self.add_item(back_btn)

    async def on_select(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        deal = next((d for d in self.deals if d["id"] == item_id), None)
        if not deal:
            return

        from views.market_view import MarketAnalysisView, build_analysis_embed

        await interaction.response.defer(ephemeral=True)

        item = {"id": deal["id"], "name": deal["name"]}
        lots = await api_client.get_lots(item_id) or []
        history = await api_client.get_price_history(item_id, limit=100) or []

        embed = build_analysis_embed(item, lots, history)
        await interaction.followup.send(
            embed=embed,
            view=MarketAnalysisView(item, lots, history),
            ephemeral=True,
        )

    async def on_back(self, interaction: discord.Interaction):
        from views.navigation import CategoryView
        embed = discord.Embed(
            title="📂 Выберите действие",
            description=(
                "🔍 **Поиск** — найти конкретный предмет\n"
                "🍀 **Мета-артефакты** — топ выгодных сделок\n"
                "⚔️ **Мета-шмот** — топ выгодных сделок по шмоту\n"
                "📂 **Категории** — все предметы по группам"
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())