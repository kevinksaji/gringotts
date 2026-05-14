from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.config import DB_PATH
from app.repositories import add_trip_member, create_trip, get_user_by_telegram_id, is_trip_member, list_trips_for_user

from app.handlers.common import display_name, ensure_user, resolve_trip_id, user_data


NEW_TRIP_NAME = 1


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    ensure_user(user.id, user.username, display_name(user))
    await message.reply_text(
        "Gringotts is ready. Commands: /newtrip, /mytrips, /addmember, /addexpense, /balance, /summary."
    )


async def new_trip_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message is None:
        return ConversationHandler.END
    await message.reply_text("Send the trip name.")
    return NEW_TRIP_NAME


async def new_trip_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return ConversationHandler.END

    trip_name = message.text.strip() if message.text else ""
    if not trip_name:
        await message.reply_text("Trip name cannot be empty. Send the trip name again.")
        return NEW_TRIP_NAME

    user_id = ensure_user(user.id, user.username, display_name(user))
    trip_id = create_trip(
        DB_PATH,
        name=trip_name,
        currency="USD",
        created_by_user_id=user_id,
    )
    add_trip_member(DB_PATH, trip_id=trip_id, user_id=user_id)
    user_data(context)["active_trip_id"] = trip_id
    await message.reply_text(
        f"Created trip #{trip_id}: {trip_name}. It is now your active trip."
    )
    return ConversationHandler.END


async def my_trips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    user_row = get_user_by_telegram_id(DB_PATH, user.id)
    if user_row is None:
        await message.reply_text("You do not have any trips yet. Use /newtrip first.")
        return

    trips = list_trips_for_user(DB_PATH, int(user_row["id"]))
    if not trips:
        await message.reply_text("You do not have any trips yet. Use /newtrip first.")
        return

    active_trip_id = user_data(context).get("active_trip_id")
    lines = ["Your trips:"]
    for trip in trips:
        marker = " (active)" if int(trip["id"]) == active_trip_id else ""
        lines.append(f"#{trip['id']} - {trip['name']}{marker}")
    await message.reply_text("\n".join(lines))


async def add_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    owner_user_id = ensure_user(user.id, user.username, display_name(user))
    trip_id = resolve_trip_id(context, context.args or [])
    if trip_id is None:
        await message.reply_text("Usage: /addmember <trip_id> as a reply, or use an active trip.")
        return

    if not is_trip_member(DB_PATH, trip_id=trip_id, user_id=owner_user_id):
        await message.reply_text("You must be a member of the trip to add other members.")
        return

    replied_message = message.reply_to_message
    replied_user = replied_message.from_user if replied_message else None
    if replied_user is None:
        await message.reply_text("Reply to a user message with /addmember <trip_id>.")
        return

    member_user_id = ensure_user(
        replied_user.id,
        replied_user.username,
        display_name(replied_user),
    )
    add_trip_member(DB_PATH, trip_id=trip_id, user_id=member_user_id)
    await message.reply_text(
        f"Added {display_name(replied_user)} to trip #{trip_id}."
    )