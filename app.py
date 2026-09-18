import os, sqlite3
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from ai_engine import analyze_with_ai

app = Flask(__name__)
DB = os.getenv("DB_PATH", "ghostmate.db")

CREATOR = {
    "name": "Alex Creator",
    "tone": "casual, friendly, concise",
    "facts": "Uses Sony A7 IV and Shure SM7B. Never invent creator facts.",
    "guardrails": [
        "Automatically answer routine low-stakes questions.",
        "Escalate money, sponsorships, contracts, major business opportunities, legal or sensitive issues, media requests requiring creator input, and uncertain or complicated messages.",
        "Never negotiate or promise a deal automatically."
    ]
}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def now():
    return datetime.now(timezone.utc).isoformat()

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT UNIQUE NOT NULL,
        sender_name TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        sender TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ai_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        intent TEXT, priority INTEGER, confidence REAL,
        action TEXT, reason TEXT, reply TEXT, timestamp TEXT NOT NULL
    );
    """)
    c.commit()
    c.close()

def get_or_create(sender_id, sender_name):
    c = db()
    row = c.execute("SELECT * FROM conversations WHERE sender_id=?", (sender_id,)).fetchone()
    if not row:
        c.execute(
            "INSERT INTO conversations(sender_id,sender_name,updated_at) VALUES(?,?,?)",
            (sender_id, sender_name, now())
        )
        c.commit()
        row = c.execute("SELECT * FROM conversations WHERE sender_id=?", (sender_id,)).fetchone()
    c.close()
    return dict(row)

def history(cid, limit=30):
    c = db()
    rows = c.execute(
        "SELECT sender,message,timestamp FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?",
        (cid, limit)
    ).fetchall()
    c.close()
    return [dict(r) for r in reversed(rows)]

def save_message(cid, sender, message):
    c = db()
    c.execute(
        "INSERT INTO messages(conversation_id,sender,message,timestamp) VALUES(?,?,?,?)",
        (cid, sender, message, now())
    )
    c.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), cid))
    c.commit()
    c.close()

def save_decision(cid, d):
    c = db()
    cur = c.execute("""INSERT INTO ai_decisions
        (conversation_id,intent,priority,confidence,action,reason,reply,timestamp)
        VALUES(?,?,?,?,?,?,?,?)""",
        (cid, d.get("intent"), d.get("priority"), d.get("confidence"),
         d.get("action"), d.get("reason"), d.get("reply"), now()))
    decision_id = cur.lastrowid
    c.commit()
    c.close()
    return decision_id

@app.route("/")
def index():
    return render_template("index.html", creator=CREATOR)

@app.get("/api/conversations")
def conversations():
    c = db()
    rows = c.execute("""SELECT c.*,
        (SELECT message FROM messages m WHERE m.conversation_id=c.id ORDER BY m.id DESC LIMIT 1) last_message
        FROM conversations c ORDER BY updated_at DESC""").fetchall()
    c.close()
    return jsonify([dict(r) for r in rows])

@app.get("/api/conversations/<int:cid>")
def conversation(cid):
    c = db()
    row = c.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
    c.close()
    if not row:
        return jsonify({"error": "Conversation not found"}), 404
    return jsonify({"conversation": dict(row), "messages": history(cid, 100)})

@app.post("/api/incoming")
def incoming():
    data = request.get_json(silent=True) or {}
    sender_id = str(data.get("sender_id", "demo-user")).strip()
    sender_name = str(data.get("sender_name", "Demo User")).strip() or "Demo User"
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Message is required"}), 400

    conv = get_or_create(sender_id, sender_name)
    save_message(conv["id"], "user", message)
    h = history(conv["id"])
    decision = analyze_with_ai(CREATOR, h)
    decision_id = save_decision(conv["id"], decision)
    decision["decision_id"] = decision_id

    if decision["action"] == "auto_reply":
        save_message(conv["id"], "ghostmate", decision["reply"])

    return jsonify({
        "conversation_id": conv["id"],
        "decision": decision,
        "history": history(conv["id"])
    })

@app.get("/api/stats")
def stats():
    c = db()
    incoming = c.execute("SELECT COUNT(*) n FROM messages WHERE sender='user'").fetchone()["n"]
    replies = c.execute("SELECT COUNT(*) n FROM messages WHERE sender='ghostmate'").fetchone()["n"]
    escalations = c.execute("SELECT COUNT(*) n FROM ai_decisions WHERE action='escalate'").fetchone()["n"]
    c.close()
    return jsonify({"messages": incoming, "replies": replies, "escalations": escalations})

@app.post("/api/decision/<int:did>/approve")
def approve(did):
    c = db()
    row = c.execute("SELECT * FROM ai_decisions WHERE id=?", (did,)).fetchone()
    c.close()
    if not row:
        return jsonify({"error": "Decision not found"}), 404
    save_message(row["conversation_id"], "ghostmate", row["reply"])
    return jsonify({"ok": True})

@app.post("/api/decision/<int:did>/takeover")
def takeover(did):
    c = db()
    row = c.execute("SELECT conversation_id FROM ai_decisions WHERE id=?", (did,)).fetchone()
    c.close()
    return jsonify({"ok": bool(row), "message": "Human takeover recorded for this demo."})

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True)
