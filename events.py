import discord
from bot_instance import bot
from config import GUILD_ID
from items_db import ALL_ITEMS, GROUPED_ITEMS
from monitor import monitor_auction
import user_settings


@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)

    print(f"Синхронизировано команд: {len(synced)}")
    print(f"Бот {bot.user} готов! Загружено предметов: {len(ALL_ITEMS)}")
    for key, items in GROUPED_ITEMS.items():
        print(f"  {key}: {len(items)} предметов")

    if not monitor_auction.is_running():
        monitor_auction.start()
        print("[monitor] Фоновая проверка аукциона запущена.")


@bot.event
async def on_message(message: discord.Message):
    """Удаляем команды пользователя, если они отправлены в канал уведомлений."""
    if message.author.bot:
        return
    if not message.guild:
        return

    # Проверяем, не является ли канал — notify-каналом пользователя
    notify_id = user_settings.get_notify_channel_id(message.author.id)
    if not notify_id or message.channel.id != notify_id:
        return

    # Это notify-канал — удаляем сообщение пользователя и отправляем подсказку
    try:
        await message.delete()
    except Exception:
        pass

    control = user_settings.get_valid_channel(
        message.guild, message.author.id, kind="control"
    )
    hint = (
        f"📢 Этот канал — **только для уведомлений**.\n"
        f"Для команд используйте {control.mention if control else 'канал управления'}."
    )
    try:
        await message.channel.send(hint, delete_after=8)
    except Exception:
        pass