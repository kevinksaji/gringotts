from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


class LedgerValidationError(ValueError):
    """Raised when an expense or settlement payload breaks ledger rules."""


@dataclass(frozen=True)
class Contribution:
    # One payer row for one expense. The amount is stored in cents to match the
    # database schema and to avoid floating point rounding issues.
    user_id: int
    amount_paid_cents: int


@dataclass(frozen=True)
class Share:
    # One share row for one expense. This represents how much a user consumed
    # or owes for that expense, not how much they paid upfront.
    user_id: int
    amount_owed_cents: int


@dataclass(frozen=True)
class ExpenseRecord:
    # This mirrors the normalized expense structure in the database: one parent
    # expense plus payer rows and share rows.
    trip_id: int
    total_amount_cents: int
    split_type: str
    payers: tuple[Contribution, ...]
    shares: tuple[Share, ...]
    title: str | None = None
    expense_date: str | None = None


@dataclass(frozen=True)
class SettlementRecord:
    # Settlements are separate ledger events from expenses. They reduce what a
    # debtor owes and reduce what a creditor should receive.
    trip_id: int
    from_user_id: int
    to_user_id: int
    amount_cents: int


@dataclass(frozen=True)
class MemberBalance:
    # These totals make it easier to debug the final net balance for a member.
    user_id: int
    total_paid_cents: int
    total_owed_cents: int
    settlements_sent_cents: int
    settlements_received_cents: int
    net_balance_cents: int


@dataclass(frozen=True)
class SuggestedSettlement:
    # One recommended transfer produced by the greedy matcher.
    from_user_id: int
    to_user_id: int
    amount_cents: int


def build_equal_shares(
    total_amount_cents: int, participant_user_ids: Sequence[int]
) -> tuple[Share, ...]:
    # Equal split means the same base amount for every participant. If the total
    # does not divide evenly, the first few participants receive one extra cent.
    _validate_positive_amount(total_amount_cents, "total_amount_cents")

    if not participant_user_ids:
        raise LedgerValidationError("Equal split requires at least one participant")

    _validate_unique_user_ids(participant_user_ids, "participant_user_ids")

    base_amount = total_amount_cents // len(participant_user_ids)
    remainder = total_amount_cents % len(participant_user_ids)

    shares: list[Share] = []
    for index, user_id in enumerate(participant_user_ids):
        amount_owed_cents = base_amount + (1 if index < remainder else 0)
        shares.append(Share(user_id=user_id, amount_owed_cents=amount_owed_cents))

    return tuple(shares)


def build_custom_shares(share_amounts_by_user_id: Mapping[int, int]) -> tuple[Share, ...]:
    # Custom split simply converts a per-user mapping into normalized Share
    # objects after validating the amounts.
    if not share_amounts_by_user_id:
        raise LedgerValidationError("Custom split requires at least one participant")

    shares: list[Share] = []
    for user_id, amount_owed_cents in share_amounts_by_user_id.items():
        if amount_owed_cents < 0:
            raise LedgerValidationError("Share amounts cannot be negative")
        shares.append(Share(user_id=user_id, amount_owed_cents=amount_owed_cents))

    return tuple(shares)


def validate_expense_inputs(
    *,
    trip_member_ids: Iterable[int],
    total_amount_cents: int,
    split_type: str,
    payers: Sequence[Contribution],
    shares: Sequence[Share],
) -> None:
    # This is the main ledger validator. It checks the cross-row rules that are
    # hard or awkward to enforce directly in SQLite.
    _validate_positive_amount(total_amount_cents, "total_amount_cents")

    if split_type not in {"equal", "custom"}:
        raise LedgerValidationError("split_type must be 'equal' or 'custom'")

    if not payers:
        raise LedgerValidationError("An expense must have at least one payer")

    if not shares:
        raise LedgerValidationError("An expense must have at least one share row")

    _validate_unique_user_ids([payer.user_id for payer in payers], "payers")
    _validate_unique_user_ids([share.user_id for share in shares], "shares")

    trip_member_id_set = set(trip_member_ids)
    for payer in payers:
        _validate_positive_amount(payer.amount_paid_cents, "payer.amount_paid_cents")
        if payer.user_id not in trip_member_id_set:
            raise LedgerValidationError(
                f"Payer user_id {payer.user_id} is not a member of the trip"
            )

    for share in shares:
        if share.amount_owed_cents < 0:
            raise LedgerValidationError("Share amounts cannot be negative")
        if share.user_id not in trip_member_id_set:
            raise LedgerValidationError(
                f"Share user_id {share.user_id} is not a member of the trip"
            )

    validate_balanced_expense(total_amount_cents, payers, shares)


def validate_balanced_expense(
    total_amount_cents: int,
    payers: Sequence[Contribution],
    shares: Sequence[Share],
) -> None:
    # A valid expense must balance on both sides: total paid equals the expense
    # total, and total owed also equals the expense total.
    total_paid_cents = sum(payer.amount_paid_cents for payer in payers)
    total_owed_cents = sum(share.amount_owed_cents for share in shares)

    if total_paid_cents != total_amount_cents:
        raise LedgerValidationError(
            "Sum of payer amounts must equal total_amount_cents"
        )

    if total_owed_cents != total_amount_cents:
        raise LedgerValidationError(
            "Sum of share amounts must equal total_amount_cents"
        )


def create_expense_record(
    *,
    trip_id: int,
    total_amount_cents: int,
    split_type: str,
    payers: Sequence[Contribution],
    shares: Sequence[Share],
    trip_member_ids: Iterable[int],
    title: str | None = None,
    expense_date: str | None = None,
) -> ExpenseRecord:
    # This helper validates inputs first and then returns one normalized record
    # that later phases can persist through repositories or handlers.
    validate_expense_inputs(
        trip_member_ids=trip_member_ids,
        total_amount_cents=total_amount_cents,
        split_type=split_type,
        payers=payers,
        shares=shares,
    )

    return ExpenseRecord(
        trip_id=trip_id,
        total_amount_cents=total_amount_cents,
        split_type=split_type,
        payers=tuple(payers),
        shares=tuple(shares),
        title=title,
        expense_date=expense_date,
    )


def calculate_member_balances(
    expenses: Sequence[ExpenseRecord],
    settlements: Sequence[SettlementRecord],
    member_user_ids: Iterable[int] | None = None,
) -> dict[int, MemberBalance]:
    # Balances are derived, never directly stored as the source of truth. This
    # function rolls up all expenses and settlements into per-member totals.
    totals: dict[int, dict[str, int]] = {}

    def ensure_member(user_id: int) -> None:
        if user_id not in totals:
            totals[user_id] = {
                "paid": 0,
                "owed": 0,
                "sent": 0,
                "received": 0,
            }

    if member_user_ids is not None:
        for user_id in member_user_ids:
            ensure_member(user_id)

    for expense in expenses:
        validate_balanced_expense(
            expense.total_amount_cents, expense.payers, expense.shares
        )

        for payer in expense.payers:
            ensure_member(payer.user_id)
            totals[payer.user_id]["paid"] += payer.amount_paid_cents

        for share in expense.shares:
            ensure_member(share.user_id)
            totals[share.user_id]["owed"] += share.amount_owed_cents

    for settlement in settlements:
        if settlement.amount_cents <= 0:
            raise LedgerValidationError("Settlement amounts must be positive")
        if settlement.from_user_id == settlement.to_user_id:
            raise LedgerValidationError("Settlement users must be different")

        ensure_member(settlement.from_user_id)
        ensure_member(settlement.to_user_id)
        totals[settlement.from_user_id]["sent"] += settlement.amount_cents
        totals[settlement.to_user_id]["received"] += settlement.amount_cents

    balances: dict[int, MemberBalance] = {}
    net_sum = 0
    for user_id, member_totals in totals.items():
        net_balance_cents = (
            member_totals["paid"]
            - member_totals["owed"]
            - member_totals["sent"]
            + member_totals["received"]
        )
        net_sum += net_balance_cents
        balances[user_id] = MemberBalance(
            user_id=user_id,
            total_paid_cents=member_totals["paid"],
            total_owed_cents=member_totals["owed"],
            settlements_sent_cents=member_totals["sent"],
            settlements_received_cents=member_totals["received"],
            net_balance_cents=net_balance_cents,
        )

    if net_sum != 0:
        raise LedgerValidationError("Net balances must sum to zero")

    return balances


def suggest_settlements(
    balances: Mapping[int, MemberBalance] | Mapping[int, int],
) -> tuple[SuggestedSettlement, ...]:
    # The greedy matcher is a good MVP algorithm: easy to understand, fast, and
    # guaranteed to produce a valid settlement plan when balances sum to zero.
    net_balances = _extract_net_balances(balances)
    if sum(net_balances.values()) != 0:
        raise LedgerValidationError("Cannot suggest settlements when nets do not sum to zero")

    creditors = sorted(
        ((user_id, amount) for user_id, amount in net_balances.items() if amount > 0),
        key=lambda item: item[1],
        reverse=True,
    )
    debtors = sorted(
        ((user_id, -amount) for user_id, amount in net_balances.items() if amount < 0),
        key=lambda item: item[1],
        reverse=True,
    )

    settlements: list[SuggestedSettlement] = []
    creditor_index = 0
    debtor_index = 0

    while creditor_index < len(creditors) and debtor_index < len(debtors):
        creditor_user_id, amount_to_receive = creditors[creditor_index]
        debtor_user_id, amount_to_pay = debtors[debtor_index]
        transfer_amount = min(amount_to_receive, amount_to_pay)

        settlements.append(
            SuggestedSettlement(
                from_user_id=debtor_user_id,
                to_user_id=creditor_user_id,
                amount_cents=transfer_amount,
            )
        )

        amount_to_receive -= transfer_amount
        amount_to_pay -= transfer_amount
        creditors[creditor_index] = (creditor_user_id, amount_to_receive)
        debtors[debtor_index] = (debtor_user_id, amount_to_pay)

        if amount_to_receive == 0:
            creditor_index += 1
        if amount_to_pay == 0:
            debtor_index += 1

    return tuple(settlements)


def _extract_net_balances(
    balances: Mapping[int, MemberBalance] | Mapping[int, int],
) -> dict[int, int]:
    # This helper makes `suggest_settlements` flexible: callers can either pass
    # full MemberBalance objects or a simpler user_id -> net mapping.
    extracted: dict[int, int] = {}
    for user_id, balance in balances.items():
        if isinstance(balance, MemberBalance):
            extracted[user_id] = balance.net_balance_cents
        else:
            extracted[user_id] = balance
    return extracted


def _validate_positive_amount(amount_cents: int, field_name: str) -> None:
    if amount_cents <= 0:
        raise LedgerValidationError(f"{field_name} must be positive")


def _validate_unique_user_ids(user_ids: Sequence[int], field_name: str) -> None:
    if len(user_ids) != len(set(user_ids)):
        raise LedgerValidationError(f"{field_name} cannot contain duplicate user IDs")