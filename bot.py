import json
import time
import os
from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, ContextTypes, filters

# --- fill these in with your own values ---
TELEGRAM_BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
AIPIPE_TOKEN = os.environ['AIPIPE_TOKEN']
LOG_URL = "https://raw.githubusercontent.com/24f2001737/TeleBot/refs/heads/main/run.jsonl"  # see Step 5 — where run.jsonl will be hosted
# -------------------------------------------

client = OpenAI(base_url="https://aipipe.org/openai/v1", api_key=AIPIPE_TOKEN)
LOG_FILE = "run.jsonl"

# Keeps the last few messages per chat, so multi-turn questions work —
# "answer the LAST message" still needs the earlier ones for context.
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

    # Ask the AI to work out the answer. The system prompt tells it exactly how to
    # format the final reply — this is the part that MUST match what the question asked.
    system_prompt = (
    "You are a highly accurate data analyst solving automated data-analysis "
    "questions.\n\n"
    
    "IMPORTANT RULES:\n"
    
    "1. Answer the LAST user message. Earlier messages are context only.\n"
    
    "2. Return EXACTLY ONE valid JSON object and absolutely nothing else. "
    "No markdown, no code fences, and no explanations.\n"
    
    "3. Follow the exact JSON structure requested by the user.\n"
    
    "4. NEVER add extra keys. In particular, NEVER add a 'log_url' key, "
    "unless the user's message explicitly requests a 'log_url' key.\n"
    
    "5. If the user provides a list and asks for a calculation on every item, "
    "perform the calculation on EVERY item and preserve the original order.\n"
    
    "6. If the user explicitly provides a mathematical operation or formula, "
    "follow that formula exactly.\n"
    
    "7. Carefully calculate numerical answers yourself. Do not simply repeat "
    "the input values when a transformation is requested.\n"
    
    "8. For multi-turn questions, use previous messages as context but answer "
    "only the latest user request.\n"
    
    "9. The final response must be valid JSON that can be parsed using json.loads()."
)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_prompt}] + history[-6:],
    )
    reply_text = response.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply_text})

    # Make sure we actually reply with valid JSON containing "log_url" — if the model
    # forgot the log_url field or wrapped it in markdown, fix it up here so the grader
    # never sees a malformed reply.
    try:
        parsed = json.loads(reply_text)
    except json.JSONDecodeError:
        # Model added extra text — try to pull out just the {...} part.
        start, end = reply_text.find("{"), reply_text.rfind("}")
        parsed = json.loads(reply_text[start:end + 1])
    
    final_reply = json.dumps(parsed)

    log_event({"type": "outgoing", "chat_id": chat_id, "text": final_reply})
    await update.message.reply_text(final_reply)

app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
print("Bot is running... (Ctrl+C to stop)")
app.run_polling()
