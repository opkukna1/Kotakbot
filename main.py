import os
import json
import base64
import firebase_admin
from firebase_admin import credentials, firestore
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)

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

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

ASK_SUBJECT, ASK_SUBSUBJECT, ASK_TOPIC = range(3)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📘 कृपया Subject नाम लिखें:")
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

    # Firestore में save
    db.collection("subjects").document(subject).collection("subsubjects").document(subsubject).collection("topics").document(topic).set(
        {"name": topic}, merge=True
    )

    await update.message.reply_text(
        f"✅ Thank you!\n\nआपने जोड़ा:\nSubject → {subject}\nSub Subject → {subsubject}\nTopic → {topic}\n\n"
        "👉 /next (नया structure जोड़ें)\n👉 /close (Conversation बंद करें)"
    )
    return ConversationHandler.END


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 नया data structure जोड़ने के लिए Subject नाम लिखें:")
    return ASK_SUBJECT


async def close(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Conversation बंद किया गया।")
    return ConversationHandler.END


# --- Application ---
application = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        ASK_SUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, subject_handler)],
        ASK_SUBSUBJECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, subsubject_handler)],
        ASK_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, topic_handler)],
    },
    fallbacks=[
        CommandHandler("next", next_command),
        CommandHandler("close", close)
    ],
)

application.add_handler(conv_handler)


if __name__ == "__main__":
    application.run_polling()
