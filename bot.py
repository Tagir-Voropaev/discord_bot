from bot_instance import bot
from config import TOKEN

import commands  # noqa: F401
import events    # noqa: F401


if __name__ == "__main__":
    bot.run(TOKEN)