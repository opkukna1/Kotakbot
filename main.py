import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
from telegram.error import Forbidden

# --- Firebase Setup ---
FIREBASE_KEY_JSON_B64 = os.getenv("FIREBASE_KEY_JSON_B64")
cred_json = base64.b64decode(FIREBASE_KEY_JSON_B64).decode("utf-8")
cred_dict = json.loads(cred_json)

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g. https://your-app.onrender.com/webhook

# --- States ---
ASK_SUBJECT, ASK_SUBSUBJECT, ASK_TOPIC = range(3)
ASK_Q_SUBJECT, ASK_Q_SUBSUBJECT, ASK_Q_TOPIC, ASK_EXAM, ASK_YEAR, ASK_LEVEL, ASK_EXPLANATION, ASK_QUESTION = range(8)


# -------------------------------
# SAFE SEND MESSAGE
# -------------------------------
async def safe_send_message(chat_id, text, context):
    try:
        await context.bot.send_message(chat_id=chat_id, text=text)
    except Forbidden:
        print(f"❌ User {chat_id} blocked the bot.")


# -------------------------------
# SUBJECT CREATION FLOW (/start)
# -------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📘 Subject नाम लिखें:")
    return ASK_SUBJECT


async def subject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    context.user_data["subject"] = subject
    await update.message.reply_text(f"✅ Subject: {subject}\nअब Sub Subject लिखें:")
    return ASK_SUBSUBJECT


async def subsubject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subsubject = update.message.text.strip()
    context.user_data["subsubject"] = subsubject
    await update.message.reply_text(f"✅ Sub Subject: {subsubject}\nअब Topic लिखें:")
    return ASK_TOPIC


async def topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text.strip()
    subject = context.user_data.get("subject")
    subsubject = context.user_data.get("subsubject")

    db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").document(topic).set(
        {"name": topic}, merge=True
    )

    await update.message.reply_text(
        f"✅ Saved!\n\nSubject → {subject}\nSub Subject → {subsubject}\nTopic → {topic}\n\n"
        "👉 /start (नया structure जोड़ें)\n👉 /add_question (Question जोड़ें)"
    )
    return ConversationHandler.END


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Conversation बंद किया गया।")
    return ConversationHandler.END


conv_handler_subject = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, subject_handler)],
        ASK_SUBSUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, subsubject_handler)],
        ASK_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, topic_handler)],
    },
    fallbacks=[CommandHandler("close", close)],
)


# -------------------------------
# QUESTION ADD FLOW (/add_question)
# -------------------------------
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
        await query.edit_message_text("❌ इस subject में कोई subsubject नहीं है। पहले /start से जोड़ें।")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(ss, callback_data=f"subsubject|{ss}")] for ss in subsubjects]
    await query.edit_message_text(f"✅ Subject: {subject}\n\nअब SubSubject चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_SUBSUBJECT


async def subsubject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    subsubject = query.data.split("|")[1]
    context.user_data["subsubject"] = subsubject

    subject = context.user_data["subject"]
    topics = [doc.id for doc in db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").stream()]
    if not topics:
        await query.edit_message_text("❌ इस subsubject में कोई topic नहीं है। पहले /start से जोड़ें।")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(t, callback_data=f"topic|{t}")] for t in topics]
    await query.edit_message_text(f"✅ SubSubject: {subsubject}\n\nअब Topic चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_TOPIC


async def topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    topic = query.data.split("|")[1]
    context.user_data["topic"] = topic

    await query.edit_message_text(f"✅ Topic: {topic}\n\nअब Exam का नाम लिखें:")
    return ASK_EXAM


async def exam_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["exam"] = update.message.text.strip()
    await update.message.reply_text("📅 Exam Year लिखें:")
    return ASK_YEAR


async def year_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["year"] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton("🟢 Easy", callback_data="level|Easy")],
        [InlineKeyboardButton("🟡 Moderate", callback_data="level|Moderate")],
        [InlineKeyboardButton("🔴 Hard", callback_data="level|Hard")],
    ]
    await update.message.reply_text("⚖️ Difficulty Level चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_LEVEL


async def level_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    level = query.data.split("|")[1]
    context.user_data["level"] = level

    await query.edit_message_text(f"✅ Level: {level}\n\nअब Explanation लिखें:")
    return ASK_EXPLANATION


async def explanation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["explanation"] = update.message.text.strip()
    await update.message.reply_text("📨 अब Question Poll forward करें:")
    return ASK_QUESTION


async def question_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.poll:
        await update.message.reply_text("❌ कृपया Poll Question forward करें।")
        return ASK_QUESTION

    poll_id = update.message.poll.id
    user_id = update.message.from_user.id

    subject = context.user_data["subject"]
    subsubject = context.user_data["subsubject"]
    topic = context.user_data["topic"]

    question_data = {
        "poll_id": poll_id,
        "exam": context.user_data["exam"],
        "year": context.user_data["year"],
        "level": context.user_data["level"],
        "explanation": context.user_data["explanation"],
        "added_by": user_id
    }

    db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").document(topic).collection("questions").add(question_data)

    await update.message.reply_text("✅ Question Firebase में सेव हो गया।\n👉 /add_question नया question जोड़ने के लिए")
    return ConversationHandler.END


conv_handler_question = ConversationHandler(
    entry_points=[CommandHandler("add_question", add_question)],
    states={
        ASK_Q_SUBJECT: [CallbackQueryHandler(subject_chosen, pattern="^subject\\|")],
        ASK_Q_SUBSUBJECT: [CallbackQueryHandler(subsubject_chosen, pattern="^subsubject\\|")],
        ASK_Q_TOPIC: [CallbackQueryHandler(topic_chosen, pattern="^topic\\|")],
        ASK_EXAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, exam_handler)],
        ASK_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, year_handler)],
        ASK_LEVEL: [CallbackQueryHandler(level_handler, pattern="^level\\|")],
        ASK_EXPLANATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, explanation_handler)],
        ASK_QUESTION: [MessageHandler(filters.FORWARDED & filters.POLL, question_handler)],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
)


# -------------------------------
# APPLICATION
# -------------------------------
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(conv_handler_subject)   # /start flow
application.add_handler(conv_handler_question)  # /add_question flow


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )
