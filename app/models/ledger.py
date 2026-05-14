from __future__ import annotations

from dataclasses import dataclass


class LedgerValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Contribution:
    user_id: int
    amount_paid_cents: int


@dataclass(frozen=True)
class Share:
    user_id: int
    amount_owed_cents: int


@dataclass(frozen=True)
class ExpenseRecord:
    trip_id: int
    total_amount_cents: int
    split_type: str
    payers: tuple[Contribution, ...]
    shares: tuple[Share, ...]
    title: str | None = None
    expense_date: str | None = None


@dataclass(frozen=True)
class SettlementRecord:
    trip_id: int
    from_user_id: int
    to_user_id: int
    amount_cents: int


@dataclass(frozen=True)
class MemberBalance:
    user_id: int
    total_paid_cents: int
    total_owed_cents: int
    settlements_sent_cents: int
    settlements_received_cents: int
    net_balance_cents: int


@dataclass(frozen=True)
class SuggestedSettlement:
    from_user_id: int
    to_user_id: int
    amount_cents: int