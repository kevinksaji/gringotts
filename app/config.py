import os
from dotenv import load_dotenv

# Load variables from the project-level .env file into process environment
# variables. This lets the app keep secrets out of source code.
load_dotenv()

# BOT_TOKEN is the credential issued by BotFather. The Telegram library uses it
# to authenticate every request made on behalf of this bot.
BOT_TOKEN = os.getenv("BOT_TOKEN")

# WEBHOOK_SECRET is used as part of the incoming webhook URL path. This is not
# the main security boundary, but it helps avoid exposing a predictable public
# route for Telegram updates.
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# PORT is used by the local HTTP server. The default keeps local development
# simple while still allowing an override in deployment environments.
PORT = int(os.getenv("PORT", "8000"))

# DB_PATH points to the SQLite database file used for local persistence. During
# the early phases we keep this simple with a single file database.
DB_PATH = os.getenv("DB_PATH", "data/gringotts.db")

# Fail fast during startup if required configuration is missing. This is better
# than letting the application run partially configured and fail later when it
# tries to contact Telegram.
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing")

if not WEBHOOK_SECRET:
    raise ValueError("WEBHOOK_SECRET is missing")