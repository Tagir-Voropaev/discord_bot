import discord


class HelpView(discord.ui.View):
    """Меню помощи с кнопками, которые выполняют действия команд."""

    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="Отслеживать",
        style=discord.ButtonStyle.success,
        emoji="🔔",
        custom_id="help_track",
        row=0,
    )
    async def btn_track(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.navigation import CategoryView

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
        custom_id="help_list",
        row=0,
    )
    async def btn_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.subscription_view import SubscriptionListView
        import subscriptions as subs_db

        user_subs = subs_db.get_user_subs(interaction.user.id)
        if not user_subs:
            embed = discord.Embed(
                title="📭 Нет подписок",
                description="Нажмите **🔔 Отслеживать**, чтобы создать первую.",
                color=discord.Color.orange(),
            )
            embed.set_footer(text="→ Возврат в главное меню через 30 секунд")
            from views.main_menu import BackToMenuView
            await interaction.response.edit_message(embed=embed, view=BackToMenuView())
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
        custom_id="help_untrack",
        row=0,
    )
    async def btn_untrack(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.subscription_view import SubscriptionListView
        import subscriptions as subs_db

        user_subs = subs_db.get_user_subs(interaction.user.id)
        if not user_subs:
            embed = discord.Embed(
                title="📭 Нет подписок",
                description="Нечего удалять.",
                color=discord.Color.orange(),
            )
            from views.main_menu import BackToMenuView
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
        custom_id="help_forcecheck",
        row=1,
    )
    async def btn_check(self, interaction: discord.Interaction, button: discord.ui.Button):
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
        from views.main_menu import BackToMenuView
        await interaction.edit_original_response(embed=embed, view=BackToMenuView())

    @discord.ui.button(
        label="Выгодные лоты",
        style=discord.ButtonStyle.success,
        emoji="💎",
        custom_id="help_deals",
        row=1,
    )
    async def btn_deals(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Имитируем команду /deals: вызываем её callback
        import asyncio
        import statistics
        import subscriptions as subs_db
        import user_settings
        import api_client

        await interaction.response.defer()

        subs = subs_db.get_user_subs(interaction.user.id)
        if not subs:
            embed = discord.Embed(
                title="📭 Нет подписок",
                description="Добавьте предметы через `/track`.",
                color=discord.Color.orange(),
            )
            from views.main_menu import BackToMenuView
            await interaction.edit_original_response(embed=embed, view=BackToMenuView())
            return

        unique_items = {}
        for s in subs:
            unique_items[s["item_id"]] = s

        all_deals = []
        for item_id, sub in unique_items.items():
            lots = await api_client.get_lots(item_id)
            if not lots:
                await asyncio.sleep(0.3)
                continue
            prices = sorted([l["buyout_price"] for l in lots if l["buyout_price"] > 0])
            if len(prices) < 3:
                await asyncio.sleep(0.3)
                continue
            baseline = statistics.median(prices[:5])
            for lot in lots:
                p = lot["buyout_price"]
                if p <= 0 or p >= baseline:
                    continue
                discount = (baseline - p) / baseline
                if discount < 0.20:
                    continue
                all_deals.append({
                    "name": sub["name"], "item_id": item_id, "price": p,
                    "baseline": int(baseline), "discount": discount,
                    "amount": lot["amount"], "qlt": lot.get("qlt"),
                    "ptn": lot.get("ptn"),
                })
            await asyncio.sleep(0.3)

        if not all_deals:
            embed = discord.Embed(
                title="😕 Ничего не найдено",
                description="Лотов с скидкой 20%+ не обнаружено.",
                color=discord.Color.orange(),
            )
            from views.main_menu import BackToMenuView
            await interaction.edit_original_response(embed=embed, view=BackToMenuView())
            return

        all_deals.sort(key=lambda x: x["discount"], reverse=True)
        embed = discord.Embed(
            title="💎 Выгодные лоты",
            description=f"Найдено **{len(all_deals)}** лотов на 20%+ ниже медианы.",
            color=discord.Color.green(),
        )
        for i, d in enumerate(all_deals[:10], 1):
            embed.add_field(
                name=f"#{i} {d['name']} — {d['price']:,} ₽",
                value=(
                    f"📉 Скидка **-{int(d['discount'] * 100)}%** "
                    f"от медианы {d['baseline']:,} ₽\n📦 ×{d['amount']}"
                ),
                inline=False,
            )

        from views.main_menu import BackToMenuView
        embed.set_footer(text="→ Возврат в главное меню")
        await interaction.edit_original_response(embed=embed, view=BackToMenuView())

    @discord.ui.button(
        label="Очистить канал",
        style=discord.ButtonStyle.secondary,
        emoji="🧹",
        custom_id="help_clear",
        row=1,
    )
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.permissions import ensure_channel_permissions
        from bot_instance import bot
        import asyncio

        channel = interaction.channel
        await ensure_channel_permissions(channel)

        await interaction.response.defer()
        this_msg_id = interaction.message.id if interaction.message else None
        deleted = 0
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
        from views.main_menu import BackToMenuView
        embed.set_footer(text="→ Возврат в главное меню")
        await interaction.edit_original_response(embed=embed, view=BackToMenuView())

    @discord.ui.button(
        label="В главное меню",
        style=discord.ButtonStyle.primary,
        emoji="🎛️",
        custom_id="help_menu",
        row=2,
    )
    async def btn_menu(self, interaction: discord.Interaction, button: discord.ui.Button):
        from views.main_menu import MainMenuView

        embed = discord.Embed(
            title="🎛️ Главное меню",
            description="Выберите действие:",
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=MainMenuView())