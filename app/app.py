import os, sqlite3, logging, sys
from functools import wraps
from flask import Flask, request, session, jsonify, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret")
DB = os.getenv("DB_PATH", "notes.db")
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
REQS = Counter("app_requests_total", "Total requests", ["path", "status"])

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.executescript(
            "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT);"
            "CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, body TEXT);")
    return g.db

@app.teardown_appcontext
def close(e):
    d = g.pop("db", None)
    if d: d.close()

@app.after_request
def track(r):
    path = request.url_rule.rule if request.url_rule else "unknown"
    REQS.labels(path, r.status_code).inc()
    app.logger.info("%s %s %s", request.method, request.path, r.status_code)
    return r

@app.errorhandler(404)
def nf(e): return jsonify(error="not found"), 404

@app.errorhandler(500)
def err(e): return jsonify(error="server error"), 500

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "uid" not in session:
            return jsonify(error="login required"), 401
        return f(*a, **k)
    return w

@app.route("/")
def index(): return render_template("index.html")

@app.route("/health")
def health(): return jsonify(status="ok")

@app.route("/metrics")
def metrics(): return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}

@app.post("/api/register")
def register():
    d = request.get_json(silent=True) or {}
    if not d.get("username") or not d.get("password"):
        return jsonify(error="username and password required"), 400
    try:
        db().execute("INSERT INTO users(username,password) VALUES(?,?)",
                     (d["username"], generate_password_hash(d["password"])))
        db().commit()
    except sqlite3.IntegrityError:
        return jsonify(error="user exists"), 409
    return jsonify(ok=True), 201

@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u = db().execute("SELECT * FROM users WHERE username=?", (d.get("username"),)).fetchone()
    if not u or not check_password_hash(u["password"], d.get("password", "")):
        return jsonify(error="invalid credentials"), 401
    session["uid"] = u["id"]
    return jsonify(ok=True)

@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)

@app.get("/api/notes")
@login_required
def list_notes():
    rows = db().execute("SELECT id,title,body FROM notes WHERE user_id=?", (session["uid"],)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.post("/api/notes")
@login_required
def create_note():
    d = request.get_json(silent=True) or {}
    if not d.get("title"):
        return jsonify(error="title required"), 400
    cur = db().execute("INSERT INTO notes(user_id,title,body) VALUES(?,?,?)",
                       (session["uid"], d["title"], d.get("body", "")))
    db().commit()
    return jsonify(id=cur.lastrowid), 201

@app.put("/api/notes/<int:nid>")
@login_required
def update_note(nid):
    d = request.get_json(silent=True) or {}
    cur = db().execute("UPDATE notes SET title=?, body=? WHERE id=? AND user_id=?",
                       (d.get("title"), d.get("body", ""), nid, session["uid"]))
    db().commit()
    return (jsonify(ok=True), 200) if cur.rowcount else (jsonify(error="not found"), 404)

@app.delete("/api/notes/<int:nid>")
@login_required
def delete_note(nid):
    cur = db().execute("DELETE FROM notes WHERE id=? AND user_id=?", (nid, session["uid"]))
    db().commit()
    return (jsonify(ok=True), 200) if cur.rowcount else (jsonify(error="not found"), 404)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)