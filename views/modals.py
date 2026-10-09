import discord
import subscriptions as subs_db
from config import RARITIES, RARITY_COLORS
from user_settings import get_or_create_user_channels


def _build_market_warning(price: int, prices: list) -> str | None:
    if not prices:
        return None
    min_price = min(prices)
    if price < min_price:
        return (
            f"⚠️ Порог **{price:,} ₽** ниже минимальной цены на рынке "
            f"(**{min_price:,} ₽**). Уведомления не будут приходить."
        )
    return None


class PriceModal(discord.ui.Modal, title="Указание порога цены"):
    def __init__(self, item, prices: list | None = None):
        super().__init__()
        self.item = item
        self.prices = prices or []

        if self.prices:
            placeholder = "Топ-3: " + " · ".join(f"{p:,}₽" for p in self.prices)
            label = f"Макс. цена (мин {self.prices[0]:,}₽)"
        else:
            placeholder = "Например: 9000000"
            label = f"Максимальная цена для «{item['name']}»"

        self.price_input = discord.ui.TextInput(
            label=label[:45],
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
            await interaction.response.send_message(
                "❌ Введите только цифры, например: `9000000`.", ephemeral=True
            )
            return

        subs_db.add_sub(
            user_id=interaction.user.id,
            item_id=self.item["id"],
            name=self.item["name"],
            max_price=price,
        )

        control, notify = await get_or_create_user_channels(
            interaction.guild, interaction.user
        )

        embed = discord.Embed(title="✅ Подписка создана", color=discord.Color.green())
        embed.add_field(name="Предмет", value=f"**{self.item['name']}**", inline=False)
        embed.add_field(name="ID", value=f"`{self.item['id']}`", inline=True)
        embed.add_field(name="Порог цены", value=f"**{price:,}** ₽", inline=True)

        if self.prices:
            embed.add_field(
                name="💡 Топ-3 на аукционе",
                value=" · ".join(f"{p:,} ₽" for p in self.prices),
                inline=False,
            )
            warning = _build_market_warning(price, self.prices)
            if warning:
                embed.add_field(name="🚨 Внимание", value=warning, inline=False)

        if notify:
            embed.add_field(
                name="🔔 Канал уведомлений",
                value=notify.mention,
                inline=False,
            )

        embed.set_footer(text="Бот пришлёт уведомление при появлении выгодного лота.")

        from views.subscription_created import SubscriptionCreatedView
        await interaction.response.send_message(
            embed=embed, view=SubscriptionCreatedView(), ephemeral=True
        )


class ArtifactPriceModal(discord.ui.Modal, title="Параметры артефакта"):
    def __init__(self, item, rarity: int, prices: list | None = None):
        super().__init__()
        self.item = item
        self.rarity = rarity
        self.prices = prices or []

        self.refinement_input = discord.ui.TextInput(
            label="Заточка +0…+15 (необязательно)",
            placeholder="Оставьте пустым, если уровень не важен",
            required=False,
            max_length=2,
        )
        self.add_item(self.refinement_input)

        if self.prices:
            placeholder = "Топ-3: " + " · ".join(f"{p:,}₽" for p in self.prices)
            label = f"Макс. цена (мин {self.prices[0]:,}₽)"
        else:
            placeholder = "Нет активных лотов этой редкости"
            label = "Максимальная цена"

        self.price_input = discord.ui.TextInput(
            label=label[:45],
            placeholder=placeholder[:100],
            required=True,
            max_length=20,
        )
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        refinement = None
        ref_raw = self.refinement_input.value.strip()
        if ref_raw:
            try:
                refinement = int(ref_raw)
                if not (0 <= refinement <= 15):
                    raise ValueError
            except ValueError:
                await interaction.response.send_message(
                    "❌ Заточка должна быть 0–15.", ephemeral=True
                )
                return

        raw = self.price_input.value.replace(" ", "").replace(",", "").replace(".", "")
        try:
            price = int(raw)
        except ValueError:
            await interaction.response.send_message(
                "❌ Цена — только цифры.", ephemeral=True
            )
            return

        subs_db.add_sub(
            user_id=interaction.user.id,
            item_id=self.item["id"],
            name=self.item["name"],
            max_price=price,
            rarity=self.rarity,
            refinement=refinement,
        )

        control, notify = await get_or_create_user_channels(
            interaction.guild, interaction.user
        )

        embed = discord.Embed(
            title="✅ Подписка на артефакт создана",
            color=RARITY_COLORS.get(self.rarity, discord.Color.green()),
        )
        embed.add_field(name="Предмет", value=f"**{self.item['name']}**", inline=False)
        embed.add_field(name="ID", value=f"`{self.item['id']}`", inline=True)
        embed.add_field(
            name="Редкость",
            value=f"**{RARITIES[self.rarity]}** (`{self.rarity}`)",
            inline=True,
        )
        if refinement is not None:
            embed.add_field(name="Заточка", value=f"**+{refinement}**", inline=True)
        else:
            embed.add_field(name="Заточка", value="*любая*", inline=True)
        embed.add_field(name="Порог цены", value=f"**{price:,}** ₽", inline=False)

        if self.prices:
            embed.add_field(
                name="💡 Топ-3 на аукционе",
                value=" · ".join(f"{p:,} ₽" for p in self.prices),
                inline=False,
            )

        if notify:
            embed.add_field(
                name="🔔 Канал уведомлений",
                value=notify.mention,
                inline=False,
            )

        embed.set_footer(text="Бот пришлёт уведомление при появлении выгодного лота.")

        from views.subscription_created import SubscriptionCreatedView
        await interaction.response.send_message(
            embed=embed, view=SubscriptionCreatedView(), ephemeral=True
        )