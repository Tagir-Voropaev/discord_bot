import discord
from views.navigation import CategoryView
from views.subscription_view import SubscriptionListView
from views.permissions import ensure_channel_permissions
import subscriptions as subs_db


class MainMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Отслеживать предмет",
        style=discord.ButtonStyle.success,
        emoji="🔔",
        custom_id="menu_track",
        row=0,
    )
    async def btn_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🔔 Отслеживание предмета",
            description="Выберите категорию предметов:",
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Панель закроется через 5 минут.")
        await interaction.response.edit_message(embed=embed, view=CategoryView())

    @discord.ui.button(
        label="Мои подписки",
        style=discord.ButtonStyle.primary,
        emoji="📋",
        custom_id="menu_list",
        row=0,
    )
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_subs = subs_db.get_user_subs(interaction.user.id)
        if not user_subs:
            embed = discord.Embed(
                title="📭 Нет подписок",
                description="Нажмите **🔔 Отслеживать предмет**, чтобы создать первую.",
                color=discord.Color.orange(),
            )
            embed.set_footer(text="→ Возврат в главное меню через 30 секунд")
            await interaction.response.edit_message(
                embed=embed, view=BackToMenuView()
            )
            return

        embed = discord.Embed(
            title="📋 Ваши подписки",
            description="Выберите подписку, затем **Изменить** или **Удалить**.",
            color=discord.Color.blurple(),
        )
        view = SubscriptionListView(interaction.user.id, with_back=True)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(
        label="Удалить подписку",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
        custom_id="menu_untrack",
        row=0,
    )
    async def btn_untrack(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_subs = subs_db.get_user_subs(interaction.user.id)
        if not user_subs:
            embed = discord.Embed(
                title="📭 Нет подписок",
                description="Нечего удалять.",
                color=discord.Color.orange(),
            )
            await interaction.response.edit_message(embed=embed, view=BackToMenuView())
            return
        embed = discord.Embed(
            title="🗑️ Удаление подписки",
            description="Выберите подписку, затем нажмите **Удалить**.",
            color=discord.Color.red(),
        )
        view = SubscriptionListView(interaction.user.id, with_back=True)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(
        label="Проверить сейчас",
        style=discord.ButtonStyle.secondary,
        emoji="🧪",
        custom_id="menu_forcecheck",
        row=1,
    )
    async def btn_check(self, interaction: discord.Interaction, button: discord.ui.Button):
        # defer, потом отредактируем то же сообщение
        await interaction.response.defer()
        try:
            from monitor import run_check_once
            count = await run_check_once()
            embed = discord.Embed(
                title="✅ Проверка выполнена",
                description=f"Отправлено уведомлений: **{count}**",
                color=discord.Color.green(),
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Ошибка",
                description=f"`{e}`",
                color=discord.Color.red(),
            )
        embed.set_footer(text="→ Возврат в главное меню через 30 секунд")
        await interaction.edit_original_response(embed=embed, view=BackToMenuView())

    @discord.ui.button(
        label="Помощь",
        style=discord.ButtonStyle.secondary,
        emoji="❓",
        custom_id="menu_help",
        row=1,
    )
    async def btn_help(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="📖 Справка",
            color=discord.Color.gold(),
        )
        embed.add_field(
            name="🔔 Отслеживать",
            value="Создать подписку на предмет. Нужно указать цену, редкость и заточку.",
            inline=False,
        )
        embed.add_field(
            name="📋 Мои подписки",
            value="Список подписок. Можно изменить или удалить каждую.",
            inline=False,
        )
        embed.add_field(
            name="🧪 Проверить сейчас",
            value="Проверить аукцион немедленно, не дожидаясь авто-проверки.",
            inline=False,
        )
        embed.add_field(
            name="🧹 Очистить канал",
            value="Удалить все старые сообщения бота в канале.",
            inline=False,
        )
        embed.add_field(
            name="💎 Редкости",
            value="0 Обычный · 1 Необычный · 2 Особый · 3 Редкий · 4 Исключительный · 5 Легендарный",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=BackToMenuView())

    @discord.ui.button(
        label="Очистить канал",
        style=discord.ButtonStyle.secondary,
        emoji="🧹",
        custom_id="menu_clear",
        row=1,
    )
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        await ensure_channel_permissions(channel)

        await interaction.response.defer()
        import asyncio
        from bot_instance import bot
        deleted = 0
        # Не удаляем это сообщение
        this_msg_id = interaction.message.id if interaction.message else None
        async for msg in channel.history(limit=500):
            if msg.author == bot.user and msg.id != this_msg_id:
                try:
                    await msg.delete()
                    deleted += 1
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

        embed = discord.Embed(
            title="🧹 Канал очищен",
            description=f"Удалено сообщений: **{deleted}**",
            color=discord.Color.green(),
        )
        embed.set_footer(text="→ Возврат в главное меню через 30 секунд")
        await interaction.edit_original_response(embed=embed, view=BackToMenuView())


class BackToMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="← В главное меню",
        style=discord.ButtonStyle.primary,
        custom_id="back_to_menu",
    )
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())