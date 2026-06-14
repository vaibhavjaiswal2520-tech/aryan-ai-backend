import os
import json
import logging
import uuid
import time

from flask import Flask, jsonify
from flask_cors import CORS
from flask_sock import Sock
from dotenv import load_dotenv
import google.generativeai as genai

# =========================
# CONFIG & LOGGING
# =========================

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found")

genai.configure(api_key=GEMINI_API_KEY)

# Specialized for Job Seekers & Mock Interviews
SYSTEM_PROMPT = """
You are Aryan AI.
Role: Expert Interview Coach, Spoken English Mentor, and Career Guide for Indian job seekers.

Your Mission:
Help Indian candidates crack job interviews by improving their fluency, confidence, and answer structuring.

Rules:
1. Speak like a professional HR/Mock Interviewer with a warm, encouraging 'Senior Bhaiya' vibe.
2. Reply in short, concise conversational sentences (max 3-4 sentences). Keep answers under 120 words.
3. If the user makes a grammatical error or uses weak vocabulary for an interview setup, politely correct them and suggest a better, professional alternative (e.g., instead of "I want job", suggest "I am looking for an opportunity").
4. Actively engage the user in mock interview scenarios. Ask relevant situational or technical-behavioral questions one by one.
5. Guide them on structuring answers using simple frameworks like STAR (Situation, Task, Action, Result) if needed.
"""

MODEL = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=SYSTEM_PROMPT
)

# =========================
# FLASK APP
# =========================

app = Flask(__name__)

CORS(
    app,
    resources={r"/*": {"origins": "*"}}
)

sock = Sock(app)

# Active chat sessions
chat_sessions = {}

# =========================
# HEALTH CHECKS
# =========================

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "service": "Aryan AI Backend",
        "version": "1.0"
    })

@app.route("/health")
def health():
    return jsonify({
        "status": "healthy"
    })

@app.route("/healthz")
def healthz():
    return jsonify({
        "ok": True
    })

# =========================
# WEBSOCKET
# =========================

@sock.route("/voice")
def voice_socket(ws):

    ws_id = str(uuid.uuid4())

    logging.info(f"Client connected: {ws_id}")

    try:
        ws.send(json.dumps({
            "type": "text",
            "message": "Namaste! I'm Aryan, your English coach. Ready to practice?",
            "timestamp": int(time.time())
        }))
    except Exception as e:
        logging.error(f"Welcome message failed: {e}")
        return

    chat_sessions[ws_id] = {
        "chat": MODEL.start_chat(history=[]),
        "last_seen": time.time()
    }

    while True:

        try:
            raw_message = ws.receive()

            if raw_message is None:
                logging.info(f"Client disconnected: {ws_id}")
                break

            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                logging.warning(f"Invalid JSON from {ws_id}")
                continue

            user_text = (
                data.get("text")
                or data.get("message")
                or data.get("content")
                or ""
            )

            if not user_text:
                continue

            session = chat_sessions.get(ws_id)

            if not session:
                break

            session["last_seen"] = time.time()

            try:

                chat = session["chat"]

                response = chat.send_message(user_text)

                ai_reply = getattr(response, "text", None)

                if not ai_reply:
                    ai_reply = (
                        "I didn't quite understand that. "
                        "Could you try saying it another way?"
                    )

                ai_reply = ai_reply.strip()

            except Exception as gemini_error:

                logging.error(
                    f"Gemini error ({ws_id}): {gemini_error}"
                )

                ws.send(json.dumps({
                    "type": "error",
                    "message": (
                        "Aryan is temporarily busy. "
                        "Please try again."
                    ),
                    "timestamp": int(time.time())
                }))

                continue

            ws.send(json.dumps({
                "type": "text",
                "message": ai_reply,
                "timestamp": int(time.time())
            }))

        except Exception as e:

            logging.error(
                f"WebSocket error ({ws_id}): {e}"
            )

            break

    chat_sessions.pop(ws_id, None)

    logging.info(f"Session cleaned: {ws_id}")

# =========================
# ENTRYPOINT
# =========================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )