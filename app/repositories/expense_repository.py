import sqlite3

from app.db import get_connection
from app.models.ledger import Contribution, ExpenseRecord, SettlementRecord, Share


def create_expense(
    db_path: str,
    *,
    expense: ExpenseRecord,
    created_by_user_id: int,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (
                trip_id,
                title,
                category,
                total_amount_cents,
                split_type,
                notes,
                expense_date,
                created_by_user_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expense.trip_id,
                expense.title,
                None,
                expense.total_amount_cents,
                expense.split_type,
                None,
                expense.expense_date,
                created_by_user_id,
            ),
        )
        if cursor.lastrowid:
            expense_id = int(cursor.lastrowid)

        connection.executemany(
            """
            INSERT INTO expense_payers (expense_id, trip_id, user_id, amount_paid_cents)
            VALUES (?, ?, ?, ?)
            """,
            [
                (expense_id, expense.trip_id, payer.user_id, payer.amount_paid_cents)
                for payer in expense.payers
            ],
        )
        connection.executemany(
            """
            INSERT INTO expense_shares (expense_id, trip_id, user_id, amount_owed_cents)
            VALUES (?, ?, ?, ?)
            """,
            [
                (expense_id, expense.trip_id, share.user_id, share.amount_owed_cents)
                for share in expense.shares
            ],
        )
        connection.commit()
        return expense_id


def list_expenses_for_trip(db_path: str, trip_id: int) -> list[ExpenseRecord]:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        expense_rows = connection.execute(
            "SELECT * FROM expenses WHERE trip_id = ? ORDER BY expense_date, id",
            (trip_id,),
        ).fetchall()

        expenses: list[ExpenseRecord] = []
        for expense_row in expense_rows:
            payer_rows = connection.execute(
                """
                SELECT user_id, amount_paid_cents
                FROM expense_payers
                WHERE expense_id = ?
                ORDER BY id
                """,
                (expense_row["id"],),
            ).fetchall()
            share_rows = connection.execute(
                """
                SELECT user_id, amount_owed_cents
                FROM expense_shares
                WHERE expense_id = ?
                ORDER BY id
                """,
                (expense_row["id"],),
            ).fetchall()
            expenses.append(
                ExpenseRecord(
                    trip_id=int(expense_row["trip_id"]),
                    total_amount_cents=int(expense_row["total_amount_cents"]),
                    split_type=str(expense_row["split_type"]),
                    payers=tuple(
                        Contribution(
                            user_id=int(payer_row["user_id"]),
                            amount_paid_cents=int(payer_row["amount_paid_cents"]),
                        )
                        for payer_row in payer_rows
                    ),
                    shares=tuple(
                        Share(
                            user_id=int(share_row["user_id"]),
                            amount_owed_cents=int(share_row["amount_owed_cents"]),
                        )
                        for share_row in share_rows
                    ),
                    title=str(expense_row["title"]),
                    expense_date=str(expense_row["expense_date"]),
                )
            )

        return expenses


def list_settlements_for_trip(db_path: str, trip_id: int) -> list[SettlementRecord]:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        settlement_rows = connection.execute(
            "SELECT * FROM settlements WHERE trip_id = ? ORDER BY created_at, id",
            (trip_id,),
        ).fetchall()
        return [
            SettlementRecord(
                trip_id=int(row["trip_id"]),
                from_user_id=int(row["from_user_id"]),
                to_user_id=int(row["to_user_id"]),
                amount_cents=int(row["amount_cents"]),
            )
            for row in settlement_rows
        ]