import discord
from config import MAIN_CATEGORIES
from items_db import ALL_ITEMS, get_main_category
from views.market_view import MarketAnalysisView, build_analysis_embed
import api_client


class SearchModal(discord.ui.Modal, title="Поиск предмета"):
    def __init__(self, category_filter: str | None = None):
        super().__init__()
        self.category_filter = category_filter
        label = "Введите часть названия"
        if category_filter:
            cat_name = MAIN_CATEGORIES.get(category_filter, category_filter)
            label = f"Поиск в «{cat_name[:40]}»"

        self.query_input = discord.ui.TextInput(
            label=label[:45],
            placeholder="Например: Five-seveN, АК, Браслет…",
            required=True,
            max_length=50,
        )
        self.add_item(self.query_input)

    async def on_submit(self, interaction: discord.Interaction):
        query = self.query_input.value.strip().lower()
        if len(query) < 2:
            await interaction.response.send_message(
                "❌ Минимум 2 символа.", ephemeral=True
            )
            return

        words = query.split()
        matches = []
        seen_names = set()
        seen_ids = set()

        for item in ALL_ITEMS:
            if "_variants" in item["category"]:
                continue
            if self.category_filter:
                if get_main_category(item["category"]) != self.category_filter:
                    continue
            name_lower = item["name"].lower()
            if (
                all(w in name_lower for w in words)
                and item["name"] not in seen_names
                and item["id"] not in seen_ids
            ):
                seen_names.add(item["name"])
                seen_ids.add(item["id"])
                matches.append(item)
            if len(matches) >= 25:
                break

        if not matches:
            await interaction.response.send_message(
                f"🔍 Ничего не найдено по «{self.query_input.value}».",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"🔍 {self.query_input.value}",
            description=f"Найдено: **{len(matches)}**. Выберите предмет:",
            color=discord.Color.green(),
        )
        view = SearchResultView(matches, category_filter=self.category_filter)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class SearchResultView(discord.ui.View):
    def __init__(self, matches, category_filter: str | None = None):
        super().__init__(timeout=300)
        self.matches = matches

        options = [
            discord.SelectOption(
                label=item["name"][:100],
                value=item["id"],
                description=MAIN_CATEGORIES[get_main_category(item["category"])][:100],
            )
            for item in matches
        ]
        select = discord.ui.Select(
            placeholder="📦 Выберите предмет…",
            options=options,
            row=0,
        )
        select.callback = self.on_item
        self.add_item(select)

        back_menu = discord.ui.Button(
            label="← В главное меню",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_menu.callback = self.on_back_menu
        self.add_item(back_menu)

        back_cat = discord.ui.Button(
            label="📂 К категориям",
            style=discord.ButtonStyle.primary,
            row=1,
        )
        back_cat.callback = self.on_back_categories
        self.add_item(back_cat)

    async def on_item(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = next(i for i in self.matches if i["id"] == item_id)

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

    async def on_back_menu(self, interaction: discord.Interaction):
        from views.main_menu import MainMenuView

        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())

    async def on_back_categories(self, interaction: discord.Interaction):
        from views.navigation import CategoryView

        embed = discord.Embed(
            title="📂 Выбор категории",
            description="Выберите категорию предметов:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())