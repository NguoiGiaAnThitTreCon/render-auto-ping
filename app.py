import os
import json
import uuid
import requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

DATA_FILE = "targets.json"

# ----------------- Data Helpers -----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"targets": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def update_target(target_id, **kwargs):
    data = load_data()
    for t in data["targets"]:
        if t["id"] == target_id:
            for k, v in kwargs.items():
                t[k] = v
            break
    save_data(data)

# ----------------- Ping Function -----------------
def ping_target(target_id, url):
    try:
        r = requests.get(url, timeout=10)
        status = r.status_code
    except Exception as e:
        status = f"Error: {e}"

    update_target(target_id,
                  last_ping=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} → {status}")

# ----------------- Routes -----------------
@app.route("/", methods=["GET"])
def index():
    data = load_data()
    return render_template("index.html", targets=data.get("targets", []))

@app.route("/add_target", methods=["POST"])
def add_target():
    data = load_data()
    url = request.form["url"]
    label = request.form["label"]
    interval = int(request.form["interval"])

    new_target = {
        "id": str(uuid.uuid4()),
        "url": url,
        "label": label,
        "interval": interval,
        "running": False,
        "last_ping": None
    }
    data["targets"].append(new_target)
    save_data(data)
    return redirect(url_for("index"))

@app.route("/start/<target_id>")
def start_target(target_id):
    data = load_data()
    for t in data["targets"]:
        if t["id"] == target_id:
            scheduler.add_job(
                ping_target,
                "interval",
                seconds=t["interval"],
                args=[t["id"], t["url"]],
                id=t["id"],
                replace_existing=True
            )
            t["running"] = True
            break
    save_data(data)
    return redirect(url_for("index"))

@app.route("/stop/<target_id>")
def stop_target(target_id):
    try:
        scheduler.remove_job(target_id)
    except Exception:
        pass
    update_target(target_id, running=False)
    return redirect(url_for("index"))

@app.route("/ping/<target_id>")
def ping_now(target_id):
    data = load_data()
    for t in data["targets"]:
        if t["id"] == target_id:
            ping_target(t["id"], t["url"])
            break
    return redirect(url_for("index"))

@app.route("/delete/<target_id>")
def delete_target(target_id):
    data = load_data()
    data["targets"] = [t for t in data["targets"] if t["id"] != target_id]
    save_data(data)
    try:
        scheduler.remove_job(target_id)
    except Exception:
        pass
    return redirect(url_for("index"))

# ----------------- Self Ping -----------------
SELF_URL = os.environ.get("RENDER_EXTERNAL_URL")
if SELF_URL:
    def ping_self():
        try:
            r = requests.get(SELF_URL, timeout=5)
            print(f"[SELF PING] {SELF_URL} -> {r.status_code}")
        except Exception as e:
            print(f"[SELF PING ERROR] {e}")

    scheduler.add_job(
        ping_self,
        trigger="interval",
        seconds=300,  # mỗi 5 phút
        id="self_ping",
        replace_existing=True,
    )

# ----------------- Main -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
