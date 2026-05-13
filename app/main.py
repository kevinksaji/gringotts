from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import BOT_TOKEN

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    name = user.first_name if user else "there"
    if update.message:
        await update.message.reply_text(
            f"Hello {name}! Gringotts is open for business."
        )

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Gringotts is open for business.")

    app.run_polling()


if __name__ == "__main__":
    main()