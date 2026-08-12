import json
import time
import os
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters
from flask import Flask, send_file
import threading


health_app = Flask(__name__)
LOG_FILE = "run.jsonl"

@health_app.route("/")
def home():
    return "Bot is alive!", 200

@health_app.route("/health")
def health():
    return "OK", 200

@health_app.route("/run.jsonl")
def run_log():
    if not os.path.exists(LOG_FILE):
        return "", 200

    return send_file(
        LOG_FILE,
        mimetype="application/jsonl"
    )


def run_health_server():
    port = int(os.environ.get("PORT", 10000))
    health_app.run(host="0.0.0.0", port=port)
    
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
AIPIPE_TOKEN = os.environ['AIPIPE_TOKEN']
LOG_URL = "https://telebot-tds.onrender.com/run.jsonl"

client = OpenAI(base_url="https://aipipe.org/openai/v1", api_key=AIPIPE_TOKEN)


conversation_history = {}

def log_event(event: dict):
    event["timestamp"] = time.time()
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_text = update.message.text
    log_event({"type": "incoming", "chat_id": chat_id, "text": user_text})

    history = conversation_history.setdefault(chat_id, [])
    history.append({"role": "user", "content": user_text})

    
    system_prompt = (
    "You are a highly accurate data analyst solving automated data-analysis "
    "questions.\n\n"

    "IMPORTANT RULES:\n"

    "1. Answer the LAST user message. Earlier messages are context only.\n"

    "2. Return EXACTLY ONE valid JSON object and absolutely nothing else. "
    "No markdown, no code fences, and no explanations.\n"

    "3. Follow the requested answer shape exactly.\n"

    "4. Return ONLY the answer object requested by the question. "
    "Do NOT add 'log_url', 'answer', metadata, explanations, or any other "
    "wrapper unless they are explicitly part of the requested answer data.\n"

    "5. If the question asks for an object such as "
    "{\"country\": \"<country name>\"}, return exactly that object.\n"

    "6. If the user provides a list and asks for a calculation on every item, "
    "perform the calculation on EVERY item and preserve the original order.\n"

    "7. If the user explicitly provides a mathematical operation or formula, "
    "follow that formula exactly.\n"

    "8. Carefully calculate numerical answers yourself. "
    "Do not simply repeat input values when a transformation is requested.\n"

    "9. For data retrieval questions, use the information available to you "
    "and reason carefully about the requested dataset, indicator, years, "
    "countries, and calculation.\n"

    "10. For multi-turn questions, use previous messages as context but "
    "answer only the latest user request.\n"

    "11. Your response will be wrapped automatically by the Python application "
    "as {\"answer\": <your response>, \"log_url\": <public log URL>}.\n"

    "12. Therefore, NEVER generate that outer wrapper yourself.\n"

    "13. The final response must be valid JSON that can be parsed using "
    "json.loads()."
)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}] + history[-6:],
    )
    reply_text = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply_text})

    
    try:
        parsed = json.loads(reply_text)
    except json.JSONDecodeError:
        start = reply_text.find("{")
        end = reply_text.rfind("}")

        if start == -1 or end == -1:
            raise ValueError("Model did not return valid JSON")

        parsed = json.loads(reply_text[start:end + 1])


    if isinstance(parsed, dict) and "answer" in parsed:
        answer = parsed["answer"]
    else:
        answer = parsed

    final_response = {
        "answer": answer,
        "log_url": LOG_URL
    }

    final_reply = json.dumps(final_response, ensure_ascii=False)

    log_event({
        "type": "outgoing",
        "chat_id": chat_id,
        "text": final_reply
    })

    await update.message.reply_text(final_reply)

app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

print("Starting health server...")
threading.Thread(target=run_health_server, daemon=True).start()

print("Bot is running...")
app.run_polling()
