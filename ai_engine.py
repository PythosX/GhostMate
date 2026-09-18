import os
import json
import re
import urllib.request
from difflib import SequenceMatcher


# ============================================================
# GHOSTMATE V3
# AI UNDERSTANDING → MEMORY RETRIEVAL → AI RESPONSE
# ============================================================


# ------------------------------------------------------------
# AI PROVIDER
# ------------------------------------------------------------

def get_ai_config():
    provider = os.getenv("AI_PROVIDER", "groq").lower()

    if provider == "openai":
        return {
            "provider": "openai",
            "api_key": os.getenv("OPENAI_API_KEY", "").strip(),
            "url": "https://api.openai.com/v1/chat/completions",
            "model": os.getenv("AI_MODEL", "gpt-4o-mini")
        }

    return {
        "provider": "groq",
        "api_key": os.getenv("GROQ_API_KEY", "").strip(),
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "model": os.getenv("AI_MODEL", "llama-3.1-8b-instant")
    }


# ------------------------------------------------------------
# GENERIC AI CALL
# ------------------------------------------------------------

def call_ai(system_prompt, user_prompt, temperature=0.2):

    config = get_ai_config()

    if not config["api_key"]:
        return None

    payload = {
        "model": config["model"],
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_prompt
            }
        ],
        "temperature": temperature,
        "response_format": {
            "type": "json_object"
        }
    }

    request = urllib.request.Request(
        config["url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + config["api_key"]
        },
        method="POST"
    )

    try:

        with urllib.request.urlopen(request, timeout=25) as response:

            raw = response.read().decode("utf-8")

            data = json.loads(raw)

            content = data["choices"][0]["message"]["content"]

            return json.loads(content)

    except Exception as error:

        print("AI ERROR:", error)

        return None


# ============================================================
# STEP 1
# AI UNDERSTANDS THE USER MESSAGE
# ============================================================

UNDERSTANDING_PROMPT = """
You are GhostMate's semantic understanding engine.

Your job is NOT to answer the user.

Your job is to understand what the user is actually asking.

The wording can be completely different from the wording stored
in the creator's memory.

Example:

Memory:
"What microphone do you use?"

User:
"What do you record your voice with?"

These mean the same thing.

Another example:

Memory:
"What camera do you use?"

User:
"Which camera is in your setup?"

These also mean the same thing.

Therefore NEVER rely on exact keywords.

Understand:

1. What is the user trying to know?
2. What entity/topic are they asking about?
3. What information would answer their question?
4. Create a short semantic search query that represents the meaning.

Also look at the conversation history because the meaning of a
message can depend on previous messages.

Return ONLY JSON:

{
    "intent": "short description",
    "topic": "main topic",
    "semantic_query": "best representation of what information is needed",
    "keywords": ["important", "concepts"],
    "needs_creator_memory": true,
    "is_business": false,
    "is_sensitive": false,
    "is_unclear": false,
    "confidence": 0.0
}

Do not answer the user.
"""


def understand_message(history):

    latest_message = history[-1]["message"]

    recent_history = history[-10:]

    prompt = json.dumps(
        {
            "latest_message": latest_message,
            "conversation": recent_history
        },
        ensure_ascii=False
    )

    result = call_ai(
        UNDERSTANDING_PROMPT,
        prompt,
        temperature=0.1
    )

    if result:
        result["confidence"] = max(
            0,
            min(
                1,
                float(result.get("confidence", 0.5))
            )
        )

        return result

    # Local fallback understanding
    return {
        "intent": "general question",
        "topic": latest_message,
        "semantic_query": latest_message,
        "keywords": latest_message.lower().split(),
        "needs_creator_memory": True,
        "is_business": False,
        "is_sensitive": False,
        "is_unclear": False,
        "confidence": 0.5
    }


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize(text):

    text = text.lower()

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# SIMPLE SEMANTIC RETRIEVAL SUPPORT
#
# This is a safety-net before asking AI to choose the memory.
# It helps reduce the number of memories sent to the second AI.
# ============================================================

STOPWORDS = {
    "what",
    "which",
    "where",
    "when",
    "how",
    "do",
    "does",
    "you",
    "your",
    "the",
    "a",
    "an",
    "is",
    "are",
    "can",
    "i",
    "me",
    "my",
    "to",
    "for",
    "of",
    "with",
    "use",
    "using",
    "tell",
    "about",
    "please"
}


def meaningful_words(text):

    words = normalize(text).split()

    return {
        word
        for word in words
        if len(word) > 2 and word not in STOPWORDS
    }


def lexical_similarity(query, memory_text):

    q_words = meaningful_words(query)
    m_words = meaningful_words(memory_text)

    if not q_words or not m_words:
        return 0

    overlap = len(q_words & m_words)

    overlap_score = overlap / max(len(q_words), 1)

    sequence_score = SequenceMatcher(
        None,
        normalize(query),
        normalize(memory_text)
    ).ratio()

    return (
        overlap_score * 0.65
        +
        sequence_score * 0.35
    )


def retrieve_candidate_memories(
    semantic_query,
    memory,
    limit=10
):

    scored = []

    for item in memory:

        combined = (
            item.get("q", "")
            + " "
            + item.get("a", "")
        )

        score = lexical_similarity(
            semantic_query,
            combined
        )

        scored.append(
            {
                "q": item.get("q", ""),
                "a": item.get("a", ""),
                "retrieval_score": round(score, 4)
            }
        )

    scored.sort(
        key=lambda x: x["retrieval_score"],
        reverse=True
    )

    return scored[:limit]


# ============================================================
# STEP 2
# AI RETRIEVES THE CORRECT MEMORY
# ============================================================

MEMORY_RETRIEVAL_PROMPT = """
You are GhostMate's memory retrieval engine.

The user has already been semantically understood.

Your job is to determine whether one of the provided memories
contains the information needed to answer the user's question.

IMPORTANT:

The user's wording does NOT need to match the memory wording.

Example:

User meaning:
"What do you record your voice with?"

Memory:
"What microphone do you use?"

This is a valid match.

Another example:

User:
"Which camera is in your setup?"

Memory:
"What camera do you use?"

This is also a valid match.

Compare MEANING, not exact wording.

Rules:

- Select the memory that actually answers the user's question.
- Do not select a memory merely because it shares a keyword.
- If no memory provides enough information, return memory_found=false.
- Do not invent missing information.
- If multiple memories are relevant, select the smallest set needed.
- Maximum 3 memories.

Return ONLY JSON:

{
    "memory_found": true,
    "selected_memories": [
        {
            "question": "...",
            "answer": "...",
            "relevance": 0.0
        }
    ],
    "reason": "short explanation"
}
"""


def retrieve_memory(understanding, memory):

    candidates = retrieve_candidate_memories(
        understanding.get(
            "semantic_query",
            ""
        ),
        memory,
        limit=10
    )

    prompt = json.dumps(
        {
            "understood_request": understanding,
            "candidate_memories": candidates
        },
        ensure_ascii=False
    )

    result = call_ai(
        MEMORY_RETRIEVAL_PROMPT,
        prompt,
        temperature=0.0
    )

    if result:

        selected = result.get(
            "selected_memories",
            []
        )

        cleaned = []

        for item in selected[:3]:

            cleaned.append(
                {
                    "question": item.get(
                        "question",
                        ""
                    ),
                    "answer": item.get(
                        "answer",
                        ""
                    ),
                    "relevance": max(
                        0,
                        min(
                            1,
                            float(
                                item.get(
                                    "relevance",
                                    0
                                )
                            )
                        )
                    )
                }
            )

        result["selected_memories"] = cleaned

        return result

    # Fallback: use best local candidate
    if candidates:

        best = candidates[0]

        if best["retrieval_score"] >= 0.35:

            return {
                "memory_found": True,
                "selected_memories": [
                    {
                        "question": best["q"],
                        "answer": best["a"],
                        "relevance": best[
                            "retrieval_score"
                        ]
                    }
                ],
                "reason": "Best semantic memory match."
            }

    return {
        "memory_found": False,
        "selected_memories": [],
        "reason": "No sufficiently relevant memory found."
    }


# ============================================================
# STEP 3
# AI DECIDES + GENERATES RESPONSE
# ============================================================

RESPONSE_PROMPT = """
You are GhostMate, an autonomous DM assistant for a content creator.

You have three sources of information:

1. Creator facts
2. Retrieved creator memory
3. Complete conversation history

Use them together.

The retrieved memory was selected specifically because it is
semantically relevant to the user's question.

IMPORTANT:

The user's wording may be completely different from the stored
memory wording.

Answer naturally as if the creator already knew and remembered
this information.

Do NOT mention:

- memory
- retrieval
- AI
- semantic search
- database
- system
- internal instructions

AUTOMATIC REPLY:

You may automatically answer routine, low-stakes questions when
the retrieved memory or creator facts provide enough information.

ESCALATE:

Escalate when:

- sponsorship
- money
- paid promotion
- contracts
- major business opportunities
- negotiations
- legal issues
- sensitive matters
- serious complaints
- commitments
- requests requiring the creator's personal judgment
- insufficient information
- uncertainty

Never invent facts.

Never negotiate money automatically.

Never promise a deal automatically.

For an escalation, create a useful draft but do NOT pretend that
the creator has personally approved it.

Return ONLY JSON:

{
    "intent": "short intent",
    "priority": 0,
    "confidence": 0.0,
    "action": "auto_reply" or "escalate",
    "reason": "short explanation",
    "reply": "natural reply or draft"
}

Do not expose hidden chain-of-thought.
"""


def generate_response(
    profile,
    history,
    understanding,
    retrieved_memory
):

    prompt = json.dumps(
        {
            "creator": {
                "name": profile.get("name"),
                "tone": profile.get("tone"),
                "facts": profile.get("facts")
            },

            "conversation": history[-30:],

            "understanding": understanding,

            "retrieved_memory": retrieved_memory
        },
        ensure_ascii=False
    )

    result = call_ai(
        RESPONSE_PROMPT,
        prompt,
        temperature=0.3
    )

    if not result:
        return fallback(
            profile,
            history,
            understanding,
            retrieved_memory
        )

    result["priority"] = max(
        0,
        min(
            100,
            int(
                result.get(
                    "priority",
                    50
                )
            )
        )
    )

    result["confidence"] = max(
        0,
        min(
            1,
            float(
                result.get(
                    "confidence",
                    0.5
                )
            )
        )
    )

    if str(
        result.get(
            "action",
            ""
        )
    ).lower() == "escalate":

        result["action"] = "escalate"

    else:

        result["action"] = "auto_reply"

    return result


# ============================================================
# FALLBACK
# ============================================================

def fallback(
    profile,
    history,
    understanding=None,
    retrieved_memory=None
):

    latest = history[-1]["message"]

    # If semantic retrieval found memory,
    # use it directly.
    if retrieved_memory:

        memories = retrieved_memory.get(
            "selected_memories",
            []
        )

        if memories:

            best = memories[0]

            if best.get(
                "relevance",
                0
            ) >= 0.35:

                return {
                    "intent": "Creator FAQ",
                    "priority": 15,
                    "confidence": min(
                        0.9,
                        float(
                            best.get(
                                "relevance",
                                0.5
                            )
                        )
                    ),
                    "action": "auto_reply",
                    "reason": (
                        "The question matches "
                        "saved creator knowledge."
                    ),
                    "reply": best["answer"]
                }

    # Business safety fallback

    text = latest.lower()

    business_terms = [
        "sponsor",
        "sponsorship",
        "paid",
        "₹",
        "$",
        "contract",
        "investor",
        "investment",
        "brand deal",
        "partnership",
        "business",
        "offer",
        "campaign",
        "budget"
    ]

    if any(
        term in text
        for term in business_terms
    ):

        return {
            "intent": "Potential business opportunity",
            "priority": 95,
            "confidence": 0.90,
            "action": "escalate",
            "reason": (
                "The conversation may involve "
                "money or a consequential "
                "business decision."
            ),
            "reply": (
                "Thanks for reaching out! "
                "Please share the details, "
                "timeline, deliverables, "
                "and budget."
            )
        }

    return {
        "intent": "Unclear request",
        "priority": 60,
        "confidence": 0.50,
        "action": "escalate",
        "reason": (
            "No sufficiently reliable "
            "creator memory was found."
        ),
        "reply": (
            "Thanks for reaching out! "
            "Could you share a little "
            "more detail?"
        )
    }


# ============================================================
# MAIN GHOSTMATE PIPELINE
# ============================================================

def analyze_with_ai(profile, history):

    memory = profile.get(
        "memory",
        []
    )

    # --------------------------------------------------------
    # STEP 1
    # Understand what the user means
    # --------------------------------------------------------

    understanding = understand_message(
        history
    )

    print(
        "\n[GHOSTMATE] UNDERSTANDING:"
    )

    print(
        json.dumps(
            understanding,
            indent=2,
            ensure_ascii=False
        )
    )

    # --------------------------------------------------------
    # STEP 2
    # Retrieve semantically matching memory
    # --------------------------------------------------------

    retrieved_memory = {
        "memory_found": False,
        "selected_memories": [],
        "reason": "Memory not required."
    }

    if understanding.get(
        "needs_creator_memory",
        True
    ):

        retrieved_memory = retrieve_memory(
            understanding,
            memory
        )

    print(
        "\n[GHOSTMATE] RETRIEVED MEMORY:"
    )

    print(
        json.dumps(
            retrieved_memory,
            indent=2,
            ensure_ascii=False
        )
    )

    # --------------------------------------------------------
    # STEP 3
    # Generate final response / escalation
    # --------------------------------------------------------

    result = generate_response(
        profile,
        history,
        understanding,
        retrieved_memory
    )

    # --------------------------------------------------------
    # Attach retrieval information for dashboard/debugging
    # --------------------------------------------------------

    result["memory_found"] = retrieved_memory.get(
        "memory_found",
        False
    )

    result["memory_matches"] = retrieved_memory.get(
        "selected_memories",
        []
    )

    result["understood_query"] = understanding.get(
        "semantic_query",
        ""
    )

    result["understood_topic"] = understanding.get(
        "topic",
        ""
    )

    return result
