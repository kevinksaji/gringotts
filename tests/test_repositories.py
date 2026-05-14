import tempfile
import unittest

from app.db import init_db
from app.models.ledger import Contribution, ExpenseRecord, Share
from app.repositories.expense_repository import create_expense, list_expenses_for_trip, list_settlements_for_trip
from app.repositories.trip_repository import add_trip_member, create_trip, is_trip_member, list_trip_members, list_trips_for_user
from app.repositories.user_repository import get_user_by_telegram_id, upsert_user


class RepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = f"{self.temp_dir.name}/test.db"
        init_db(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_user_trip_and_member_repository_flow(self) -> None:
        creator_id = upsert_user(
            self.db_path,
            telegram_user_id=101,
            username="alice",
            display_name="Alice",
        )
        member_id = upsert_user(
            self.db_path,
            telegram_user_id=202,
            username="bob",
            display_name="Bob",
        )

        trip_id = create_trip(
            self.db_path,
            name="Paris",
            currency="USD",
            created_by_user_id=creator_id,
        )
        add_trip_member(self.db_path, trip_id=trip_id, user_id=creator_id)
        add_trip_member(self.db_path, trip_id=trip_id, user_id=member_id)

        creator_row = get_user_by_telegram_id(self.db_path, 101)
        trips = list_trips_for_user(self.db_path, creator_id)
        members = list_trip_members(self.db_path, trip_id)

        self.assertIsNotNone(creator_row)
        self.assertEqual(int(creator_row["id"]), creator_id)
        self.assertEqual(len(trips), 1)
        self.assertEqual(int(trips[0]["id"]), trip_id)
        self.assertTrue(is_trip_member(self.db_path, trip_id=trip_id, user_id=member_id))
        self.assertEqual([member["display_name"] for member in members], ["Alice", "Bob"])

    def test_expense_repository_persists_normalized_expense(self) -> None:
        creator_id = upsert_user(
            self.db_path,
            telegram_user_id=101,
            username="alice",
            display_name="Alice",
        )
        member_id = upsert_user(
            self.db_path,
            telegram_user_id=202,
            username="bob",
            display_name="Bob",
        )
        trip_id = create_trip(
            self.db_path,
            name="Paris",
            currency="USD",
            created_by_user_id=creator_id,
        )
        add_trip_member(self.db_path, trip_id=trip_id, user_id=creator_id)
        add_trip_member(self.db_path, trip_id=trip_id, user_id=member_id)

        expense = ExpenseRecord(
            trip_id=trip_id,
            total_amount_cents=3000,
            split_type="equal",
            payers=(Contribution(user_id=creator_id, amount_paid_cents=3000),),
            shares=(
                Share(user_id=creator_id, amount_owed_cents=1500),
                Share(user_id=member_id, amount_owed_cents=1500),
            ),
            title="Taxi",
            expense_date="2026-05-14",
        )

        create_expense(self.db_path, expense=expense, created_by_user_id=creator_id)

        expenses = list_expenses_for_trip(self.db_path, trip_id)
        settlements = list_settlements_for_trip(self.db_path, trip_id)

        self.assertEqual(len(expenses), 1)
        self.assertEqual(expenses[0].title, "Taxi")
        self.assertEqual(expenses[0].total_amount_cents, 3000)
        self.assertEqual(len(expenses[0].payers), 1)
        self.assertEqual(len(expenses[0].shares), 2)
        self.assertEqual(settlements, [])