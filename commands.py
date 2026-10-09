import asyncio
import statistics
import discord
from discord import app_commands

from bot_instance import bot
from views import CategoryView, UntrackView, MainMenuView, HelpView
from views.permissions import ensure_channel_permissions
import subscriptions as subs_db
import user_settings
import api_client
from config import RARITIES
from monitor import run_check_once, reset_cache
from items_db import ALL_ITEMS, get_main_category


@bot.tree.command(name="menu", description="Главное меню с кнопками")
async def menu(interaction: discord.Interaction):
    if await user_settings.redirect_if_not_personal(interaction):
        return
    embed = discord.Embed(
        title="🎛️ Главное меню",
        description="Выберите действие:",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(
        embed=embed, view=MainMenuView(), ephemeral=True
    )


@bot.tree.command(name="track", description="Отслеживать цену предмета")
async def track(interaction: discord.Interaction):
    # /track можно вызывать везде — при создании подписки создадутся оба канала
    embed = discord.Embed(
        title="🔔 Отслеживание предмета",
        description="Выберите категорию предметов:",
        color=discord.Color.blurple(),
    )
    await interaction.response.send_message(
        embed=embed, view=CategoryView(), ephemeral=True
    )


@bot.tree.command(name="untrack", description="Удалить подписку")
async def untrack(interaction: discord.Interaction):
    if await user_settings.redirect_if_not_personal(interaction):
        return
    user_subs = subs_db.get_user_subs(interaction.user.id)
    if not user_subs:
        await interaction.response.send_message(
            "📭 Нет активных подписок.", ephemeral=True
        )
        return
    embed = discord.Embed(
        title="🗑️ Удаление подписки",
        description=f"У вас **{len(user_subs)}** подписок. Выберите:",
        color=discord.Color.red(),
    )
    await interaction.response.send_message(
        embed=embed, view=UntrackView(user_subs), ephemeral=True
    )


@bot.tree.command(name="list", description="Показать ваши подписки")
async def list_subs(interaction: discord.Interaction):
    if await user_settings.redirect_if_not_personal(interaction):
        return
    user_subs = subs_db.get_user_subs(interaction.user.id)
    if not user_subs:
        await interaction.response.send_message(
            "📭 Нет подписок. Используйте `/track`.", ephemeral=True
        )
        return
    embed = discord.Embed(title="📋 Ваши подписки", color=discord.Color.blurple())
    for s in user_subs:
        mode = s.get("mode", "smart")
        if mode == "smart":
            value = "🔥 Умный режим (ловит выгодные лоты)"
        else:
            value = f"💰 Порог: **{s.get('max_price', 0):,}** ₽"
        embed.add_field(name=s["name"], value=value, inline=True)

    notify = user_settings.get_valid_channel(
        interaction.guild, interaction.user.id, kind="notify"
    )
    if notify:
        embed.set_footer(text=f"Уведомления идут в #{notify.name}")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="mychannel", description="Ссылки на ваши каналы")
async def mychannel(interaction: discord.Interaction):
    control = user_settings.get_valid_channel(
        interaction.guild, interaction.user.id, kind="control"
    )
    notify = user_settings.get_valid_channel(
        interaction.guild, interaction.user.id, kind="notify"
    )

    if not control and not notify:
        await interaction.response.send_message(
            "📭 У вас ещё нет каналов. Создайте подписку через `/track` — "
            "бот создаст оба канала автоматически.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(title="📢 Ваши каналы", color=discord.Color.blurple())
    if control:
        embed.add_field(name="🎛️ Управление", value=control.mention, inline=False)
    if notify:
        embed.add_field(name="🔔 Уведомления", value=notify.mention, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="clear", description="Очистить канал от старых сообщений")
async def clear_channel(interaction: discord.Interaction):
    if await user_settings.redirect_if_not_personal(interaction):
        return
    channel = interaction.channel
    perms = channel.permissions_for(interaction.guild.me)
    if not perms.manage_messages:
        await interaction.response.send_message(
            "❌ Нет права **Управлять сообщениями**. Используйте `/fixperms`.",
            ephemeral=True,
        )
        return
    await interaction.response.defer(ephemeral=True)
    deleted = 0
    async for msg in channel.history(limit=500):
        if msg.author == bot.user:
            try:
                await msg.delete()
                deleted += 1
                await asyncio.sleep(0.3)
            except Exception:
                pass
    await interaction.followup.send(f"🗑️ Удалено: **{deleted}**", ephemeral=True)


@bot.tree.command(name="fixperms", description="Выдать боту права на управление каналом")
async def fixperms(interaction: discord.Interaction):
    if await user_settings.redirect_if_not_personal(interaction):
        return
    ok = await ensure_channel_permissions(interaction.channel)
    if ok:
        await interaction.response.send_message("✅ Права обновлены.", ephemeral=True)
    else:
        await interaction.response.send_message(
            "❌ Не удалось. Нужно право **Управлять каналами** на уровне сервера.",
            ephemeral=True,
        )


@bot.tree.command(name="help", description="Справка по боту")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Справка",
        description=(
            "Бот следит за аукционом каждые 30 секунд и присылает "
            "уведомления о выгодных лотах.\n\n"
            "**У вас два канала:**\n"
            "🎛️ **Управление** — команды и настройки (здесь работает)\n"
            "🔔 **Уведомления** — только сообщения от бота\n\n"
            "**Что бот делает автоматически:**\n"
            "• Сканирует подписки\n"
            "• Сравнивает с историей продаж\n"
            "• Присылает уведомления при скидке 10%+"
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="🎛️ /menu", value="Главное меню.", inline=False)
    embed.add_field(name="🔔 /track", value="Создать подписку.", inline=False)
    embed.add_field(name="📋 /list", value="Ваши подписки.", inline=False)
    embed.add_field(name="📢 /mychannel", value="Ссылки на ваши каналы.", inline=False)
    embed.add_field(name="🧹 /clear", value="Очистить канал.", inline=False)
    embed.set_footer(text="Уведомления приходят автоматически — писать команды не нужно.")
    await interaction.response.send_message(
        embed=embed, view=HelpView(), ephemeral=True
    )


# ============================================================
# ДИАГНОСТИКА — только для админов
# ============================================================


@bot.tree.command(
    name="debug_lots",
    description="[АДМИН] Показать все лоты по предмету",
)
@app_commands.default_permissions(administrator=True)
@app_commands.describe(name="Название предмета")
async def debug_lots(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    query = name.strip().lower()
    matches = [it for it in ALL_ITEMS if query in it["name"].lower()]
    if not matches:
        await interaction.followup.send(f"❌ «{name}» не найден.", ephemeral=True)
        return
    item = matches[0]
    lots = await api_client.get_lots(item["id"])
    if not lots:
        await interaction.followup.send(
            f"📦 Лотов по «{item['name']}» нет или ошибка API.", ephemeral=True
        )
        return
    lines = [f"**{item['name']}** (`{item['id']}`) — лотов: {len(lots)}\n"]
    for lot in sorted(lots, key=lambda x: x["buyout_price"])[:25]:
        lines.append(
            f"`{lot['buyout_price']:>12,} ₽` · qlt={lot.get('qlt')} · "
            f"ptn={lot.get('ptn')} · ×{lot['amount']}"
        )
    text = "\n".join(lines)
    if len(text) > 1900:
        text = text[:1900] + "\n…"
    await interaction.followup.send(text, ephemeral=True)


@bot.tree.command(
    name="resetnotified",
    description="[АДМИН] Сбросить кэш отправленных уведомлений",
)
@app_commands.default_permissions(administrator=True)
async def resetnotified(interaction: discord.Interaction):
    reset_cache()
    await interaction.response.send_message("🔄 Кэш сброшен.", ephemeral=True)


@bot.tree.command(
    name="forcecheck",
    description="[АДМИН] Запустить проверку аукциона сейчас",
)
@app_commands.default_permissions(administrator=True)
async def forcecheck(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        count = await run_check_once()
        await interaction.followup.send(
            f"✅ Проверка завершена. Уведомлений: **{count}**", ephemeral=True
        )
    except Exception as e:
        print(f"[forcecheck] {e}")
        await interaction.followup.send(f"❌ Ошибка: `{e}`", ephemeral=True)