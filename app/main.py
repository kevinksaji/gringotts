import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ConversationHandler, MessageHandler, filters

from app.config import BOT_TOKEN, DB_PATH, WEBHOOK_SECRET
from app.handlers import (
    ADD_EXPENSE_TITLE,
    ADD_EXPENSE_TOTAL,
    NEW_TRIP_NAME,
    add_expense_start,
    add_expense_title,
    add_expense_total,
    add_member,
    balance,
    cancel,
    my_trips,
    new_trip_name,
    new_trip_start,
    start,
    summary,
)
from app.db import init_db
from app.ngrok_utils import get_ngrok_https_url

# Configure application-wide logging early so startup, webhook activity, and
# failures all produce consistent output in the terminal.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# The Telegram stack uses httpx/httpcore underneath. Lowering these loggers to
# WARNING keeps the console readable by hiding repetitive request-level logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Build the Telegram application object once during module import. This object
# is responsible for handler registration, update processing, bot access, and
# lifecycle methods such as initialize/start/stop.
if BOT_TOKEN:
    telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("mytrips", my_trips))
    telegram_app.add_handler(CommandHandler("addmember", add_member))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("summary", summary))
    telegram_app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("newtrip", new_trip_start)],
            states={
                NEW_TRIP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_trip_name)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )
    telegram_app.add_handler(
        ConversationHandler(
            entry_points=[CommandHandler("addexpense", add_expense_start)],
            states={
                ADD_EXPENSE_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense_title)],
                ADD_EXPENSE_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense_total)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FastAPI lifespan runs once when the server starts and once when it shuts
    # down. This is the right place to initialize Telegram resources that should
    # exist for the whole lifetime of the web server.
    init_db(DB_PATH)
    logger.info("Database initialized at %s", DB_PATH)

    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram application initialized")

    # Resolve the current public ngrok URL and combine it with the secret path.
    # This produces the exact webhook URL Telegram should send updates to.
    ngrok_url = get_ngrok_https_url()
    webhook_url = f"{ngrok_url}/telegram/{WEBHOOK_SECRET}"

    # Register the webhook with Telegram so future messages are delivered to our
    # FastAPI endpoint instead of being pulled via long polling.
    await telegram_app.bot.set_webhook(url=webhook_url)
    logger.info("Webhook set to %s", webhook_url)

    try:
        yield
    finally:
        # Clean shutdown matters. Deleting the webhook and stopping the Telegram
        # app prevents stale configuration and releases library resources.
        await telegram_app.bot.delete_webhook()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram application stopped")


# FastAPI is only serving HTTP routes here. The Telegram bot logic still lives
# inside python-telegram-bot; FastAPI just gives Telegram a webhook target.
app = FastAPI(lifespan=lifespan)


@app.get("/")
async def healthcheck():
    # Simple route for checking whether the web server is alive.
    return {"status": "ok"}


@app.post(f"/telegram/{WEBHOOK_SECRET}")
async def telegram_webhook(request: Request):
    try:
        # Telegram sends JSON payloads describing updates. We parse that payload
        # and convert it into the library's Update object.
        data = await request.json()
        update = Update.de_json(data, telegram_app.bot)

        # Hand the update to the Telegram application so it can route the event
        # through registered handlers like CommandHandler("start", start).
        await telegram_app.process_update(update)
        return {"ok": True}
    except Exception as e:
        # Log the full stack trace server-side, but return a generic HTTP error
        # response to the caller.
        logger.exception("Failed to process update")
        raise HTTPException(status_code=500, detail="update processing failed") from e