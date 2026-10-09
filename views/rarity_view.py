import discord
from config import RARITIES, RARITY_EMOJI
from views.modals import ArtifactPriceModal


class RaritySelectView(discord.ui.View):
    def __init__(self, item, by_qlt: dict):
        super().__init__(timeout=180)
        self.item = item
        self.by_qlt = by_qlt

        options = []
        for num, name in RARITIES.items():
            prices = by_qlt.get(num, [])
            if prices:
                desc = f"от {min(prices):,} ₽"
            else:
                desc = "нет лотов"
            options.append(
                discord.SelectOption(
                    label=f"{num} — {name}",
                    value=str(num),
                    description=desc[:100],
                    emoji=RARITY_EMOJI[num],
                )
            )

        select = discord.ui.Select(
            placeholder="Выберите редкость…",
            options=options,
            row=0,
        )
        select.callback = self.on_rarity
        self.add_item(select)

        back_btn = discord.ui.Button(
            label="← Назад",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        back_btn.callback = self.on_back
        self.add_item(back_btn)

    async def on_rarity(self, interaction: discord.Interaction):
        rarity = int(interaction.data["values"][0])
        prices = self.by_qlt.get(rarity, [])[:3]
        await interaction.response.send_modal(
            ArtifactPriceModal(self.item, rarity, prices)
        )

    async def on_back(self, interaction: discord.Interaction):
        from views.navigation import CategoryView

        embed = discord.Embed(
            title="📂 Выбор категории",
            description="Выберите категорию предметов для отслеживания:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())