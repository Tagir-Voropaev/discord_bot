import json
import os
import discord

FILE = "user_settings.json"
NOTIFICATION_CATEGORY_NAME = "уведомления"


def load_settings() -> dict:
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(settings: dict):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def _get_user_entry(user_id: int) -> dict:
    return load_settings().get(str(user_id), {})


def set_channels(user_id: int, control_id: int, notify_id: int):
    s = load_settings()
    s.setdefault(str(user_id), {})
    s[str(user_id)]["control_channel_id"] = control_id
    s[str(user_id)]["notify_channel_id"] = notify_id
    # Убираем legacy-ключ
    s[str(user_id)].pop("channel_id", None)
    save_settings(s)


def _clear_one(user_id: int, kind: str):
    s = load_settings()
    uid = str(user_id)
    if uid not in s:
        return
    if kind == "notify":
        s[uid].pop("notify_channel_id", None)
        s[uid].pop("channel_id", None)
    else:
        s[uid].pop("control_channel_id", None)
    if not s[uid]:
        del s[uid]
    save_settings(s)


def get_notify_channel_id(user_id: int):
    entry = _get_user_entry(user_id)
    return entry.get("notify_channel_id") or entry.get("channel_id")


def get_control_channel_id(user_id: int):
    return _get_user_entry(user_id).get("control_channel_id")


def get_valid_channel(guild: discord.Guild | None, user_id: int, kind: str = "notify"):
    """kind: 'notify' или 'control'. Возвращает живой канал или None."""
    if guild is None:
        return None
    cid = (
        get_notify_channel_id(user_id) if kind == "notify"
        else get_control_channel_id(user_id)
    )
    if not cid:
        return None
    ch = guild.get_channel(cid)
    if ch is None:
        _clear_one(user_id, kind)
        return None
    return ch


# Обратная совместимость — монитор использует get_channel, чтобы получать notify
def get_channel(user_id: int):
    return get_notify_channel_id(user_id)


def set_channel(user_id: int, channel_id: int):
    """Legacy: только notify."""
    s = load_settings()
    s.setdefault(str(user_id), {})["notify_channel_id"] = channel_id
    save_settings(s)


def clear_channel(user_id: int):
    _clear_one(user_id, "notify")


def _safe_channel_name(name: str) -> str:
    safe = name.lower().replace(" ", "-")
    safe = "".join(ch for ch in safe if ch.isalnum() or ch in "-_")
    return safe[:80] or "user"


async def redirect_if_not_personal(interaction) -> bool:
    """Разрешает команды только в control-канале.

    Если у пользователя ещё нет control-канала — не блокирует
    (первый /track или /menu создадут оба).
    """
    guild = interaction.guild
    control = get_valid_channel(guild, interaction.user.id, kind="control")
    if control is None:
        return False
    if interaction.channel and interaction.channel.id == control.id:
        return False
    await interaction.response.send_message(
        f"📢 Эту команду нужно использовать в вашем канале управления: "
        f"{control.mention}",
        ephemeral=True,
    )
    return True


async def get_or_create_user_channels(guild: discord.Guild, user: discord.Member):
    """Возвращает (control, notify). Создаёт оба канала, если их нет."""
    control = get_valid_channel(guild, user.id, kind="control")
    notify = get_valid_channel(guild, user.id, kind="notify")

    # Legacy: если у пользователя был только один старый канал — считаем его notify
    legacy = _get_user_entry(user.id).get("channel_id")
    if legacy and not notify:
        ch = guild.get_channel(legacy)
        if ch:
            notify = ch

    if control and notify:
        return control, notify

    # Категория
    category = discord.utils.find(
        lambda c: c.name.lower() == NOTIFICATION_CATEGORY_NAME,
        guild.categories,
    )
    if category is None:
        try:
            category = await guild.create_category(
                name=NOTIFICATION_CATEGORY_NAME,
                reason="Категория для каналов бота",
            )
        except discord.Forbidden:
            category = None

    user_overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    safe_name = _safe_channel_name(user.name)

    if not control:
        try:
            control = await guild.create_text_channel(
                name=f"управление-{safe_name}",
                overwrites=user_overwrites,
                category=category,
                topic=f"Управление ботом для {user.display_name}",
                reason=f"Создан канал управления для {user}",
            )
        except discord.Forbidden:
            return None, None

    if not notify:
        try:
            notify = await guild.create_text_channel(
                name=f"лоты-{safe_name}",
                overwrites=user_overwrites,
                category=category,
                topic=f"Только уведомления аукциона для {user.display_name}",
                reason=f"Создан канал уведомлений для {user}",
            )
        except discord.Forbidden:
            return control, None

    set_channels(user.id, control.id, notify.id)

    # Приветствие в control
    try:
        from views.main_menu import MainMenuView

        embed = discord.Embed(
            title="👋 Добро пожаловать!",
            description=(
                f"Это ваш **канал управления ботом**.\n\n"
                f"📋 Все команды, настройки и подписки — здесь.\n"
                f"🔔 Уведомления о лотах приходят в {notify.mention}\n\n"
                f"Используйте кнопки ниже."
            ),
            color=discord.Color.blurple(),
        )
        await control.send(embed=embed, view=MainMenuView())
    except Exception as e:
        print(f"[user_settings] Ошибка приветствия в control: {e}")

    # Приветствие в notify
    try:
        embed = discord.Embed(
            title="🔔 Канал уведомлений",
            description=(
                f"Здесь приходят **только уведомления** о выгодных лотах.\n\n"
                f"📋 Управление ботом и команды — в {control.mention}"
            ),
            color=discord.Color.green(),
        )
        await notify.send(embed=embed)
    except Exception as e:
        print(f"[user_settings] Ошибка приветствия в notify: {e}")

    return control, notify