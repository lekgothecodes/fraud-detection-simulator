"""
Fraud Detection Rule Simulator
------------------------------
A simplified rule-based fraud engine. Users submit transactions, the engine
evaluates each one against a set of hand-written risk rules, and flags
suspicious transactions with a clear reason. All transactions and flags are
persisted in SQLite so there's a full history.

Run with:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

from flask import Flask, request, jsonify, render_template
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fraud_detection.db")

# ----------------------------------------------------------------------
# Configurable rule thresholds (tweak these to simulate different policies)
# ----------------------------------------------------------------------
RULES_CONFIG = {
    "velocity_max_transactions": 3,      # max transactions allowed...
    "velocity_window_minutes": 10,       # ...within this many minutes
    "high_amount_multiplier": 3.0,       # flag if amount > avg * multiplier
    "odd_hour_start": 1,                 # flag window start (24h clock)
    "odd_hour_end": 4,                   # flag window end (24h clock)
}


# ----------------------------------------------------------------------
# Database helpers
# ----------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            location TEXT NOT NULL,
            merchant TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            rule_name TEXT NOT NULL,
            reason TEXT NOT NULL,
            severity TEXT NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id)
        )
    """)
    conn.commit()
    conn.close()


def seed_demo_data():
    """Populate with a believable scenario so the dashboard works on first open."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM transactions")
    if cur.fetchone()["c"] > 0:
        conn.close()
        return  # already seeded

    now = datetime.now()
    demo_transactions = [
        # user_1: normal spending history
        ("user_1", 450.00, "Cape Town, ZA", "Checkers", now - timedelta(days=5)),
        ("user_1", 320.00, "Cape Town, ZA", "Pick n Pay", now - timedelta(days=4)),
        ("user_1", 600.00, "Cape Town, ZA", "Engen Garage", now - timedelta(days=2)),
        # user_1: sudden velocity burst (4 transactions in 10 minutes)
        ("user_1", 200.00, "Cape Town, ZA", "Takealot", now - timedelta(minutes=9)),
        ("user_1", 150.00, "Cape Town, ZA", "Uber Eats", now - timedelta(minutes=7)),
        ("user_1", 90.00, "Cape Town, ZA", "Spar", now - timedelta(minutes=5)),
        ("user_1", 310.00, "Cape Town, ZA", "Game Store", now - timedelta(minutes=2)),
        # user_1: location jump + odd hour + high amount combo
        ("user_1", 8500.00, "Lagos, NG", "Unknown Electronics", now.replace(hour=2, minute=30)),
        # user_2: normal history then one high-amount outlier
        ("user_2", 200.00, "Johannesburg, ZA", "Woolworths", now - timedelta(days=6)),
        ("user_2", 180.00, "Johannesburg, ZA", "Clicks", now - timedelta(days=3)),
        ("user_2", 220.00, "Johannesburg, ZA", "Dis-Chem", now - timedelta(days=1)),
        ("user_2", 4500.00, "Johannesburg, ZA", "Luxury Watch Co", now - timedelta(hours=3)),
        # user_3: clean history, no flags expected
        ("user_3", 150.00, "Durban, ZA", "Spar", now - timedelta(days=3)),
        ("user_3", 175.00, "Durban, ZA", "KFC", now - timedelta(days=1)),
    ]

    for user_id, amount, location, merchant, ts in demo_transactions:
        cur.execute(
            "INSERT INTO transactions (user_id, amount, location, merchant, timestamp, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, amount, location, merchant, ts.isoformat(), datetime.now().isoformat())
        )
    conn.commit()
    conn.close()

    # Now run the fraud engine over every seeded transaction
    conn = get_db()
    rows = conn.execute("SELECT id FROM transactions ORDER BY id ASC").fetchall()
    conn.close()
    for row in rows:
        evaluate_transaction(row["id"])


# ----------------------------------------------------------------------
# Fraud rule engine
# ----------------------------------------------------------------------
def evaluate_transaction(transaction_id):
    """
    Runs all fraud rules against a single transaction (in the context of
    that user's transaction history) and stores any flags raised.
    """
    conn = get_db()
    cur = conn.cursor()

    txn = cur.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if txn is None:
        conn.close()
        return []

    # Pull this user's full history (excluding the txn being evaluated, for averages)
    history = cur.execute(
        "SELECT * FROM transactions WHERE user_id = ? AND id != ? ORDER BY timestamp ASC",
        (txn["user_id"], txn["id"])
    ).fetchall()

    flags_raised = []
    txn_time = datetime.fromisoformat(txn["timestamp"])

    # --- Rule 1: Velocity — too many transactions in a short window ---
    window_start = txn_time - timedelta(minutes=RULES_CONFIG["velocity_window_minutes"])
    recent_count = 1  # count the current transaction itself
    for h in history:
        h_time = datetime.fromisoformat(h["timestamp"])
        if window_start <= h_time <= txn_time:
            recent_count += 1

    if recent_count > RULES_CONFIG["velocity_max_transactions"]:
        flags_raised.append((
            "velocity",
            f"{recent_count} transactions within {RULES_CONFIG['velocity_window_minutes']} minutes "
            f"(limit is {RULES_CONFIG['velocity_max_transactions']})",
            "high"
        ))

    # --- Rule 2: Location jump — differs from last known location ---
    past_history = [h for h in history if datetime.fromisoformat(h["timestamp"]) < txn_time]
    if past_history:
        last_known_location = past_history[-1]["location"]
        if last_known_location != txn["location"]:
            flags_raised.append((
                "location_jump",
                f"Transaction location '{txn['location']}' differs from last known "
                f"location '{last_known_location}'",
                "medium"
            ))

    # --- Rule 3: High amount — unusually large vs. this user's average ---
    if past_history:
        avg_amount = sum(h["amount"] for h in past_history) / len(past_history)
        threshold = avg_amount * RULES_CONFIG["high_amount_multiplier"]
        if avg_amount > 0 and txn["amount"] > threshold:
            flags_raised.append((
                "high_amount",
                f"Amount R{txn['amount']:.2f} exceeds {RULES_CONFIG['high_amount_multiplier']}x "
                f"this user's average of R{avg_amount:.2f}",
                "high"
            ))

    # --- Rule 4: Odd hour — transaction during a high-risk time window ---
    hour = txn_time.hour
    if RULES_CONFIG["odd_hour_start"] <= hour < RULES_CONFIG["odd_hour_end"]:
        flags_raised.append((
            "odd_hour",
            f"Transaction occurred at {txn_time.strftime('%H:%M')}, "
            f"within the high-risk window ({RULES_CONFIG['odd_hour_start']}:00\u2013{RULES_CONFIG['odd_hour_end']}:00)",
            "medium"
        ))

    # Clear old flags for this transaction (in case of re-evaluation) and insert fresh ones
    cur.execute("DELETE FROM flags WHERE transaction_id = ?", (transaction_id,))
    for rule_name, reason, severity in flags_raised:
        cur.execute(
            "INSERT INTO flags (transaction_id, rule_name, reason, severity) VALUES (?, ?, ?, ?)",
            (transaction_id, rule_name, reason, severity)
        )
    conn.commit()
    conn.close()
    return flags_raised


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
    """Returns all transactions with their flags, newest first."""
    conn = get_db()
    txns = conn.execute("SELECT * FROM transactions ORDER BY timestamp DESC").fetchall()

    result = []
    for t in txns:
        flags = conn.execute(
            "SELECT rule_name, reason, severity FROM flags WHERE transaction_id = ?",
            (t["id"],)
        ).fetchall()
        result.append({
            "id": t["id"],
            "user_id": t["user_id"],
            "amount": t["amount"],
            "location": t["location"],
            "merchant": t["merchant"],
            "timestamp": t["timestamp"],
            "is_flagged": len(flags) > 0,
            "flags": [dict(f) for f in flags],
        })
    conn.close()
    return jsonify(result)


@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    """Adds a new transaction and immediately runs it through the rule engine."""
    data = request.get_json(force=True)

    required = ["user_id", "amount", "location", "merchant", "timestamp"]
    missing = [f for f in required if f not in data or str(data[f]).strip() == ""]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        amount = float(data["amount"])
    except (ValueError, TypeError):
        return jsonify({"error": "Amount must be a number"}), 400

    try:
        # Accept "YYYY-MM-DDTHH:MM" from an HTML datetime-local input
        timestamp = datetime.fromisoformat(data["timestamp"]).isoformat()
    except ValueError:
        return jsonify({"error": "Invalid timestamp format"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (user_id, amount, location, merchant, timestamp, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (data["user_id"], amount, data["location"], data["merchant"], timestamp, datetime.now().isoformat())
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()

    flags_raised = evaluate_transaction(new_id)

    return jsonify({
        "id": new_id,
        "is_flagged": len(flags_raised) > 0,
        "flags": [{"rule_name": r, "reason": reason, "severity": sev} for r, reason, sev in flags_raised]
    }), 201


@app.route("/api/stats", methods=["GET"])
def stats():
    """Summary counts for the dashboard header."""
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    flagged = conn.execute(
        "SELECT COUNT(DISTINCT transaction_id) AS c FROM flags"
    ).fetchone()["c"]
    conn.close()
    return jsonify({
        "total_transactions": total,
        "flagged_transactions": flagged,
        "clean_transactions": total - flagged,
        "flag_rate": round((flagged / total * 100), 1) if total > 0 else 0
    })


@app.route("/api/reset", methods=["POST"])
def reset_demo():
    """Wipes the DB and reseeds demo data — handy for a clean interview demo."""
    conn = get_db()
    conn.execute("DELETE FROM flags")
    conn.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
    seed_demo_data()
    return jsonify({"status": "reset complete"})


if __name__ == "__main__":
    init_db()
    seed_demo_data()
    app.run(debug=True)
