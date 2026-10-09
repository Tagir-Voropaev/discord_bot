import discord
from config import MAIN_CATEGORIES
from items_db import GROUPED_ITEMS
from views.market_view import MarketAnalysisView, build_analysis_embed
from views.search_view import SearchModal
import api_client


class CategoryView(discord.ui.View):
    def __init__(self, with_back: bool = True):
        super().__init__(timeout=300)

        # Row 0: поиск + мета-кнопки
        search_btn = discord.ui.Button(
            label="Поиск предмета",
            style=discord.ButtonStyle.success,
            emoji="🔍",
            row=0,
        )
        search_btn.callback = self.on_search
        self.add_item(search_btn)

        meta_art_btn = discord.ui.Button(
            label="Мета-артефакты",
            style=discord.ButtonStyle.danger,
            emoji="🍀",
            row=0,
        )
        meta_art_btn.callback = self.on_meta_artefacts
        self.add_item(meta_art_btn)

        meta_gear_btn = discord.ui.Button(
            label="Мета-шмот",
            style=discord.ButtonStyle.danger,
            emoji="⚔️",
            row=0,
        )
        meta_gear_btn.callback = self.on_meta_gear
        self.add_item(meta_gear_btn)

        # Row 1: категории
        options = [
            discord.SelectOption(label=name, value=key)
            for key, name in MAIN_CATEGORIES.items()
        ]
        select = discord.ui.Select(
            placeholder="📂 Выберите категорию предметов…",
            options=options,
            row=1,
        )
        select.callback = self.on_category
        self.add_item(select)

        # Row 2: назад
        if with_back:
            back_btn = discord.ui.Button(
                label="← В главное меню",
                style=discord.ButtonStyle.secondary,
                row=2,
            )
            back_btn.callback = self.on_back
            self.add_item(back_btn)

    async def on_search(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SearchModal())

    async def on_meta_artefacts(self, interaction: discord.Interaction):
        await interaction.response.defer()

        async def progress(done, total, found):
            try:
                embed = discord.Embed(
                    title="🍀 Сканирую мета-артефакты…",
                    description=(
                        f"Прогресс: **{done}/{total}**\n"
                        f"Найдено прибыльных: **{found}**"
                    ),
                    color=discord.Color.orange(),
                )
                await interaction.edit_original_response(embed=embed)
            except Exception:
                pass

        try:
            from views.meta_view import (
                scan_meta_artefacts, build_meta_embed, MetaArtefactsView,
            )
            deals = await scan_meta_artefacts(progress_callback=progress)

            if not deals:
                embed = discord.Embed(
                    title="😕 Выгодных предложений нет",
                    description="По всем мета-артефактам сейчас нет прибыльных сделок.",
                    color=discord.Color.orange(),
                )
                await interaction.edit_original_response(embed=embed, view=CategoryView())
                return

            embed = build_meta_embed(deals)
            await interaction.edit_original_response(
                embed=embed, view=MetaArtefactsView(deals)
            )
        except Exception as e:
            print(f"[meta] Ошибка: {e}")
            import traceback
            traceback.print_exc()
            embed = discord.Embed(
                title="❌ Ошибка",
                description=f"`{e}`",
                color=discord.Color.red(),
            )
            await interaction.edit_original_response(embed=embed, view=CategoryView())

    async def on_meta_gear(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Мета-шмот",
            description=(
                "Список мета-шмота пока не задан.\n"
                "Пришлите названия — я найду ID и добавлю."
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())

    async def on_category(self, interaction: discord.Interaction):
        main_cat_key = interaction.data["values"][0]
        items_in_cat = GROUPED_ITEMS[main_cat_key]
        if not items_in_cat:
            await interaction.response.send_message("Категория пуста.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{MAIN_CATEGORIES[main_cat_key]}",
            description=(
                f"Найдено предметов: **{len(items_in_cat)}**\n"
                "Выберите предмет или воспользуйтесь поиском:"
            ),
            color=discord.Color.blurple(),
        )
        view = ItemView(items_in_cat, page=0, main_cat_key=main_cat_key)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_back(self, interaction: discord.Interaction):
        from views.main_menu import MainMenuView
        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())


class ItemView(discord.ui.View):
    def __init__(self, items, page, main_cat_key):
        super().__init__(timeout=300)

        seen = set()
        unique_items = []
        for it in items:
            if it["id"] not in seen:
                seen.add(it["id"])
                unique_items.append(it)

        self.items = unique_items
        self.page = page
        self.main_cat_key = main_cat_key

        start = page * 25
        chunk = self.items[start:start + 25]

        options = [
            discord.SelectOption(label=item["name"][:100], value=item["id"])
            for item in chunk
        ]
        select = discord.ui.Select(
            placeholder=f"📦 Предметы {start+1}–{start+len(chunk)} из {len(self.items)}",
            options=options,
            row=0,
        )
        select.callback = self.on_item
        self.add_item(select)

        total_pages = (len(self.items) + 24) // 25
        if page > 0:
            prev_btn = discord.ui.Button(
                label="◀ Назад", style=discord.ButtonStyle.secondary, row=1
            )
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

        if page + 1 < total_pages:
            next_btn = discord.ui.Button(
                label="Вперёд ▶", style=discord.ButtonStyle.secondary, row=1
            )
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        search_btn = discord.ui.Button(
            label="🔍 Поиск в категории",
            style=discord.ButtonStyle.success,
            row=2,
        )
        search_btn.callback = self.on_search_in_category
        self.add_item(search_btn)

        back_btn = discord.ui.Button(
            label="📂 К категориям",
            style=discord.ButtonStyle.primary,
            row=2,
        )
        back_btn.callback = self.back_to_categories
        self.add_item(back_btn)

    async def on_item(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = next(i for i in self.items if i["id"] == item_id)

        loading = discord.Embed(
            title=f"📦 {item['name']}",
            description="⏳ Загружаю цены и историю продаж…",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=loading, view=None)

        lots = await api_client.get_lots(item["id"]) or []
        history = await api_client.get_price_history(item["id"], limit=100) or []

        embed = build_analysis_embed(item, lots, history)
        await interaction.edit_original_response(
            embed=embed, view=MarketAnalysisView(item, lots, history)
        )

    async def on_search_in_category(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SearchModal(self.main_cat_key))

    async def prev_page(self, interaction: discord.Interaction):
        view = ItemView(self.items, self.page - 1, self.main_cat_key)
        await interaction.response.edit_message(view=view)

    async def next_page(self, interaction: discord.Interaction):
        view = ItemView(self.items, self.page + 1, self.main_cat_key)
        await interaction.response.edit_message(view=view)

    async def back_to_categories(self, interaction: discord.Interaction):
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