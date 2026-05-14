import sqlite3

from app.db import get_connection


def upsert_user(
    db_path: str,
    *,
    telegram_user_id: int,
    username: str | None,
    display_name: str,
) -> int:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO users (telegram_user_id, username, display_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_user_id)
            DO UPDATE SET
                username = excluded.username,
                display_name = excluded.display_name
            """,
            (telegram_user_id, username, display_name),
        )
        row = connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        connection.commit()
        return int(row[0])


def get_user_by_telegram_id(db_path: str, telegram_user_id: int) -> sqlite3.Row | None:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()


def get_users_by_ids(db_path: str, user_ids: list[int]) -> dict[int, sqlite3.Row]:
    if not user_ids:
        return {}

    placeholders = ", ".join(["?"] * len(user_ids))
    query = f"SELECT * FROM users WHERE id IN ({placeholders})"

    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query, tuple(user_ids)).fetchall()
        return {int(row["id"]): row for row in rows}