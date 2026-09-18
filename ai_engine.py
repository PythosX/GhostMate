import os, json, urllib.request

SYSTEM_PROMPT = """You are GhostMate, an autonomous DM assistant for a content creator.

Read the COMPLETE conversation, not just the newest message. Understand meaning and context, not keywords.

Automatically reply to routine, low-stakes questions when the creator facts are sufficient.

Escalate when the conversation is important, financially consequential, sensitive, complicated, unclear,
or requires the creator's personal judgment. Examples: sponsorships, paid offers, contracts, investor/press
requests, major partnerships, legal/safety issues, serious complaints, commitments, or low-confidence cases.

Never invent facts. Never negotiate money or promise a deal automatically.

For auto_reply: generate the actual natural response.
For escalate: create a helpful draft but do NOT send it automatically.

Return ONLY valid JSON:
{
  "intent": "short intent",
  "priority": 0,
  "confidence": 0.0,
  "action": "auto_reply" or "escalate",
  "reason": "brief decision explanation for the dashboard",
  "reply": "natural reply or draft"
}

Do not expose hidden chain-of-thought. The reason must be a short explanation only.
"""

def fallback(profile, history):
    text = history[-1]["message"].lower()
    high = ["sponsor","sponsorship","₹","$","paid","contract","investor","investment",
            "media","press","partnership","brand deal","collab","business","offer"]
    faq = ["camera","mic","microphone","gear","setup","lens","editing software"]
    if any(x in text for x in high):
        return {
            "intent":"Potential business opportunity","priority":95,"confidence":0.92,
            "action":"escalate",
            "reason":"The conversation may involve money, business, or a consequential request.",
            "reply":"Thanks for reaching out! I’d be happy to learn more. Please share the details, timeline, deliverables, and budget."
        }
    if any(x in text for x in faq):
        return {
            "intent":"Creator FAQ","priority":15,"confidence":0.95,
            "action":"auto_reply",
            "reason":"This appears to be a routine creator question covered by the creator profile.",
            "reply":"I usually record with my Sony A7 IV and Shure SM7B. Hope that helps!"
        }
    return {
        "intent":"Unclear/general message","priority":60,"confidence":0.62,
        "action":"escalate",
        "reason":"There is not enough context to safely automate this conversation.",
        "reply":"Thanks for reaching out! Could you share a little more detail so I can point you in the right direction?"
    }

def analyze_with_ai(profile, history):
    provider = os.getenv("AI_PROVIDER", "groq").lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        url = "https://api.openai.com/v1/chat/completions"
        model = os.getenv("AI_MODEL", "gpt-4o-mini")
    else:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        url = "https://api.groq.com/openai/v1/chat/completions"
        model = os.getenv("AI_MODEL", "llama-3.1-8b-instant")

    if not api_key:
        return fallback(profile, history)

    payload = {
        "model": model,
        "messages": [
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":json.dumps(
                {"creator": profile, "conversation": history[-30:]},
                ensure_ascii=False
            )}
        ],
        "temperature": 0.2,
        "response_format": {"type":"json_object"}
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type":"application/json",
            "Authorization":"Bearer " + api_key
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            data = json.loads(response.read().decode("utf-8"))
        result = json.loads(data["choices"][0]["message"]["content"])
        result["priority"] = max(0, min(100, int(result.get("priority", 50))))
        result["confidence"] = max(0, min(1, float(result.get("confidence", 0.5))))
        result["action"] = "escalate" if str(result.get("action","")).lower() == "escalate" else "auto_reply"
        return result
    except Exception:
        return fallback(profile, history)
