import os, subprocess, threading, zipfile, time
from flask import Flask, render_template, request, redirect, session, jsonify
from config import PANEL_PASSWORD

app = Flask(__name__)
app.secret_key = "secret-key"

SCRIPTS = "scripts"
LOGS = "logs"

os.makedirs(SCRIPTS, exist_ok=True)
os.makedirs(LOGS, exist_ok=True)

processes = {}

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form["password"] == PANEL_PASSWORD:
            session["login"] = True
            return redirect("/dashboard")
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if not session.get("login"):
        return redirect("/")
    return render_template(
        "dashboard.html",
        files=os.listdir(SCRIPTS),
        running=list(processes.keys())
    )

# ---------------- RUN SCRIPT ----------------
def runner(name):
    path = os.path.join(SCRIPTS, name)
    log = os.path.join(LOGS, name + ".log")

    while True:
        with open(log, "a") as f:
            p = subprocess.Popen(
                ["python", path],
                stdout=f,
                stderr=f
            )
            processes[name] = p
            p.wait()

        if name not in processes:
            break   # manual stop
        time.sleep(2)  # auto restart delay

@app.route("/run", methods=["POST"])
def run():
    name = request.json["name"]
    if name in processes:
        return "already running"

    t = threading.Thread(target=runner, args=(name,), daemon=True)
    t.start()
    return "started"

@app.route("/stop", methods=["POST"])
def stop():
    name = request.json["name"]
    p = processes.get(name)
    if p:
        p.terminate()
        del processes[name]
    return "stopped"

@app.route("/delete", methods=["POST"])
def delete():
    name = request.json["name"]
    stop()
    os.remove(os.path.join(SCRIPTS, name))
    return "deleted"

# ---------------- LOG STREAM ----------------
@app.route("/logs/<name>")
def logs(name):
    log = os.path.join(LOGS, name + ".log")
    if not os.path.exists(log):
        return ""
    with open(log) as f:
        return "<pre>"+f.read()[-8000:]+"</pre>"

# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["POST"])
def upload():
    f = request.files["file"]

    if f.filename.endswith(".zip"):
        path = os.path.join(SCRIPTS, f.filename)
        f.save(path)

        with zipfile.ZipFile(path) as z:
            z.extractall(SCRIPTS)

        os.remove(path)

        req = os.path.join(SCRIPTS, "requirements.txt")
        if os.path.exists(req):
            subprocess.call(["pip", "install", "-r", req])

    else:
        f.save(os.path.join(SCRIPTS, f.filename))

    return redirect("/dashboard")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
