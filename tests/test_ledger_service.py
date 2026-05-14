import unittest

from app.models.ledger import Contribution, ExpenseRecord, LedgerValidationError, SettlementRecord, Share
from app.services.ledger_service import (
    build_custom_shares,
    build_equal_shares,
    calculate_member_balances,
    create_expense_record,
    suggest_settlements,
    validate_expense_inputs,
)


class LedgerServiceTestCase(unittest.TestCase):
    # These tests focus on the business rules for Phase 3. They do not touch
    # Telegram, FastAPI, or SQLite because the ledger logic should stand alone.

    def test_build_equal_shares_distributes_remainder_deterministically(self) -> None:
        shares = build_equal_shares(1001, [1, 2, 3])

        self.assertEqual([share.amount_owed_cents for share in shares], [334, 334, 333])

    def test_build_custom_shares_returns_normalized_share_objects(self) -> None:
        shares = build_custom_shares({1: 1500, 2: 2000, 3: 2500})

        self.assertEqual(sum(share.amount_owed_cents for share in shares), 6000)
        self.assertEqual([share.user_id for share in shares], [1, 2, 3])

    def test_validate_expense_inputs_rejects_unbalanced_payers(self) -> None:
        with self.assertRaises(LedgerValidationError):
            validate_expense_inputs(
                trip_member_ids={1, 2, 3},
                total_amount_cents=3000,
                split_type="equal",
                payers=[Contribution(user_id=1, amount_paid_cents=2000)],
                shares=build_equal_shares(3000, [1, 2, 3]),
            )

    def test_validate_expense_inputs_rejects_non_member_users(self) -> None:
        with self.assertRaises(LedgerValidationError):
            validate_expense_inputs(
                trip_member_ids={1, 2},
                total_amount_cents=2000,
                split_type="custom",
                payers=[Contribution(user_id=1, amount_paid_cents=2000)],
                shares=(Share(user_id=1, amount_owed_cents=1000), Share(user_id=3, amount_owed_cents=1000)),
            )

    def test_create_expense_record_accepts_equal_split_single_payer(self) -> None:
        expense = create_expense_record(
            trip_id=1,
            total_amount_cents=5000,
            split_type="equal",
            payers=[Contribution(user_id=1, amount_paid_cents=5000)],
            shares=build_equal_shares(5000, [1, 2, 3, 4, 5]),
            trip_member_ids={1, 2, 3, 4, 5},
            title="Taxi",
            expense_date="2026-05-14",
        )

        self.assertEqual(expense.trip_id, 1)
        self.assertEqual(expense.total_amount_cents, 5000)
        self.assertEqual(expense.title, "Taxi")

    def test_calculate_member_balances_handles_multiple_payers(self) -> None:
        expense = ExpenseRecord(
            trip_id=1,
            total_amount_cents=5000,
            split_type="equal",
            payers=(
                Contribution(user_id=1, amount_paid_cents=3000),
                Contribution(user_id=2, amount_paid_cents=2000),
            ),
            shares=build_equal_shares(5000, [1, 2, 3, 4, 5]),
        )

        balances = calculate_member_balances([expense], [], member_user_ids=[1, 2, 3, 4, 5])

        self.assertEqual(balances[1].net_balance_cents, 2000)
        self.assertEqual(balances[2].net_balance_cents, 1000)
        self.assertEqual(balances[3].net_balance_cents, -1000)
        self.assertEqual(sum(balance.net_balance_cents for balance in balances.values()), 0)

    def test_calculate_member_balances_handles_custom_split_and_settlement(self) -> None:
        dinner = ExpenseRecord(
            trip_id=1,
            total_amount_cents=6000,
            split_type="custom",
            payers=(Contribution(user_id=1, amount_paid_cents=6000),),
            shares=(
                Share(user_id=1, amount_owed_cents=2500),
                Share(user_id=2, amount_owed_cents=1500),
                Share(user_id=3, amount_owed_cents=2000),
            ),
        )
        settlement = SettlementRecord(
            trip_id=1,
            from_user_id=2,
            to_user_id=1,
            amount_cents=500,
        )

        balances = calculate_member_balances([dinner], [settlement], member_user_ids=[1, 2, 3])

        self.assertEqual(balances[1].net_balance_cents, 4000)
        self.assertEqual(balances[2].net_balance_cents, -2000)
        self.assertEqual(balances[3].net_balance_cents, -2000)
        self.assertEqual(sum(balance.net_balance_cents for balance in balances.values()), 0)

    def test_suggest_settlements_matches_debtors_to_creditors(self) -> None:
        settlements = suggest_settlements({1: 4000, 2: -1500, 3: -2500})

        self.assertEqual(
            list(settlements),
            [
                settlements[0].__class__(from_user_id=3, to_user_id=1, amount_cents=2500),
                settlements[1].__class__(from_user_id=2, to_user_id=1, amount_cents=1500),
            ],
        )

    def test_suggest_settlements_rejects_non_zero_sum_inputs(self) -> None:
        with self.assertRaises(LedgerValidationError):
            suggest_settlements({1: 1000, 2: -900})


if __name__ == "__main__":
    unittest.main()