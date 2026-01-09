import os
import time
import zipfile
import threading
import subprocess

from flask import (
    Flask, render_template, request,
    redirect, session, jsonify
)

import psutil
from config import PANEL_PASSWORD

# ---------------- BASIC SETUP ----------------
app = Flask(__name__)
app.secret_key = "render-script-panel-secret"

BASE_DIR = os.getcwd()
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(SCRIPTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# script_name -> subprocess.Popen
processes = {}

# ---------------- AUTH ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == PANEL_PASSWORD:
            session["login"] = True
            return redirect("/dashboard")
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if not session.get("login"):
        return redirect("/")

    files = [
        f for f in os.listdir(SCRIPTS_DIR)
        if f.endswith(".py")
    ]

    return render_template(
        "dashboard.html",
        files=files,
        running=list(processes.keys())
    )

# ---------------- SCRIPT RUNNER ----------------
def runner(script_name):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    log_path = os.path.join(LOGS_DIR, script_name + ".log")

    while True:
        with open(log_path, "a", buffering=1) as log:
            try:
                p = subprocess.Popen(
                    ["python", script_path],
                    stdout=log,
                    stderr=log
                )
                processes[script_name] = p
                p.wait()
            except Exception as e:
                log.write(f"\n[ERROR] {e}\n")

        # manual stop hua to break
        if script_name not in processes:
            break

        time.sleep(2)  # auto-restart delay

# ---------------- CONTROL APIs ----------------
@app.route("/run", methods=["POST"])
def run_script():
    name = request.json.get("name")

    if not name or name in processes:
        return "invalid", 400

    t = threading.Thread(
        target=runner,
        args=(name,),
        daemon=True
    )
    t.start()
    return "started"


@app.route("/stop", methods=["POST"])
def stop_script():
    name = request.json.get("name")

    p = processes.get(name)
    if p:
        try:
            p.terminate()
        except:
            pass
        processes.pop(name, None)

    return "stopped"


@app.route("/restart", methods=["POST"])
def restart_script():
    name = request.json.get("name")

    # stop if running
    p = processes.get(name)
    if p:
        try:
            p.terminate()
        except:
            pass
        processes.pop(name, None)

    time.sleep(1)

    t = threading.Thread(
        target=runner,
        args=(name,),
        daemon=True
    )
    t.start()

    return "restarted"


@app.route("/restart-all", methods=["POST"])
def restart_all():
    names = list(processes.keys())

    for name in names:
        try:
            processes[name].terminate()
        except:
            pass
        processes.pop(name, None)

    time.sleep(1)

    for name in names:
        threading.Thread(
            target=runner,
            args=(name,),
            daemon=True
        ).start()

    return "ok"

# ---------------- DELETE ----------------
@app.route("/delete", methods=["POST"])
def delete_script():
    name = request.json.get("name")

    # stop first
    p = processes.get(name)
    if p:
        try:
            p.terminate()
        except:
            pass
        processes.pop(name, None)

    path = os.path.join(SCRIPTS_DIR, name)
    if os.path.exists(path):
        os.remove(path)

    return "deleted"

# ---------------- LOGS ----------------
@app.route("/log-text/<name>")
def log_text(name):
    path = os.path.join(LOGS_DIR, name + ".log")
    if not os.path.exists(path):
        return ""
    with open(path, "r", errors="ignore") as f:
        return f.read()[-6000:]


# ---------------- STATS ----------------
@app.route("/stats/<name>")
def stats(name):
    p = processes.get(name)
    if not p:
        return jsonify(cpu=0, ram=0)

    try:
        proc = psutil.Process(p.pid)
        cpu = proc.cpu_percent(interval=0.1)
        ram = round(proc.memory_info().rss / 1024 / 1024, 1)
        return jsonify(cpu=cpu, ram=ram)
    except:
        return jsonify(cpu=0, ram=0)

# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return redirect("/dashboard")

    filename = f.filename

    # ZIP upload
    if filename.endswith(".zip"):
        zip_path = os.path.join(SCRIPTS_DIR, filename)
        f.save(zip_path)

        with zipfile.ZipFile(zip_path) as z:
            z.extractall(SCRIPTS_DIR)

        os.remove(zip_path)

        req = os.path.join(SCRIPTS_DIR, "requirements.txt")
        if os.path.exists(req):
            subprocess.call(
                ["pip", "install", "-r", req]
            )

    # single file upload
    else:
        f.save(os.path.join(SCRIPTS_DIR, filename))

    return redirect("/dashboard")

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=10000,
        debug=False
        )
