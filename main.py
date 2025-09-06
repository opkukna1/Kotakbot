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

# --- Telegram Bot Token ---
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Render secrets me set karo

# --- Firebase Setup (Base64 Safe) ---
FIREBASE_KEY_JSON_B64 = os.getenv("FIREBASE_KEY_JSON_B64")

if not firebase_admin._apps:
    if not FIREBASE_KEY_JSON_B64:
        raise ValueError("⚠️ FIREBASE_KEY_JSON_B64 secret missing in Render!")

    cred_json = base64.b64decode(FIREBASE_KEY_JSON_B64).decode("utf-8")
    cred_dict = json.loads(cred_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()


# --- Bot Conversation States ---
ASK_SUBJECT, ASK_TOPIC, ASK_SUBTOPIC, WAIT_POLL = range(4)


# --- Start Command ---
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


# --- Handle Subject Selection ---
async def subject_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data
    context.user_data["subject"] = subject

    # Firebase subjects collection me store
    db.collection("subjects").document(subject).set({"name": subject}, merge=True)

    topics = {
        "Rajasthan History": ["Mewar", "Marwar", "Civilisations"],
        "Rajasthan Polity": ["Constitution", "Governance", "Administration"],
        "Rajasthan Geography": ["Physical", "Climate", "Rivers"],
        "Rajasthan Art & Culture": ["Dance", "Music", "Fairs & Festivals"],
        "Rajasthan Economic Survey": ["Agriculture", "Industry", "Services"],
        "Rajasthan Current Affairs": ["State News", "Schemes", "Government Programs"],
    }

    keyboard = [[InlineKeyboardButton(t, callback_data=t)] for t in topics.get(subject, [])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"आपने चुना है: {subject}\nअब Topic चुनें:", reply_markup=reply_markup)
    return ASK_TOPIC


# --- Handle Topic Selection ---
async def topic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data
    context.user_data["topic"] = topic

    subject = context.user_data["subject"]

    db.collection("subjects").document(subject).collection("topics").document(topic).set({"name": topic}, merge=True)

    subtopics = {
        "Mewar": ["Rana Sanga", "Rana Pratap", "Udai Singh"],
        "Marwar": ["Jaswant Singh", "Durgadas Rathore", "Ajit Singh"],
        "Constitution": ["Fundamental Rights", "Directive Principles", "Amendments"],
        "Climate": ["Desert Climate", "Rainfall", "Temperature Zones"],
    }

    keyboard = [[InlineKeyboardButton(st, callback_data=st)] for st in subtopics.get(topic, ["General"])]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"आपने चुना है: {topic}\nअब Subtopic चुनें:", reply_markup=reply_markup)
    return ASK_SUBTOPIC


# --- Handle Subtopic Selection ---
async def subtopic_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subtopic = query.data
    context.user_data["subtopic"] = subtopic

    subject = context.user_data["subject"]
    topic = context.user_data["topic"]

    db.collection("subjects").document(subject).collection("topics").document(topic).collection("subtopics").document(subtopic).set({"name": subtopic}, merge=True)

    await query.edit_message_text(f"✅ आपने चुना है: {subtopic}\nअब Poll forward करें।")
    return WAIT_POLL


# --- Save Poll (Question) ---
async def save_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
    poll = update.message.poll
    subject = context.user_data.get("subject")
    topic = context.user_data.get("topic")
    subtopic = context.user_data.get("subtopic")

    question = poll.question
    options = [opt.text for opt in poll.options]
    while len(options) < 4:
        options.append("")

    correct_option = poll.correct_option_id if poll.correct_option_id is not None else -1

    db.collection("subjects").document(subject).collection("topics").document(topic).collection("subtopics").document(subtopic).collection("questions").add({
        "question": question,
        "options": options,
        "correct_option": correct_option,
        "explanation": getattr(poll, "explanation", "")
    })

    await update.message.reply_text(f"✅ प्रश्न '{question[:30]}...' save हो गया!")
    return WAIT_POLL


# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancel किया गया।")
    return ConversationHandler.END


# --- Main ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

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

    app.add_handler(conv_handler)
    app.run_polling()


if __name__ == "__main__":
    main()
