from __future__ import annotations

from datetime import date

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from app.config import DB_PATH
from app.models import Contribution
from app.repositories import create_expense, get_user_by_telegram_id, is_trip_member, list_expenses_for_trip, list_settlements_for_trip, list_trip_members
from app.services import build_equal_shares, calculate_member_balances, create_expense_record, suggest_settlements

from app.handlers.common import (
    LedgerInputError,
    display_name,
    ensure_user,
    format_cents,
    format_signed_cents,
    parse_amount_to_cents,
    resolve_trip_id,
    user_data,
)


ADD_EXPENSE_TITLE = 2
ADD_EXPENSE_TOTAL = 3


async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return ConversationHandler.END

    user_id = ensure_user(user.id, user.username, display_name(user))
    trip_id = resolve_trip_id(context, context.args or [])
    if trip_id is None:
        await message.reply_text("Usage: /addexpense <trip_id>, or use an active trip.")
        return ConversationHandler.END

    if not is_trip_member(DB_PATH, trip_id=trip_id, user_id=user_id):
        await message.reply_text("You must be a member of the trip to add an expense.")
        return ConversationHandler.END

    user_data(context)["expense_trip_id"] = trip_id
    await message.reply_text("Send the expense title.")
    return ADD_EXPENSE_TITLE


async def add_expense_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message is None:
        return ConversationHandler.END

    title = message.text.strip() if message.text else ""
    if not title:
        await message.reply_text("Expense title cannot be empty. Send the title again.")
        return ADD_EXPENSE_TITLE

    user_data(context)["expense_title"] = title
    await message.reply_text("Send the total amount, for example 42.50")
    return ADD_EXPENSE_TOTAL


async def add_expense_total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return ConversationHandler.END

    current_user_data = user_data(context)
    raw_trip_id = current_user_data.get("expense_trip_id")
    raw_title = current_user_data.get("expense_title")
    if raw_trip_id is None or raw_title is None:
        await message.reply_text("Expense setup expired. Start again with /addexpense.")
        return ConversationHandler.END
    if not isinstance(raw_trip_id, int):
        await message.reply_text("Expense setup expired. Start again with /addexpense.")
        return ConversationHandler.END
    title = str(raw_title)
    trip_id = raw_trip_id

    try:
        total_amount_cents = parse_amount_to_cents(message.text or "")
    except LedgerInputError as exc:
        await message.reply_text(str(exc))
        return ADD_EXPENSE_TOTAL

    user_id = ensure_user(user.id, user.username, display_name(user))
    members = list_trip_members(DB_PATH, trip_id)
    if not members:
        await message.reply_text("The trip has no members.")
        return ConversationHandler.END

    member_ids = [int(member["user_id"]) for member in members]
    shares = build_equal_shares(total_amount_cents, member_ids)
    expense = create_expense_record(
        trip_id=trip_id,
        total_amount_cents=total_amount_cents,
        split_type="equal",
        payers=[Contribution(user_id=user_id, amount_paid_cents=total_amount_cents)],
        shares=shares,
        trip_member_ids=member_ids,
        title=title,
        expense_date=date.today().isoformat(),
    )
    create_expense(DB_PATH, expense=expense, created_by_user_id=user_id)
    current_user_data["active_trip_id"] = trip_id
    current_user_data.pop("expense_trip_id", None)
    current_user_data.pop("expense_title", None)

    await message.reply_text(
        f"Added expense '{title}' for {format_cents(total_amount_cents)} to trip #{trip_id}."
    )
    return ConversationHandler.END


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    user_row = get_user_by_telegram_id(DB_PATH, user.id)
    if user_row is None:
        await message.reply_text("Start the bot first with /start.")
        return

    trip_id = resolve_trip_id(context, context.args or [])
    if trip_id is None:
        await message.reply_text("Usage: /balance <trip_id>, or use an active trip.")
        return

    if not is_trip_member(DB_PATH, trip_id=trip_id, user_id=int(user_row["id"])):
        await message.reply_text("You must be a member of the trip to view balances.")
        return

    members = list_trip_members(DB_PATH, trip_id)
    expenses = list_expenses_for_trip(DB_PATH, trip_id)
    settlements = list_settlements_for_trip(DB_PATH, trip_id)
    member_ids = [int(member["user_id"]) for member in members]
    balances_by_user_id = calculate_member_balances(expenses, settlements, member_ids)
    suggestions = suggest_settlements(balances_by_user_id)
    names_by_user_id = {
        int(member["user_id"]): str(member["display_name"])
        for member in members
    }

    lines = [f"Balances for trip #{trip_id}:"]
    for member in members:
        balance_row = balances_by_user_id[int(member["user_id"])]
        lines.append(
            f"- {member['display_name']}: {format_signed_cents(balance_row.net_balance_cents)}"
        )

    if suggestions:
        lines.append("")
        lines.append("Suggested settlements:")
        for suggestion in suggestions:
            lines.append(
                f"- {names_by_user_id[suggestion.from_user_id]} pays {names_by_user_id[suggestion.to_user_id]} {format_cents(suggestion.amount_cents)}"
            )
    else:
        lines.append("")
        lines.append("No outstanding settlements.")

    await message.reply_text("\n".join(lines))


summary = balance


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if message is not None:
        current_user_data = user_data(context)
        current_user_data.pop("expense_trip_id", None)
        current_user_data.pop("expense_title", None)
        await message.reply_text("Cancelled.")
    return ConversationHandler.END