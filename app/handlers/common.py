from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import MutableMapping, cast

from telegram.ext import ContextTypes

from app.config import DB_PATH
from app.repositories import upsert_user


class LedgerInputError(ValueError):
    pass


def ensure_user(telegram_user_id: int, username: str | None, display_name: str) -> int:
    return upsert_user(
        DB_PATH,
        telegram_user_id=telegram_user_id,
        username=username,
        display_name=display_name,
    )


def display_name(user) -> str:
    full_name = " ".join(
        part
        for part in [getattr(user, "first_name", None), getattr(user, "last_name", None)]
        if part
    ).strip()
    return full_name or getattr(user, "username", None) or str(getattr(user, "id", "user"))


def resolve_trip_id(
    context: ContextTypes.DEFAULT_TYPE,
    args: list[str] | tuple[str, ...],
) -> int | None:
    if args:
        try:
            trip_id = int(args[0])
        except ValueError:
            return None
        user_data(context)["active_trip_id"] = trip_id
        return trip_id
    active_trip_id = user_data(context).get("active_trip_id")
    if active_trip_id is None:
        return None
    if not isinstance(active_trip_id, int):
        return None
    return active_trip_id


def user_data(context: ContextTypes.DEFAULT_TYPE) -> MutableMapping[str, object]:
    return cast(MutableMapping[str, object], context.user_data)


def parse_amount_to_cents(raw_amount: str) -> int:
    normalized = raw_amount.strip().replace("$", "")
    if not normalized:
        raise LedgerInputError("Amount cannot be empty. Send a value like 42.50")
    try:
        amount = Decimal(normalized)
    except InvalidOperation as exc:
        raise LedgerInputError("Amount must be a valid number like 42.50") from exc
    if amount <= 0:
        raise LedgerInputError("Amount must be greater than zero")
    return int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_cents(amount_cents: int) -> str:
    dollars = Decimal(amount_cents) / Decimal("100")
    return f"${dollars:.2f}"


def format_signed_cents(amount_cents: int) -> str:
    prefix = "+" if amount_cents > 0 else ""
    return f"{prefix}{format_cents(amount_cents)}"