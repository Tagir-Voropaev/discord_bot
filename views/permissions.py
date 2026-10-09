import discord


async def ensure_channel_permissions(channel: discord.TextChannel) -> bool:
    """Проверяет и добавляет боту права Manage Messages / Manage Channels.

    Возвращает True, если права в порядке (или исправлены).
    """
    me = channel.guild.me
    perms = channel.permissions_for(me)

    if perms.manage_messages and perms.manage_channels:
        return True

    # Пытаемся добавить права через overwrites
    try:
        overwrite = channel.overwrites_for(me)
        overwrite.manage_messages = True
        overwrite.manage_channels = True
        overwrite.send_messages = True
        overwrite.embed_links = True
        overwrite.read_message_history = True
        await channel.set_permissions(
            me,
            overwrite=overwrite,
            reason="Автонастройка прав для управления каналом",
        )
        return True
    except discord.Forbidden:
        return False
    except Exception as e:
        print(f"[perms] Ошибка: {e}")
        return False