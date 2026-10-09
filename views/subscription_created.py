import discord


class SubscriptionCreatedView(discord.ui.View):
    """Кнопки навигации после создания/изменения подписки."""

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Ещё подписку",
        style=discord.ButtonStyle.success,
        emoji="🔔",
        custom_id="created_new",
    )
    async def btn_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.navigation import CategoryView

        embed = discord.Embed(
            title="🔔 Отслеживание предмета",
            description="Выберите категорию предметов:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=CategoryView())

    @discord.ui.button(
        label="Мои подписки",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="created_list",
    )
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.subscription_view import SubscriptionListView

        embed = discord.Embed(
            title="📋 Ваши подписки",
            description="Выберите подписку, затем **Изменить** или **Удалить**.",
            color=discord.Color.blurple(),
        )
        view = SubscriptionListView(interaction.user.id, with_back=True)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(
        label="В главное меню",
        style=discord.ButtonStyle.secondary,
        emoji="🎛️",
        custom_id="created_menu",
    )
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.main_menu import MainMenuView

        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())