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
from flask_cors import CORS
from datetime import datetime, timedelta
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fraud_detection.db")

# ----------------------------------------------------------------------
# Configurable rule thresholds (tweak these to simulate different policies)
# ----------------------------------------------------------------------
RULES_CONFIG = {
    "velocity_max_transactions": 3,
    "velocity_window_minutes": 10,
    "high_amount_multiplier": 3.0,
    "odd_hour_start": 1,
    "odd_hour_end": 4,
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
            severity TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def seed_demo_data():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM transactions")
    if cur.fetchone()["c"] > 0:
        conn.close()
        return

    now = datetime.now()

    demo_transactions = [
        ("user_1", 450.00, "Cape Town, ZA", "Checkers", now - timedelta(days=5)),
        ("user_1", 320.00, "Cape Town, ZA", "Pick n Pay", now - timedelta(days=4)),
        ("user_1", 600.00, "Cape Town, ZA", "Engen Garage", now - timedelta(days=2)),
        ("user_1", 200.00, "Cape Town, ZA", "Takealot", now - timedelta(minutes=9)),
        ("user_1", 150.00, "Cape Town, ZA", "Uber Eats", now - timedelta(minutes=7)),
        ("user_1", 90.00, "Cape Town, ZA", "Spar", now - timedelta(minutes=5)),
        ("user_1", 310.00, "Cape Town, ZA", "Game Store", now - timedelta(minutes=2)),
        ("user_1", 8500.00, "Lagos, NG", "Unknown Electronics", now.replace(hour=2, minute=30)),
        ("user_2", 200.00, "Johannesburg, ZA", "Woolworths", now - timedelta(days=6)),
        ("user_2", 180.00, "Johannesburg, ZA", "Clicks", now - timedelta(days=3)),
        ("user_2", 220.00, "Johannesburg, ZA", "Dis-Chem", now - timedelta(days=1)),
        ("user_2", 4500.00, "Johannesburg, ZA", "Luxury Watch Co", now - timedelta(hours=3)),
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

    conn = get_db()
    rows = conn.execute("SELECT id FROM transactions").fetchall()
    conn.close()

    for row in rows:
        evaluate_transaction(row["id"])


# ----------------------------------------------------------------------
# FRAUD ENGINE (UNCHANGED)
# ----------------------------------------------------------------------
def evaluate_transaction(transaction_id):
    conn = get_db()
    cur = conn.cursor()

    txn = cur.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if txn is None:
        conn.close()
        return []

    history = cur.execute(
        "SELECT * FROM transactions WHERE user_id = ? AND id != ? ORDER BY timestamp ASC",
        (txn["user_id"], txn["id"])
    ).fetchall()

    flags_raised = []
    txn_time = datetime.fromisoformat(txn["timestamp"])

    window_start = txn_time - timedelta(minutes=RULES_CONFIG["velocity_window_minutes"])
    recent_count = 1

    for h in history:
        h_time = datetime.fromisoformat(h["timestamp"])
        if window_start <= h_time <= txn_time:
            recent_count += 1

    if recent_count > RULES_CONFIG["velocity_max_transactions"]:
        flags_raised.append(("velocity", "velocity rule triggered", "high"))

    past_history = [h for h in history if datetime.fromisoformat(h["timestamp"]) < txn_time]
    if past_history:
        last_known_location = past_history[-1]["location"]
        if last_known_location != txn["location"]:
            flags_raised.append(("location_jump", "location change detected", "medium"))

    if past_history:
        avg_amount = sum(h["amount"] for h in past_history) / len(past_history)
        threshold = avg_amount * RULES_CONFIG["high_amount_multiplier"]
        if txn["amount"] > threshold:
            flags_raised.append(("high_amount", "high amount anomaly", "high"))

    hour = txn_time.hour
    if RULES_CONFIG["odd_hour_start"] <= hour < RULES_CONFIG["odd_hour_end"]:
        flags_raised.append(("odd_hour", "odd hour transaction", "medium"))

    cur.execute("DELETE FROM flags WHERE transaction_id = ?", (transaction_id,))
    for r, reason, sev in flags_raised:
        cur.execute(
            "INSERT INTO flags (transaction_id, rule_name, reason, severity) VALUES (?, ?, ?, ?)",
            (transaction_id, r, reason, sev)
        )

    conn.commit()
    conn.close()
    return flags_raised


# ----------------------------------------------------------------------
# ROUTES
# ----------------------------------------------------------------------
@app.route("/")
def dashboard():
    return render_template("index.html")


@app.route("/api/transactions", methods=["GET"])
def list_transactions():
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
    data = request.get_json(force=True)

    amount = float(data["amount"])
    timestamp = datetime.fromisoformat(data["timestamp"]).isoformat()

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

    return jsonify({"id": new_id, "is_flagged": len(flags_raised) > 0}), 201


@app.route("/api/stats", methods=["GET"])
def stats():
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    flagged = conn.execute("SELECT COUNT(DISTINCT transaction_id) AS c FROM flags").fetchone()["c"]
    conn.close()

    return jsonify({
        "total_transactions": total,
        "flagged_transactions": flagged,
        "clean_transactions": total - flagged,
        "flag_rate": round((flagged / total * 100), 1) if total > 0 else 0
    })


@app.route("/api/reset", methods=["POST"])
def reset_demo():
    conn = get_db()
    conn.execute("DELETE FROM flags")
    conn.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()

    seed_demo_data()
    return jsonify({"status": "reset complete"})


# ----------------------------------------------------------------------
# FIX: IMPORTANT FOR RENDER (THIS WAS THE BUG)
# ----------------------------------------------------------------------
init_db()
seed_demo_data()


if __name__ == "__main__":
    app.run(debug=True)