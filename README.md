# Gringotts

Gringotts is a Telegram bot for tracking shared group travel expenses, calculating who owes whom, and exporting trip data to Excel.

The current codebase is in the early setup stage. Right now it provides:

- A Telegram bot application built with `python-telegram-bot`
- A FastAPI server to receive Telegram webhook updates locally
- An ngrok-based helper flow so Telegram can reach a local machine during development
- A minimal `/start` command to verify the bot wiring end to end
- Automatic SQLite database initialization with the initial project schema
- A pure Python ledger service for expense validation, balances, and settlement suggestions

## Tech Stack

- Python
- `python-telegram-bot`
- FastAPI
- Uvicorn
- `python-dotenv`
- `openpyxl` for later Excel export work

## Project Structure

```text
gringotts/
├── app/
│   ├── bot_handlers.py
│   ├── config.py
│   ├── db.py
│   ├── main.py
│   ├── ngrok_utils.py
│   └── services/
│       └── ledger_service.py
├── tests/
│   └── test_ledger_service.py
├── requirements.txt
└── README.md
```

## Current Status

### Phase Tracker

| Phase   | Goal                                         | Status      |
| :------ | :------------------------------------------- | :---------- |
| Phase 1 | Bot setup, env loading, basic command wiring | Complete    |
| Phase 2 | SQLite setup and schema creation             | Complete    |
| Phase 3 | Ledger logic and balance calculation         | Complete    |
| Phase 4 | Telegram conversation flows                  | Not started |
| Phase 5 | Excel export                                 | Not started |
| Phase 6 | Settlements, editing, polish                 | Not started |

### Why Phase 1 Counts As Complete

Phase 1 was defined as:

- Load secrets from `.env`
- Start the bot application successfully
- Respond to `/start`

The current project satisfies the code-level requirements and has already gone a step beyond the original polling-only version by using a local webhook flow with FastAPI and ngrok.

One operational note: if startup fails with `address already in use`, that is not a Phase 1 code problem. It only means port `8000` is already occupied by another process.

## How The Current App Works

1. `app/config.py` loads environment variables.
2. `app/main.py` initializes the SQLite database during startup.
3. `app/main.py` builds the Telegram application.
4. FastAPI exposes a health route and a Telegram webhook route.
5. `app/ngrok_utils.py` fetches the public ngrok HTTPS URL.
6. On startup, the app registers the webhook with Telegram.
7. Telegram sends updates to the webhook endpoint.
8. `app/bot_handlers.py` contains the `/start` command handler.

## Webhook Flow Diagram

This diagram shows how Telegram reaches your local machine during development when you use ngrok.

```mermaid
flowchart LR
	A[Telegram User] -->|sends /start| B[Telegram Servers]
	B -->|POST update to webhook| C[Public ngrok HTTPS URL]
	C -->|forwards request| D[Local FastAPI server on localhost:8000]
	D -->|builds Update and routes handler| E[python-telegram-bot application]
	E -->|runs CommandHandler start| F[start handler in app/bot_handlers.py]
	F -->|sendMessage API call| B
	B -->|delivers bot reply| A
```

You can think about it in two halves:

- Incoming path: Telegram sends the webhook request to ngrok, and ngrok forwards it to your local FastAPI app.
- Outgoing path: your bot code uses the Telegram Bot API to send a reply back through Telegram's servers to the user.

## Phase 2: Database Setup

Phase 2 adds the first persistent storage layer using SQLite.

### Files Added Or Updated

- `app/db.py` contains database initialization helpers and the initial schema.
- `app/config.py` now exposes `DB_PATH`.
- `app/main.py` now initializes the database during application startup.

### Current Database Tables

- `users`
- `trips`
- `trip_members`
- `expenses`
- `expense_payers`
- `expense_shares`
- `settlements`

### What Phase 2 Achieves

- The SQLite database file is created automatically if it does not exist.
- The schema is created automatically on startup.
- The project now has persistent tables ready for trips, members, expenses, and settlements.

### Schema Design Notes

The schema is now tightened around the travel-ledger requirements we discussed earlier.

- Money is stored as integer cents instead of floating point values.
- `expense_payers` and `expense_shares` include `trip_id` so the database can enforce that those users belong to the same trip.
- Each user can appear only once per expense in `expense_payers` and `expense_shares`.
- `expenses` includes `expense_date` separately from `created_at` so the date of the real-world expense is not forced to equal the entry timestamp.
- Right now the project assumes a fresh local SQLite database and recreates the schema cleanly during setup.

### ER Diagram

This diagram shows the current database structure and how the main ledger records relate to each other.

```mermaid
erDiagram
	USERS {
		int id PK
		int telegram_user_id UK
		string username
		string display_name
		datetime created_at
	}

	TRIPS {
		int id PK
		string name
		string currency
		string status
		int created_by_user_id FK
		datetime created_at
	}

	TRIP_MEMBERS {
		int id PK
		int trip_id FK
		int user_id FK
		datetime joined_at
	}

	EXPENSES {
		int id PK
		int trip_id FK
		string title
		string category
		int total_amount_cents
		string split_type
		string notes
		date expense_date
		int created_by_user_id FK
		datetime created_at
	}

	EXPENSE_PAYERS {
		int id PK
		int expense_id FK
		int trip_id FK
		int user_id FK
		int amount_paid_cents
	}

	EXPENSE_SHARES {
		int id PK
		int expense_id FK
		int trip_id FK
		int user_id FK
		int amount_owed_cents
	}

	SETTLEMENTS {
		int id PK
		int trip_id FK
		int from_user_id FK
		int to_user_id FK
		int amount_cents
		string note
		datetime created_at
	}

	USERS ||--o{ TRIPS : creates
	USERS ||--o{ TRIP_MEMBERS : joins
	TRIPS ||--o{ TRIP_MEMBERS : has
	TRIPS ||--o{ EXPENSES : contains
	USERS ||--o{ EXPENSES : records
	EXPENSES ||--o{ EXPENSE_PAYERS : paid_by
	EXPENSES ||--o{ EXPENSE_SHARES : allocated_to
	TRIPS ||--o{ EXPENSE_PAYERS : scoped_to
	TRIPS ||--o{ EXPENSE_SHARES : scoped_to
	USERS ||--o{ EXPENSE_PAYERS : contributes
	USERS ||--o{ EXPENSE_SHARES : owes
	TRIPS ||--o{ SETTLEMENTS : has
	USERS ||--o{ SETTLEMENTS : sends_or_receives
```

## Environment Variables

Create a `.env` file in the project root with:

```env
BOT_TOKEN=your_telegram_bot_token
WEBHOOK_SECRET=your_random_secret_string
PORT=8000
DB_PATH=data/gringotts.db
```

Notes:

- `BOT_TOKEN` is the token from BotFather.
- `WEBHOOK_SECRET` is used in the webhook URL path so random internet traffic does not hit a predictable Telegram route.
- `PORT` defaults to `8000` if omitted.
- `DB_PATH` defaults to `data/gringotts.db` if omitted.

## Phase 3: Ledger Logic

Phase 3 adds the pure Python business-logic layer that sits between the database
schema and the later Telegram conversation flows.

### Files Added Or Updated

- `app/services/ledger_service.py` contains the ledger validation and balance logic.
- `tests/test_ledger_service.py` covers the main expense and settlement cases.

### What Phase 3 Achieves

- Equal split share generation.
- Custom split share normalization.
- Cross-row expense validation.
- Per-member balance calculation across expenses and settlements.
- Greedy settlement suggestions for the current net balances.

### Core Phase 3 Rules

- For every expense, total paid must equal total owed.
- Net balances across the whole trip must sum to zero.
- Settlements are separate ledger events, not edits to historical expenses.
- The ledger logic is isolated from Telegram handlers so it can be tested directly.

## Install And Run

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start ngrok in a separate terminal

```bash
ngrok http 8000
```

### 4. Start the app

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 5. Test the bot

- Open a private chat with the bot in Telegram.
- Send `/start`.
- You should receive the greeting from `app/bot_handlers.py`.

## Learning Notes

### `telegram` vs `telegram.ext`

This project uses both parts of the `python-telegram-bot` library.

- `telegram` contains Telegram domain objects like `Update`.
- `telegram.ext` contains higher-level application helpers like `ApplicationBuilder` and `CommandHandler`.

### Why FastAPI Is Here

FastAPI is not replacing the Telegram bot library. It is only acting as the HTTP server that receives webhook requests from Telegram.

### Why ngrok Is Here

Telegram must reach a public HTTPS URL when using webhooks. Since local development does not normally expose your machine to the internet, ngrok creates a temporary public tunnel to your local FastAPI server.

## Next Phase

Phase 4 will wire the ledger service into Telegram conversation flows for creating trips, adding members, recording expenses, and showing balances.

## Updating This README

This README should be updated at the end of each completed phase so it always reflects:

- what has been built,
- what still remains,
- and how the current version of the project works.
