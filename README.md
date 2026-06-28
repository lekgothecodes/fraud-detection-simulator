# Fraud Detection Rule Simulator

A simplified, rule-based fraud detection engine. Transactions are submitted
through a dashboard, evaluated against a set of hand-written risk rules,
and flagged with a clear, human-readable reason for every flag raised.
Every transaction and flag is persisted in SQLite, so the system keeps a
full history rather than just reacting in the moment.

This mirrors the kind of rule-engine logic used by real banks for
first-pass fraud screening before a transaction is escalated for manual
review.

## Why this project

Most beginner full-stack projects are CRUD forms with no real logic
behind them. This one isn't — it requires translating a business/risk
policy ("more than 3 transactions in 10 minutes is suspicious") into
working, testable code, and persisting a decision history per user. That
is the same skill used in banking risk engines, just simplified.

## Tech stack

- **Backend:** Python, Flask
- **Database:** SQLite (single file, zero configuration — no separate
  database server to install or run)
- **Frontend:** HTML, CSS, vanilla JavaScript (no frameworks, no build step)

## Fraud rules implemented

| Rule | Logic | Severity |
|---|---|---|
| Velocity | More than 3 transactions from the same user within a 10-minute window | High |
| Location jump | Transaction location differs from the user's last known location | Medium |
| High amount | Transaction amount exceeds 3× the user's historical average | High |
| Odd hour | Transaction occurs between 01:00–04:00 | Medium |

All thresholds are configurable in `app.py` under `RULES_CONFIG`, so the
engine's policy can be tuned without rewriting any logic.

## How it works

1. A transaction is submitted via the dashboard form (or POSTed directly
   to the API).
2. The transaction is saved to SQLite.
3. The rule engine (`evaluate_transaction()` in `app.py`) pulls that
   user's transaction history and checks all four rules against it.
4. Any triggered rules are stored as flags, each with a specific reason
   string — not just a generic "suspicious" label.
5. The dashboard displays every transaction, flagged ones visually
   distinguished, with the exact reason(s) shown underneath.

## Running it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

The database (`fraud_detection.db`) is created automatically on first run
and seeded with demo data across three users, including a deliberate
velocity burst and a location/amount/odd-hour combination, so the
dashboard is populated immediately — no manual setup needed to see it
working.

Use the **"Reset demo data"** button on the dashboard at any time to wipe
the database and reload the original demo scenario (handy before a live
interview demo).

## API endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/transactions` | Returns all transactions with their flags |
| POST | `/api/transactions` | Submits a new transaction, runs it through the rule engine |
| GET | `/api/stats` | Returns summary counts (total / flagged / clean / flag rate) |
| POST | `/api/reset` | Wipes the database and reseeds demo data |

Example POST body:

```json
{
  "user_id": "user_1",
  "amount": 450.00,
  "location": "Cape Town, ZA",
  "merchant": "Takealot",
  "timestamp": "2026-06-27T14:30"
}
```

## Project structure

```
fraud-detection-simulator/
├── app.py                 # Flask app, database setup, rule engine
├── requirements.txt
├── fraud_detection.db      # created automatically on first run
├── templates/
│   └── index.html
└── static/
    ├── style.css
    └── app.js
```

## Possible extensions

- Per-rule on/off toggles in the UI (currently config-only)
- A "review queue" workflow where flagged transactions can be manually
  approved or rejected, with that decision logged
- Geo-distance calculation for the location rule instead of an exact
  string match (e.g. using lat/long and a distance threshold)
