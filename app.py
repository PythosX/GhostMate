import os, sqlite3
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify
from ai_engine import analyze_with_ai

app = Flask(__name__)
if os.getenv("VERCEL"):
    DB = "/tmp/ghostmate.db"
else:
    DB = os.getenv("DB_PATH", "ghostmate.db")

CREATOR = {
    "name": "Alex Creator",
    "tone": "casual, friendly, concise",
    "facts": "Uses Sony A7 IV and Shure SM7B. Never invent creator facts.",
    
    "memory": [
    {"q": "What camera do you use?", "a": "I usually record with my Sony A7 IV."},
    {"q": "What microphone do you use?", "a": "I use the Shure SM7B for my main audio setup."},
    {"q": "What lens do you use most?", "a": "My go-to lens is a versatile zoom lens, depending on the shoot. If you need the exact model, I will check before answering."},
    {"q": "What camera settings do you use?", "a": "I adjust settings based on lighting and the type of shot, so I do not use one fixed setup for everything."},
    {"q": "What do you use to edit videos?", "a": "I use a desktop video editor for my editing workflow."},
    {"q": "How often do you post?", "a": "I try to keep a consistent posting schedule, but it can change depending on the project."},
    {"q": "Where do you get music for videos?", "a": "I use properly licensed music or royalty-free sources for videos."},
    {"q": "Do you edit your own videos?", "a": "I handle the creative direction and editing workflow, with help when a project needs it."},
    {"q": "What do you use for thumbnails?", "a": "I create thumbnails with a simple image-design workflow focused on clarity and strong visuals."},
    {"q": "What computer do you use?", "a": "I use a capable desktop setup for editing and content work; I will confirm exact specs before giving a specific model."},
    {"q": "What is your content niche?", "a": "My content focuses on practical creator and technology topics."},
    {"q": "Can I collaborate with you?", "a": "Yes, you can send the collaboration details and I can take a look."},
    {"q": "Do you accept product reviews?", "a": "Potentially, depending on the product and fit. Please send the details for review."},
    {"q": "Can I send you a product?", "a": "You can share the product information and delivery details first so I can review the request."},
    {"q": "Do you have a newsletter?", "a": "If I have an active newsletter, I will share the official signup link rather than guessing a URL."},
    {"q": "Can I use your clips?", "a": "Please ask before reusing my clips commercially or reposting them as your own."},
    {"q": "Where can I find your latest videos?", "a": "The latest videos are available on my official creator channels."},
    {"q": "How can I contact you for business?", "a": "Send the business details, company name, deliverables, timeline, and budget. Business requests may need my direct review."},
    {"q": "Do you offer consulting?", "a": "Consulting depends on the project and availability. Send the scope and timeline for review."},
    {"q": "Can you give me your personal contact number?", "a": "I keep personal contact details private. Please use the official business contact channel instead."},

    {"q": "What camera do you recommend for beginners?", "a": "I would choose a camera based on budget, content type, and ease of use. If you share those details, I can suggest an option."},
    {"q": "What microphone is good for YouTube?", "a": "A good microphone depends on your room and recording setup. I use the Shure SM7B, but that does not mean it is the right choice for everyone."},
    {"q": "What lighting do you use?", "a": "I use controlled lighting for my content, adjusting it depending on the scene and shooting conditions."},
    {"q": "Do you use a tripod?", "a": "Yes, a stable camera support is useful for many of my recordings."},
    {"q": "Do you record in 4K?", "a": "I use higher-resolution recording when it makes sense for the project and delivery requirements."},
    {"q": "Do you use a teleprompter?", "a": "A teleprompter can be useful for structured scripts, although I do not use one for every type of content."},
    {"q": "How do you plan your videos?", "a": "I usually start with the topic and goal, then organize the main points before recording."},
    {"q": "How do you come up with video ideas?", "a": "I look at audience questions, creator trends, technology topics, and ideas that can provide practical value."},
    {"q": "How long does it take to make a video?", "a": "It depends on the topic, recording requirements, editing, and amount of research involved."},
    {"q": "Do you script your videos?", "a": "For some videos I use a structured script, while other videos are planned around key talking points."},
    {"q": "How do you choose video topics?", "a": "I consider audience interest, usefulness, relevance, and whether I can provide something valuable on the topic."},
    {"q": "Do you accept sponsorships?", "a": "I consider sponsorship opportunities, but specific offers need to be reviewed before I agree to anything."},
    {"q": "How much do you charge for sponsorships?", "a": "Sponsorship pricing depends on the campaign, deliverables, audience, timeline, and other details, so I do not automatically quote a price."},
    {"q": "Can you promote my company?", "a": "Please send the company information, campaign goals, deliverables, timeline, and budget for review."},
    {"q": "Can you review my product?", "a": "Send the product information and review requirements. I can then determine whether it is appropriate for consideration."},
    {"q": "Can I interview you?", "a": "Send the interview topic, format, publication, expected time commitment, and deadline so it can be reviewed."},
    {"q": "Can I invite you to an event?", "a": "Please send the event name, location, date, purpose, and expected involvement."},
    {"q": "Can you speak at our event?", "a": "Send the event details, topic, date, location, audience, and expected involvement for review."},
    {"q": "Can you give me business advice?", "a": "I can share general creator and technology knowledge, but specific business decisions may need direct creator review."},
    {"q": "Can I become a member of your team?", "a": "You can send your background, relevant skills, portfolio, and the type of role you are interested in."}
],
    
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
