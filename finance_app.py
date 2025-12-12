import sqlite3
from flask import Flask, request, jsonify
from datetime import datetime
import os

# ====================================
# CONFIGURATION
# ====================================

app = Flask(__name__)

DB_PATH = "indago_financial_records.db"


# ====================================
# DATABASE HELPERS
# ====================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # ------------------------------------------------
    # 1. Purchase Request Log Table
    # ------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS purchase_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT NOT NULL,
            item_name TEXT NOT NULL,
            quantity_needed INTEGER NOT NULL,
            unit TEXT,
            current_stock INTEGER,
            estimated_cost REAL NOT NULL,
            status TEXT NOT NULL,
            decision_note TEXT,
            request_date TEXT NOT NULL,
            decision_date TEXT NOT NULL
        )
    """)

    # ------------------------------------------------
    # 2. Finance Budget Table
    # ------------------------------------------------
    c.execute("""
        CREATE TABLE IF NOT EXISTS finance_budget (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_budget REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # Initialize default budget if empty
    c.execute("SELECT COUNT(*) FROM finance_budget")
    if c.fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO finance_budget (current_budget, updated_at)
            VALUES (?, ?)
        """, (10000000, now))  # Default budget: 10,000,000

    conn.commit()
    conn.close()


# ====================================
# BUSINESS LOGIC
# ====================================

def estimate_cost(item_name, quantity):
    """
    Placeholder cost formula.
    Replace with real cost logic later.
    Currently:
        cost = quantity * 1000
    """
    return quantity * 1000


def approve_or_reject(estimated_cost):
    """
    Basic approval logic:
        APPROVE if cost <= 500,000
        REJECT otherwise
    """
    BUDGET_LIMIT = 500_000

    if estimated_cost <= BUDGET_LIMIT:
        return "APPROVED", "Auto-approved: within budget limit."
    else:
        return "REJECTED", f"Auto-rejected: exceeds budget limit ({BUDGET_LIMIT})."


# ====================================
# API ROUTES
# ====================================

@app.route("/", methods=["GET"])
def health():
    return jsonify({"message": "Finance subsystem running"})


# ------------------------------------------------
# GET: Current Budget
# ------------------------------------------------
@app.route("/CurrentBudget", methods=["GET"])
def get_current_budget():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT current_budget, updated_at
        FROM finance_budget
        ORDER BY id DESC
        LIMIT 1
    """)

    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({"error": "Budget not initialized"}), 500

    return jsonify({
        "current_budget": row["current_budget"],
        "updated_at": row["updated_at"]
    }), 200


# ------------------------------------------------
# POST: Inventory → Finance Purchase Request
# ------------------------------------------------
@app.route("/PurchaseRequest", methods=["POST"])
def process_purchase_request():
    data = request.get_json()

    required_fields = ["order_id", "item_name", "quantity_needed"]

    # Validate inventory payload
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Missing purchase request fields"}), 400

    # Finance calculates cost
    estimated_cost = estimate_cost(
        data["item_name"],
        data["quantity_needed"]
    )

    # Approval logic
    status, note = approve_or_reject(estimated_cost)

    now = datetime.utcnow().isoformat()

    # Save to DB
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        INSERT INTO purchase_requests (
            order_id, item_name, quantity_needed, unit, current_stock,
            estimated_cost, status, decision_note, request_date, decision_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["order_id"],
        data["item_name"],
        data["quantity_needed"],
        data.get("unit"),
        data.get("current_stock"),
        estimated_cost,
        status,
        note,
        now,
        now
    ))

    conn.commit()
    req_id = c.lastrowid
    conn.close()

    # Respond back to inventory subsystem
    return jsonify({
        "id": req_id,
        "order_id": data["order_id"],
        "item_name": data["item_name"],
        "quantity_needed": data["quantity_needed"],
        "estimated_cost": estimated_cost,
        "status": status,
        "decision_note": note
    }), 201 if status == "APPROVED" else 403


# ------------------------------------------------
# GET: Finance Approval/Denial History
# ------------------------------------------------
@app.route("/finance/history", methods=["GET"])
def finance_history():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT *
        FROM purchase_requests
        ORDER BY request_date DESC
    """)

    rows = c.fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])

# =========================
# WEEKLY ORDERS (PROXY TO ORDER APP)
# =========================

@app.route("/orders-weekly", methods=["GET"])
def finance_get_orders_weekly():
    """
    Finance service retrieves weekly orders from Order subsystem.
    This simply proxies the request.
    """
    try:
        resp = requests.get(ORDER_WEEKLY_URL, timeout=5)
        resp.raise_for_status()
        return jsonify(resp.json()), 200
    except Exception as e:
        return jsonify({
            "error": "Failed to retrieve weekly orders",
            "details": str(e)
        }), 500

# ====================================
# STARTUP
# ====================================

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        print("Database not found. Creating new one.")

    init_db()
    print("Finance subsystem running on port 5003")
    app.run(port=5003, debug=True)
