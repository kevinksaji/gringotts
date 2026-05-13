import sqlite3
from pathlib import Path


CURRENT_SCHEMA_VERSION = 2


# The current schema keeps the ledger normalized and tightens the rules that the
# database itself can enforce:
# - monetary values are stored as integer cents instead of floating point
# - expense participants must belong to the same trip
# - each user appears at most once in payer/share rows for one expense
# - expense_date is stored separately from created_at
CURRENT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS trip_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (trip_id, user_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    total_amount_cents INTEGER NOT NULL CHECK (total_amount_cents > 0),
    split_type TEXT NOT NULL CHECK (split_type IN ('equal', 'custom')),
    notes TEXT,
    expense_date TEXT NOT NULL,
    created_by_user_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, trip_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    FOREIGN KEY (trip_id, created_by_user_id) REFERENCES trip_members(trip_id, user_id)
);

CREATE TABLE IF NOT EXISTS expense_payers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount_paid_cents INTEGER NOT NULL CHECK (amount_paid_cents > 0),
    UNIQUE (expense_id, user_id),
    FOREIGN KEY (expense_id, trip_id) REFERENCES expenses(id, trip_id) ON DELETE CASCADE,
    FOREIGN KEY (trip_id, user_id) REFERENCES trip_members(trip_id, user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expense_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL,
    trip_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    amount_owed_cents INTEGER NOT NULL CHECK (amount_owed_cents >= 0),
    UNIQUE (expense_id, user_id),
    FOREIGN KEY (expense_id, trip_id) REFERENCES expenses(id, trip_id) ON DELETE CASCADE,
    FOREIGN KEY (trip_id, user_id) REFERENCES trip_members(trip_id, user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id INTEGER NOT NULL,
    from_user_id INTEGER NOT NULL,
    to_user_id INTEGER NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
    note TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_user_id != to_user_id),
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE,
    FOREIGN KEY (trip_id, from_user_id) REFERENCES trip_members(trip_id, user_id),
    FOREIGN KEY (trip_id, to_user_id) REFERENCES trip_members(trip_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_trip_members_trip_id ON trip_members(trip_id);
CREATE INDEX IF NOT EXISTS idx_expenses_trip_id ON expenses(trip_id);
CREATE INDEX IF NOT EXISTS idx_expense_payers_expense_trip ON expense_payers(expense_id, trip_id);
CREATE INDEX IF NOT EXISTS idx_expense_shares_expense_trip ON expense_shares(expense_id, trip_id);
CREATE INDEX IF NOT EXISTS idx_settlements_trip_id ON settlements(trip_id);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    # A dedicated helper keeps connection setup in one place. Enabling foreign
    # keys is important in SQLite because the constraint support exists but is
    # off by default for each new connection.
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: str) -> None:
    # Ensure the parent directory exists before opening the SQLite file.
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    with get_connection(db_path) as connection:
        _create_current_schema(connection)
        _set_user_version(connection, CURRENT_SCHEMA_VERSION)
        connection.commit()


def list_tables(db_path: str) -> list[str]:
    # This is a small helper for validation and debugging. It lets us confirm
    # the schema exists without needing to inspect the file manually.
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]


def get_schema_version(db_path: str) -> int:
    # PRAGMA user_version is the built-in SQLite slot for tracking schema
    # versioning. We still record it so future schema changes can be tracked.
    with get_connection(db_path) as connection:
        return _get_user_version(connection)


def _create_current_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(CURRENT_SCHEMA_SQL)


def _get_user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _set_user_version(connection: sqlite3.Connection, version: int) -> None:
    connection.execute(f"PRAGMA user_version = {version}")