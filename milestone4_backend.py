# backend_with_tests.py
import os
import sqlite3
import time
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, request, jsonify,send_file
from flask_cors import CORS
import pytest
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


# ------------------ Flask Setup ------------------
app = Flask(__name__)
CORS(app)


limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])


# ------------------ Logging Setup ------------------
os.makedirs("logs", exist_ok=True)
logger = logging.getLogger("web_ivr")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    handler = RotatingFileHandler("logs/web_ivr.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# ------------------ Database ------------------
DB_FILE = "ivr_web.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT,
            plan TEXT,
            balance REAL,
            phone TEXT,
            data_left TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def fetch_customer_db(cid):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers WHERE id=?", (cid,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "name": row[1], "plan": row[2], "balance": row[3], "phone": row[4], "data_left": row[5]}
    return None

def save_customer_db(cid, name):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        INSERT OR REPLACE INTO customers (id, name, plan, balance, phone, data_left)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (cid, name, "SmartPlan 299", 150.0, "9999999999", "1.5 GB"))
    conn.commit()
    conn.close()
    logger.info(f"Customer saved: {cid} - {name}")

# ------------------ Intents ------------------
def intent_check_balance(cust):
    msg = f"Your current balance is rupees {cust['balance']}."
    logger.info(f"check_balance: {cust['id']}")
    return msg

def intent_plan_details(cust):
    msg = f"Your current plan is {cust['plan']} with {cust['data_left']} data per day."
    logger.info(f"plan_details: {cust['id']}")
    return msg

def intent_offers(cust):
    msg = "Latest offers: 10% cashback on recharge above 299, double data on Premium, weekend free calls on Super 699."
    logger.info(f"offers: {cust['id']}")
    return msg

def intent_data_packs(cust, upgrade=False):
    if upgrade:
        cust['plan'] = "Premium 499"
        cust['data_left'] = "2.5 GB"
        conn = sqlite3.connect(DB_FILE)
        conn.execute("UPDATE customers SET plan=?, data_left=? WHERE id=?", (cust['plan'], cust['data_left'], cust['id']))
        conn.commit()
        conn.close()
        msg = "Upgraded to Premium Plan 499 successfully."
        logger.info(f"data_packs upgrade: {cust['id']}")
    else:
        msg = f"Your current plan is {cust['plan']} with {cust['data_left']} data per day."
    return msg

def intent_recharge(cust, amount=199):
    try:
        amount = int(amount)
    except:
        amount = 199
    cust['balance'] += amount
    conn = sqlite3.connect(DB_FILE)
    conn.execute("UPDATE customers SET balance=? WHERE id=?", (cust['balance'], cust['id']))
    conn.commit()
    conn.close()
    msg = f"Recharge of rupees {amount} successful. New balance is {cust['balance']}."
    logger.info(f"recharge: {cust['id']} amount {amount}")
    return msg

def intent_customer_care(cust, issue):
    issue_lower = issue.lower()

    if "menu" in issue_lower or "main menu" in issue_lower:
        return "Opening main menu. You can say balance, plan, offers, data upgrade, recharge, or customer care."

    elif "network" in issue_lower:
        msg = "Network issue logged. Our technical team will optimize your area soon."
        logger.info(f"network_issue: {cust['id']}")
    elif "sim" in issue_lower or "activation" in issue_lower:
        msg = "SIM issue logged. Activation will be completed shortly."
        logger.info(f"sim_issue: {cust['id']}")
    elif "recharge" in issue_lower:
        msg = "Recharge issue noted. It will be resolved shortly."
        logger.info(f"recharge_issue: {cust['id']}")
         
    else:
        msg = "Connecting to customer care. Describe your issue."
        logger.info(f"customer_care: {cust['id']}")
    return msg

def intent_exit(cust):
    msg = "Thank you for using SmartTel IVR. Goodbye!"
    logger.info(f"exit: {cust['id']}")
    return msg

def intent_unknown(cust):
    msg = "Sorry, I didn't understand that."
    logger.info(f"unknown intent: {cust.get('id','unknown')}")
    return msg

# ------------------ Flask Endpoints ------------------

 #Serve frontend HTML
@app.route('/')
def index():
    return send_file('milestone4_frontend.html')  # <-- your frontend HTML file in same folder


@app.route("/fetch_customer", methods=["POST"])
def fetch_customer():
    try:
        data = request.get_json()
        if not data or "id" not in data:
            logger.warning("Missing customer ID in fetch request")
            return jsonify({"status": "error", "message": "Missing customer ID"}), 400
        cid = data["id"].strip()
        if not cid:
            logger.warning("Empty customer ID in fetch request")
            return jsonify({"status": "error", "message": "Invalid customer ID"}), 400
        cust = fetch_customer_db(cid)
        if not cust:
            logger.info(f"Customer not found: {cid}")
            return jsonify({"status": "not_found"})
        logger.info(f"Customer fetched: {cid}")
        return jsonify({"status": "ok", "customer": cust})
    except Exception as e:
        logger.error(f"Error in fetch_customer: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500
    

@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        if not data or "id" not in data or "name" not in data:
            logger.warning("Missing fields in register request")
            return jsonify({"status": "error", "message": "Missing ID or name"}), 400
        cid = data["id"].strip()
        name = data["name"].strip()
        if not cid or not name:
            logger.warning("Invalid ID or name in register request")
            return jsonify({"status": "error", "message": "Invalid ID or name"}), 400
        existing = fetch_customer_db(cid)
        if existing:
            logger.warning(f"Duplicate registration attempt: {cid}")
            return jsonify({"status": "error", "message": "Customer ID already exists"}), 400
        save_customer_db(cid, name)
        logger.info(f"Customer registered: {cid} - {name}")
        
        # Fetch newly created customer
        cust = fetch_customer_db(cid)
        return jsonify({
            "status": "ok",
            "message": f"Customer {name} registered successfully",
            "customer": cust
        })
    except Exception as e:
        logger.error(f"Error in register: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500


@app.route("/intent", methods=["POST"])
@limiter.limit("10 per minute")
def intent():
   
    try:
        data = request.get_json()
        if not data or "id" not in data or "text" not in data:
            logger.warning("Missing fields in intent request")
            return jsonify({"status": "error", "message": "Missing ID or text"}), 400
        cid = data["id"].strip()
        cmd = data["text"].strip().lower()
        if not cid or not cmd:
            logger.warning("Invalid ID or text in intent request")
            return jsonify({"status": "error", "message": "Invalid ID or text"}), 400
        cust = fetch_customer_db(cid)
        if not cust:
            logger.warning(f"Customer not found for intent: {cid}")
            return jsonify({"status": "error", "message": "Customer not found"}), 404

        upgrade = data.get("upgrade", False)
        amount = data.get("amount", 199)

        if "balance" in cmd:
            msg = intent_check_balance(cust)
        elif "plan" in cmd:
            msg = intent_plan_details(cust)
        elif "offer" in cmd:
            msg = intent_offers(cust)
        elif "data" in cmd or "upgrade" in cmd:
            msg = intent_data_packs(cust, upgrade)
        elif "recharge" in cmd:
            msg = intent_recharge(cust, amount)
        elif "menu" in cmd or "main menu" in cmd:
            msg = "Opening main menu. You can say balance, plan, offers, data upgrade, recharge, or customer care."
        elif "network" in cmd or "sim" in cmd or "recharge issue" in cmd or "customer" in cmd or "care" in cmd or "talk" in cmd:
            msg = intent_customer_care(cust, cmd)
        elif "exit" in cmd or "bye" in cmd:
            msg = intent_exit(cust)
        else:
            msg = intent_unknown(cust)
        logger.info(f"Intent processed: {cid} - {cmd}")
        return jsonify({"status": "ok", "message": msg})
    except Exception as e:
        logger.error(f"Error in intent: {str(e)}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500

# ------------------ Initialize ------------------
init_db()

# ------------------ Tests ------------------
@pytest.fixture
def client():
    from flask.testing import FlaskClient
    _cleanup_db()
    init_db()
    save_customer_db("1001", "Aiza")
    with app.test_client() as client:
        yield client

def _cleanup_db():
    try:
        os.remove(DB_FILE)
    except FileNotFoundError:
        pass

def test_db_save_and_fetch():
    _cleanup_db()
    init_db()
    save_customer_db("9001", "UnitUser")
    c = fetch_customer_db("9001")
    assert c is not None
    assert c["name"] == "UnitUser"
    assert c["plan"].startswith("SmartPlan")

def test_detect_intent_performance():
    start = time.time()
    for _ in range(200):
        intent_check_balance(fetch_customer_db("1001"))
    end = time.time()
    avg = (end-start)/200
    assert avg < 0.05

def test_e2e_full_flow(client):
    # Register
    resp = client.post("/register", json={"id": "3003", "name": "E2EUser"})
    assert resp.status_code == 200
    # Fetch
    resp = client.post("/fetch_customer", json={"id": "3003"})
    assert resp.status_code == 200
    # Check balance
    resp = client.post("/intent", json={"id": "3003", "text": "check balance"})
    assert "balance" in resp.get_json()["message"]
    # Upgrade plan
    resp = client.post("/intent", json={"id": "3003", "text": "upgrade my data", "upgrade": True})
    assert "Upgraded" in resp.get_json()["message"]
    # Recharge
    resp = client.post("/intent", json={"id": "3003", "text": "recharge", "amount": 299})
    assert "Recharge" in resp.get_json()["message"]

def test_logging_written(client):
    log_file = "logs/web_ivr.log"
    if os.path.exists(log_file):
        os.remove(log_file)
    client.post("/intent", json={"id": "1001", "text": "check balance"})
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
    assert "check_balance" in content


# ------------------ Run Backend ------------------
if __name__ == "__main__":
    print("Starting backend on http://127.0.0.1:5000")
    app.run(debug=True)
