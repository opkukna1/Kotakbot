import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import firebase_admin
from firebase_admin import credentials, firestore

# --- Logging setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- Load Secrets from Environment ---
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram Bot Token (Render secret)
FIREBASE_KEY_JSON = os.getenv("FIREBASE_KEY_JSON")  # Firebase Private Key JSON (Render secret)

# --- Firebase Init ---
if not firebase_admin._apps:
    cred = credentials.Certificate(eval(FIREBASE_KEY_JSON))
    firebase_admin.initialize_app(cred)
db = firestore.client()


# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_html(
        rf"Hello {user.mention_html()}! 👋 Bot is running with Firebase connection."
    )

    # Example: Save user in Firebase
    db.collection("users").document(str(user.id)).set({
        "name": user.first_name,
        "username": user.username,
    }, merge=True)


async def add_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Example command: /add_question topic question_text"""
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add_question <topic> <question>")
        return

    topic = context.args[0]
    question_text = " ".join(context.args[1:])

    db.collection("questions").add({
        "topic": topic,
        "question": question_text,
    })

    await update.message.reply_text(f"✅ Question added under topic: {topic}")


# --- Main Runner ---
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add_question", add_question))

    application.run_polling()


if __name__ == "__main__":
    main()
