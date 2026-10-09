import discord
import subscriptions as subs_db
from config import RARITIES


class SubscriptionListView(discord.ui.View):
    def __init__(self, user_id: int, with_back: bool = False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.with_back = with_back
        self.selected_item_id: str | None = None

        subs = subs_db.get_user_subs(user_id)
        if not subs:
            return

        options = []
        for s in subs[:25]:
            if s.get("mode") == "smart" or s.get("max_price") is None:
                desc = "🔥 Умный режим (любая редкость)"
            else:
                desc = f"💰 Порог: {s['max_price']:,} ₽"
            options.append(discord.SelectOption(
                label=s["name"][:100],
                value=s["item_id"],
                description=desc[:100],
            ))

        select = discord.ui.Select(
            placeholder="📋 Выберите подписку…",
            options=options,
            row=0,
        )
        select.callback = self.on_select
        self.add_item(select)

        self.btn_edit = discord.ui.Button(
            label="Изменить", style=discord.ButtonStyle.primary,
            emoji="✏️", row=1, disabled=True,
        )
        self.btn_edit.callback = self.on_edit
        self.add_item(self.btn_edit)

        self.btn_delete = discord.ui.Button(
            label="Удалить", style=discord.ButtonStyle.danger,
            emoji="🗑️", row=1, disabled=True,
        )
        self.btn_delete.callback = self.on_delete
        self.add_item(self.btn_delete)

        if with_back:
            btn_back = discord.ui.Button(
                label="← Назад", style=discord.ButtonStyle.secondary, row=2,
            )
            btn_back.callback = self.on_back
            self.add_item(btn_back)

    async def on_back(self, interaction: discord.Interaction):
        from views.main_menu import MainMenuView
        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())

    async def on_select(self, interaction: discord.Interaction):
        self.selected_item_id = interaction.data["values"][0]
        self.btn_edit.disabled = False
        self.btn_delete.disabled = False
        await interaction.response.edit_message(view=self)

    async def on_delete(self, interaction: discord.Interaction):
        if not self.selected_item_id:
            return
        subs_db.remove_sub(self.user_id, self.selected_item_id)
        subs = subs_db.get_user_subs(self.user_id)
        if not subs:
            embed = discord.Embed(
                title="🗑️ Все подписки удалены",
                description="Нажмите **🔔 Отслеживать**, чтобы создать новую.",
                color=discord.Color.orange(),
            )
            from views.main_menu import BackToMenuView
            await interaction.response.edit_message(embed=embed, view=BackToMenuView())
            return
        embed = discord.Embed(
            title="📋 Ваши подписки",
            description="Подписка удалена. Выберите другую или вернитесь в меню.",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(
            embed=embed, view=SubscriptionListView(self.user_id, with_back=True)
        )

    async def on_edit(self, interaction: discord.Interaction):
        if not self.selected_item_id:
            return
        subs = subs_db.get_user_subs(self.user_id)
        sub = next((s for s in subs if s["item_id"] == self.selected_item_id), None)
        if not sub:
            await interaction.response.send_message("Подписка не найдена.", ephemeral=True)
            return
        await interaction.response.send_modal(EditSubscriptionModal(sub))


class EditSubscriptionModal(discord.ui.Modal, title="Изменение подписки"):
    def __init__(self, sub: dict):
        super().__init__()
        self.sub = sub

        current_mode = sub.get("mode", "smart")
        if current_mode == "smart" or sub.get("max_price") is None:
            default_price = ""
        else:
            default_price = str(sub["max_price"])

        self.price_input = discord.ui.TextInput(
            label="Порог цены (пусто — умный режим)",
            placeholder="Оставьте пустым для умного режима (любая редкость)",
            required=False,
            default=default_price,
            max_length=20,
        )
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw = self.price_input.value.strip()
        if not raw:
            # Умный режим
            import subscriptions as subs_db
            subs_db.add_sub(
                user_id=interaction.user.id,
                item_id=self.sub["item_id"],
                name=self.sub["name"],
                max_price=None,
                mode="smart",
            )
            embed = discord.Embed(
                title="✅ Умный режим включён",
                description=f"«{self.sub['name']}» — уведомления на выгодные лоты любой редкости.",
                color=discord.Color.green(),
            )
        else:
            try:
                price = int(raw.replace(" ", "").replace(",", "").replace(".", ""))
            except ValueError:
                await interaction.response.send_message("❌ Только цифры.", ephemeral=True)
                return
            import subscriptions as subs_db
            subs_db.add_sub(
                user_id=interaction.user.id,
                item_id=self.sub["item_id"],
                name=self.sub["name"],
                max_price=price,
                mode="fixed",
            )
            embed = discord.Embed(
                title="✅ Подписка обновлена",
                description=f"«{self.sub['name']}» — порог {price:,} ₽.",
                color=discord.Color.green(),
            )

        from views.main_menu import BackToMenuView
        embed.set_footer(text="→ Возврат в главное меню")
        await interaction.response.edit_message(embed=embed, view=BackToMenuView())