import sqlite3

from app.db import get_connection


def create_trip(
    db_path: str,
    *,
    name: str,
    currency: str,
    created_by_user_id: int,
) -> int:
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO trips (name, currency, created_by_user_id)
            VALUES (?, ?, ?)
            """,
            (name, currency, created_by_user_id),
        )
        connection.commit()
        return int(cursor.lastrowid)


def add_trip_member(db_path: str, *, trip_id: int, user_id: int) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO trip_members (trip_id, user_id)
            VALUES (?, ?)
            """,
            (trip_id, user_id),
        )
        connection.commit()


def is_trip_member(db_path: str, *, trip_id: int, user_id: int) -> bool:
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT 1 FROM trip_members WHERE trip_id = ? AND user_id = ?",
            (trip_id, user_id),
        ).fetchone()
        return row is not None


def get_trip_by_id(db_path: str, trip_id: int) -> sqlite3.Row | None:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            "SELECT * FROM trips WHERE id = ?",
            (trip_id,),
        ).fetchone()


def list_trips_for_user(db_path: str, user_id: int) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT t.*
            FROM trips t
            JOIN trip_members tm ON tm.trip_id = t.id
            WHERE tm.user_id = ?
            ORDER BY t.created_at DESC, t.id DESC
            """,
            (user_id,),
        ).fetchall()


def list_trip_members(db_path: str, trip_id: int) -> list[sqlite3.Row]:
    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        return connection.execute(
            """
            SELECT u.id AS user_id, u.telegram_user_id, u.username, u.display_name
            FROM trip_members tm
            JOIN users u ON u.id = tm.user_id
            WHERE tm.trip_id = ?
            ORDER BY u.display_name COLLATE NOCASE, u.id
            """,
            (trip_id,),
        ).fetchall()