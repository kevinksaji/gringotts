from telegram import Update
from telegram.ext import ContextTypes


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # `Update` is the main Telegram event object. For a /start command, it will
    # contain the incoming message, chat, user, and other metadata.
    user = update.effective_user

    # `effective_user` is a convenience accessor from python-telegram-bot. It
    # gives us the user who triggered the current update without needing to dig
    # through the raw update structure ourselves.
    name = user.first_name if user else "there"

    # Command handlers usually receive a message update, but checking
    # `update.message` keeps the function defensive and easier to reason about
    # while you are still learning the different update types Telegram can send.
    if update.message:
        # `reply_text` sends a message back into the same chat where the command
        # was received. This is one of the most common response methods you will
        # use when building bot flows.
        await update.message.reply_text(
            f"Hello {name}! Gringotts is open for business."
        )