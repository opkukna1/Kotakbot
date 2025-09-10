import os
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler, ContextTypes
)

# --- Firebase Setup ---
FIREBASE_KEY_JSON_B64 = os.getenv("FIREBASE_KEY_JSON_B64")
cred_json = base64.b64decode(FIREBASE_KEY_JSON_B64).decode("utf-8")
cred_dict = eval(cred_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()

# --- Conversation States ---
ASK_Q_SUBJECT, ASK_Q_SUBSUBJECT, ASK_Q_TOPIC, ASK_Q_TEXT, ASK_Q_OPTIONS, ASK_Q_ANSWER = range(6)

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Welcome! Use /add_question to add a new question.")

# --- Add Question Flow ---
async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subjects = [doc.id for doc in db.collection("subjects").stream()]
    keyboard = [[InlineKeyboardButton(s, callback_data=f"subject|{s}")] for s in subjects]
    await update.message.reply_text("📘 Subject चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_SUBJECT

async def subject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subject = query.data.split("|")[1]
    context.user_data["subject"] = subject

    subsubjects = [doc.id for doc in db.collection("subjects").document(subject).collection("subsubjects").stream()]
    keyboard = [[InlineKeyboardButton(s, callback_data=f"subsubject|{s}")] for s in subsubjects]
    await query.edit_message_text(f"📖 Subsubject चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_SUBSUBJECT

async def subsubject_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    subsubject = query.data.split("|")[1]
    context.user_data["subsubject"] = subsubject

    subject = context.user_data["subject"]
    topics = [doc.id for doc in db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").stream()]
    keyboard = [[InlineKeyboardButton(t, callback_data=f"topic|{t}")] for t in topics]
    await query.edit_message_text("📂 Topic चुनें:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_Q_TOPIC

async def topic_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    topic = query.data.split("|")[1]
    context.user_data["topic"] = topic

    await query.edit_message_text("✍️ Question लिखें:")
    return ASK_Q_TEXT

async def save_question_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["question"] = update.message.text
    await update.message.reply_text("📝 Options (comma से अलग करें, जैसे: A,B,C,D):")
    return ASK_Q_OPTIONS

async def save_question_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["options"] = update.message.text.split(",")
    await update.message.reply_text("✅ Correct Answer बताइए (option text लिखें):")
    return ASK_Q_ANSWER

async def save_question_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.message.text
    context.user_data["answer"] = answer

    subject = context.user_data["subject"]
    subsubject = context.user_data["subsubject"]
    topic = context.user_data["topic"]

    q_data = {
        "question": context.user_data["question"],
        "options": context.user_data["options"],
        "answer": context.user_data["answer"]
    }

    db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").document(topic).collection("questions").add(q_data)

    await update.message.reply_text("🎉 Question Firebase में save हो गया!")
    return ConversationHandler.END

# --- Cancel ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END

# --- Main Bot ---
def main():
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add_question", add_question)],
        states={
            ASK_Q_SUBJECT: [CallbackQueryHandler(subject_chosen, pattern="^subject\\|")],
            ASK_Q_SUBSUBJECT: [CallbackQueryHandler(subsubject_chosen, pattern="^subsubject\\|")],
            ASK_Q_TOPIC: [CallbackQueryHandler(topic_chosen, pattern="^topic\\|")],
            ASK_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_question_text)],
            ASK_Q_OPTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_question_options)],
            ASK_Q_ANSWER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_question_answer)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
