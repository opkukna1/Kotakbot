import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)
from flask import Flask, request

# --- Firebase Setup ---
FIREBASE_KEY_JSON_B64 = os.getenv("FIREBASE_KEY_JSON_B64")
cred_json = base64.b64decode(FIREBASE_KEY_JSON_B64).decode("utf-8")
cred_dict = json.loads(cred_json)

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com

# --- Flask App ---
flask_app = Flask(__name__)

# --- States ---
ASK_Q_SUBJECT, ASK_Q_SUBSUBJECT, ASK_Q_TOPIC, ASK_Q_TEXT, ASK_Q_EXAM, ASK_Q_YEAR, ASK_Q_LEVEL, ASK_Q_EXPL = range(8)

# --- Start Handler ---
async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subjects = [doc.id for doc in db.collection("subjects").stream()]
    if not subjects:
        await update.message.reply_text("❌ अभी कोई subject नहीं है। पहले /start से जोड़ें।")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in subjects]
    await update.message.reply_text("📘 Subject चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_SUBJECT

async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split("|")[1]
    context.user_data["subject"] = subject

    subsubjects = [doc.id for doc in db.collection("subjects").document(subject).collection("subsubjects").stream()]
    if not subsubjects:
        await query.edit_message_text("❌ इस subject में कोई subsubject नहीं है।")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(s, callback_data=f"subsubject|{s}")] for s in subsubjects]
    await query.edit_message_text(f"✅ Subject: {subject}\n\nअब Subsubject चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_SUBSUBJECT

async def subsubject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subsubject = query.data.split("|")[1]
    context.user_data["subsubject"] = subsubject
    subject = context.user_data["subject"]

    topics = [doc.id for doc in db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").stream()]
    if not topics:
        await query.edit_message_text("❌ इस subsubject में कोई topic नहीं है।")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(t, callback_data=f"topic|{t}")] for t in topics]
    await query.edit_message_text(f"✅ Subsubject: {subsubject}\n\nअब Topic चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_TOPIC

async def topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.split("|")[1]
    context.user_data["topic"] = topic

    await query.edit_message_text(f"✅ Topic: {topic}\n\nअब Question text भेजें (Poll forward कर सकते हैं):")
    return ASK_Q_TEXT

async def save_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["question"] = update.message.text or update.message.poll.question
    await update.message.reply_text("📚 यह Question किस Exam में आया था? (Exam का नाम लिखें)")
    return ASK_Q_EXAM

async def save_exam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam"] = update.message.text.strip()
    await update.message.reply_text("📅 Exam का Year लिखें:")
    return ASK_Q_YEAR

async def save_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["year"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("Easy", callback_data="level|easy")],
        [InlineKeyboardButton("Moderate", callback_data="level|moderate")],
        [InlineKeyboardButton("Hard", callback_data="level|hard")],
    ]
    await update.message.reply_text("⚡ Difficulty Level चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_LEVEL

async def save_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    level = query.data.split("|")[1]
    context.user_data["level"] = level
    await query.edit_message_text(f"✅ Level: {level}\n\nअब Explanation लिखें:")
    return ASK_Q_EXPL

async def save_expl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["explanation"] = update.message.text.strip()
    user_id = update.message.from_user.id

    subject = context.user_data["subject"]
    subsubject = context.user_data["subsubject"]
    topic = context.user_data["topic"]

    data = {
        "question": context.user_data["question"],
        "exam": context.user_data["exam"],
        "year": context.user_data["year"],
        "level": context.user_data["level"],
        "explanation": context.user_data["explanation"],
        "user_id": user_id,
    }

    db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").document(topic).collection("questions").add(data)

    await update.message.reply_text("✅ Question Firebase में Save हो गया!")
    return ConversationHandler.END

# --- Telegram Application ---
application = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("add_question", add_question)],
    states={
        ASK_Q_SUBJECT: [CallbackQueryHandler(subject_chosen, pattern="^subject\\|")],
        ASK_Q_SUBSUBJECT: [CallbackQueryHandler(subsubject_chosen, pattern="^subsubject\\|")],
        ASK_Q_TOPIC: [CallbackQueryHandler(topic_chosen, pattern="^topic\\|")],
        ASK_Q_TEXT: [MessageHandler(filters.TEXT | filters.POLL, save_question_text)],
        ASK_Q_EXAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_exam)],
        ASK_Q_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_year)],
        ASK_Q_LEVEL: [CallbackQueryHandler(save_level, pattern="^level\\|")],
        ASK_Q_EXPL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_expl)],
    },
    fallbacks=[],
)
application.add_handler(conv_handler)

# --- Flask Webhook Endpoint ---
@flask_app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    application.update_queue.put_nowait(update)
    return "ok"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)
