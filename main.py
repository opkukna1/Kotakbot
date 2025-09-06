import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from flask import Flask
import threading

# --- Firebase Setup ---
FIREBASE_KEY_JSON_B64 = os.getenv("FIREBASE_KEY_JSON_B64")

if not FIREBASE_KEY_JSON_B64:
    raise ValueError("FIREBASE_KEY_JSON_B64 not found in environment variables")

cred_json = base64.b64decode(FIREBASE_KEY_JSON_B64).decode("utf-8")
cred_dict = json.loads(cred_json)

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Telegram Bot ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

ASK_SUBJECT, ASK_TOPIC, ASK_SUBTOPIC, WAIT_POLL = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📘 Rajasthan History", callback_data="Rajasthan History")],
        [InlineKeyboardButton("🏛️ Rajasthan Polity", callback_data="Rajasthan Polity")],
        [InlineKeyboardButton("🌍 Rajasthan Geography", callback_data="Rajasthan Geography")],
        [InlineKeyboardButton("🎭 Rajasthan Art & Culture", callback_data="Rajasthan Art & Culture")],
        [InlineKeyboardButton("💰 Rajasthan Economic Survey", callback_data="Rajasthan Economic Survey")],
        [InlineKeyboardButton("📰 Rajasthan Current Affairs", callback_data="Rajasthan Current Affairs")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("कृपया Subject चुनें:", reply_markup=reply_markup)
    return ASK_SUBJECT


async def subject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data
    context.user_data["subject"] = subject

    # Firestore में subject save
    db.collection("subjects").document(subject).set({"name": subject}, merge=True)

    # Example Topics
    topics = {
        "Rajasthan History": ["civilizations", "marwar", "amer"],
        "Rajasthan Polity": ["Constitution", "Governance"],
        "Rajasthan Geography": ["Physical", "Rivers", "Climate"],
        "Rajasthan Art & Culture": ["Dance", "Music", "Architecture"],
        "Rajasthan Economic Survey": ["Agriculture", "Industry"],
        "Rajasthan Current Affairs": ["2024", "2025"],
    }

    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in topics.get(subject, [])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"आपने चुना है: {subject}\nअब Topic चुनें:", reply_markup=reply_markup)
    return ASK_TOPIC


async def topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    context.user_data["topic"] = topic

    subject = context.user_data["subject"]

    # Firestore में topic save
    db.collection("subjects").document(subject).collection("topics").document(topic).set({"name": topic}, merge=True)

    subtopics = {
        "civilizations": ["Harrapa", "copper", "iron", "बगोर"],
        "Marwar": ["Jaswant Singh", "Durgadas Rathore"],
        "Civilisations": ["Kalibangan", "Ahar"],
        "Constitution": ["Amendments", "Articles"],
        "Governance": ["Panchayati Raj", "State Government"],
    }

    keyboard = [[InlineKeyboardButton(st, callback_data=st)] for st in subtopics.get(topic, [])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"आपने चुना है: {topic}\nअब Subtopic चुनें:", reply_markup=reply_markup)
    return ASK_SUBTOPIC


async def subtopic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subtopic = query.data
    context.user_data["subtopic"] = subtopic

    subject = context.user_data["subject"]
    topic = context.user_data["topic"]

    # Firestore में subtopic save
    db.collection("subjects").document(subject).collection("topics").document(topic).collection("subtopics").document(subtopic).set({"name": subtopic}, merge=True)

    await query.edit_message_text(f"✅ आपने चुना है: {subtopic}\nअब Poll forward करें।")
    return WAIT_POLL


async def save_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll = update.message.poll
    subtopic = context.user_data.get("subtopic")
    topic = context.user_data.get("topic")
    subject = context.user_data.get("subject")

    question = poll.question
    options = [opt.text for opt in poll.options]
    correct_option = poll.correct_option_id if poll.correct_option_id is not None else None

    question_data = {
        "question": question,
        "options": options,
        "correct_option": correct_option,
    }

    db.collection("subjects").document(subject).collection("topics").document(topic).collection("subtopics").document(subtopic).collection("questions").add(question_data)

    await update.message.reply_text(f"✅ प्रश्न '{question[:30]}...' save हो गया!")
    return WAIT_POLL


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancel किया गया।")
    return ConversationHandler.END


# --- Bot Application ---
application = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_SUBJECT: [CallbackQueryHandler(subject_handler)],
        ASK_TOPIC: [CallbackQueryHandler(topic_handler)],
        ASK_SUBTOPIC: [CallbackQueryHandler(subtopic_handler)],
        WAIT_POLL: [MessageHandler(filters.POLL, save_poll)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)
application.add_handler(conv_handler)


# --- Flask for Render ---
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Collector Bot is alive!", 200


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def run_bot():
    application.run_polling()


if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    run_bot()
