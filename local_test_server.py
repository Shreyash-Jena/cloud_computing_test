"""
Local Development & Testing Server for IIIT BBSR Laundry Service
Run this file with: python local_test_server.py
Then open your browser to: http://localhost:8000
No AWS account or external libraries needed!
"""
import http.server
import socketserver
import json
import uuid
import math
from datetime import datetime
import os

PORT = 8000
DATA_FILE = "local_db.json"

# Load or initialize local database
def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "requests": [],
        "pins": {},
        "config": {
            "total_machines": 5,
            "working_machines": 4,
            "alert_message": "",
            "cycle_time": 45,
            "last_updated": ""
        }
    }

def save_db(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

VALID_PC_EMAIL = "pc@iiit-bh.ac.in"
VALID_PC_PASS = "LaundryAdmin123"

def calculate_wait_time(queued_ahead_count, working_machines, cycle_time=45):
    if working_machines <= 0:
        return -1
    batches = math.ceil((queued_ahead_count + 1) / max(1, working_machines))
    return batches * cycle_time

def handle_backend(body):
    db = load_db()
    action = body.get("action")

    # 1. GET STATS
    if action == "GET_STATS":
        requests = db["requests"]
        config = db["config"]
        washing = sum(1 for r in requests if r.get("status") == "WASHING")
        queued = sum(1 for r in requests if r.get("status") in ["REQUESTED", "APPROVED_WAITING", "QUEUED"])
        ready = sum(1 for r in requests if r.get("status") in ["READY", "COMPLETED"])
        wait = calculate_wait_time(queued, config["working_machines"], config["cycle_time"])

        return 200, {
            "total_submitted": len(requests),
            "washing_count": washing,
            "queued_count": queued,
            "ready_count": ready,
            "total_active": washing + queued,
            "working_machines": config["working_machines"],
            "total_machines": config["total_machines"],
            "alert_message": config["alert_message"],
            "est_wait_minutes": wait,
            "cycle_time": config["cycle_time"],
            "system_updated": config.get("last_updated", "")
        }

    # 2. AUTH LOGIN
    elif action == "AUTH_LOGIN":
        email = body.get("email", "").strip().lower()
        password = body.get("password", "").strip()
        roll_no = body.get("rollNo", "").strip().upper()

        if not email or not password:
            return 400, {"error": "Email and PIN/Password are required."}

        # Check Staff
        if email == VALID_PC_EMAIL.lower() and password == VALID_PC_PASS:
            return 200, {
                "role": "STAFF",
                "email": VALID_PC_EMAIL,
                "name": "Laundry Manager",
                "message": "Staff login successful"
            }

        # Check Student email domain
        if not email.endswith("@iiit-bh.ac.in"):
            return 403, {"error": "Invalid email. Must end with @iiit-bh.ac.in (or use pc@iiit-bh.ac.in for staff)."}

        if len(password) < 4:
            return 400, {"error": "PIN must be at least 4 characters."}

        pins = db["pins"]
        if email in pins:
            if pins[email]["pin"] != password:
                return 401, {"error": "Incorrect 4-digit PIN for this student email."}
            return 200, {
                "role": "STUDENT",
                "email": email,
                "rollNo": pins[email].get("rollNo") or roll_no,
                "message": "Student sign in successful"
            }
        else:
            if not roll_no:
                return 400, {"error": "First time sign up: Please provide your Roll Number."}
            pins[email] = {"pin": password, "rollNo": roll_no}
            save_db(db)
            return 200, {
                "role": "STUDENT",
                "email": email,
                "rollNo": roll_no,
                "message": "Student account registered & signed in!"
            }

    # 3. STUDENT REQUEST
    elif action == "STUDENT_REQUEST":
        email = body.get("email", "").strip().lower()
        pin = body.get("pin", "").strip()
        roll_no = body.get("rollNo", "").strip().upper()

        if not roll_no:
            return 400, {"error": "Roll Number is required."}
        if not email.endswith("@iiit-bh.ac.in"):
            return 403, {"error": "Only @iiit-bh.ac.in emails allowed."}
        if len(pin) < 4:
            return 400, {"error": "PIN must be at least 4 characters."}

        pins = db["pins"]
        if email in pins:
            if pins[email]["pin"] != pin:
                return 401, {"error": "Incorrect PIN."}
        else:
            pins[email] = {"pin": pin, "rollNo": roll_no}

        # Duplicate check
        active_statuses = ["REQUESTED", "APPROVED_WAITING", "QUEUED", "WASHING"]
        for r in db["requests"]:
            if (r.get("email") == email or r.get("rollNo") == roll_no) and r.get("status") in active_statuses:
                return 400, {
                    "error": f"You already have an active bucket submitted (Bucket ID: #{r.get('id')}, Status: {r.get('status')}). Multiple submissions are not allowed."
                }

        req_id = str(uuid.uuid4())[:8].upper()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_item = {
            "id": req_id,
            "rollNo": roll_no,
            "email": email,
            "status": "REQUESTED",
            "date": now_str
        }
        db["requests"].insert(0, new_item)
        save_db(db)
        return 200, {"message": f"Bucket #{req_id} submitted successfully!", "id": req_id, "rollNo": roll_no}

    # 4. CHECK MY STATUS
    elif action == "CHECK_MY_STATUS":
        query = body.get("query", "").strip().lower()
        requests = [r for r in db["requests"] if r.get("email", "").lower() == query or r.get("rollNo", "").lower() == query]
        if not requests:
            return 200, {"has_active": False, "message": "No requests found"}

        latest = requests[0]
        status = latest.get("status")
        is_active = status in ["REQUESTED", "APPROVED_WAITING", "QUEUED", "WASHING"]
        config = db["config"]

        queue_pos = 0
        if is_active and status != "WASHING":
            queued_items = [r for r in db["requests"] if r.get("status") in ["REQUESTED", "APPROVED_WAITING", "QUEUED"]]
            queued_items.reverse()  # oldest first
            for idx, it in enumerate(queued_items):
                if it.get("id") == latest.get("id"):
                    queue_pos = idx + 1
                    break

        wait = calculate_wait_time(max(0, queue_pos - 1), config["working_machines"], config["cycle_time"]) if is_active else 0
        return 200, {
            "has_active": is_active,
            "request": latest,
            "queue_position": queue_pos,
            "estimated_minutes": wait,
            "history": requests[:5]
        }

    # 5. PC DASHBOARD
    elif action == "PC_DASHBOARD":
        email = body.get("email", "").strip()
        pwd = body.get("password", "").strip()
        if email != VALID_PC_EMAIL or pwd != VALID_PC_PASS:
            return 401, {"error": "Invalid Staff Credentials"}
        return 200, {"requests": db["requests"], "config": db["config"]}

    # 6. UPDATE SYSTEM CONFIG
    elif action == "UPDATE_SYSTEM_CONFIG":
        email = body.get("email", "").strip()
        pwd = body.get("password", "").strip()
        if email != VALID_PC_EMAIL or pwd != VALID_PC_PASS:
            return 401, {"error": "Unauthorized"}

        working_m = int(body.get("working_machines", 4))
        total_m = int(body.get("total_machines", 5))
        alert_msg = str(body.get("alert_message", "")).strip()

        db["config"]["working_machines"] = min(working_m, total_m)
        db["config"]["total_machines"] = total_m
        db["config"]["alert_message"] = alert_msg
        db["config"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_db(db)
        return 200, {"message": "Config updated", "config": db["config"]}

    # 7. UPDATE STATUS
    elif action == "UPDATE_STATUS":
        req_id = body.get("id")
        new_status = body.get("newStatus")
        for r in db["requests"]:
            if r.get("id") == req_id:
                r["status"] = new_status
                r["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_db(db)
                return 200, {"message": f"Updated to {new_status}", "newStatus": new_status}
        return 404, {"error": "Request not found"}

    return 400, {"error": f"Unknown action: {action}"}


class LocalHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api" or self.path == "/api/":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length).decode("utf-8")
            try:
                body = json.loads(post_body) if post_body else {}
            except Exception:
                body = {}

            status_code, response_data = handle_backend(body)
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    print(f"============================================================")
    print(f"  IIIT BBSR Smart Laundry - Local Dev Server")
    print(f"  Running on: http://localhost:{PORT}")
    print(f"  Staff Login -> Email: pc@iiit-bh.ac.in | Password: LaundryAdmin123")
    print(f"  Press Ctrl+C to stop the server.")
    print(f"============================================================")
    with socketserver.TCPServer(("", PORT), LocalHandler) as httpd:
        httpd.serve_forever()

