import os
import logging
import asyncio
import threading
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from neo_api_client import NeoAPI
from datetime import date, timedelta
from cachetools import TTLCache
import time

# --- Flask सर्वर सेटअप ---
app = Flask(__name__)

# --- कॉन्फ़िगरेशन (Render के Environment Variables से) ---
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
BOT_URL = os.environ.get('BOT_URL')
KOTAK_CONSUMER_KEY = os.environ.get('KOTAK_CONSUMER_KEY')
KOTAK_CONSUMER_SECRET = os.environ.get('KOTAK_CONSUMER_SECRET')
KOTAK_MOBILE_NUMBER = os.environ.get('KOTAK_MOBILE_NUMBER')
KOTAK_PASSWORD = os.environ.get('KOTAK_PASSWORD')

# --- सेशन को 2 घंटे के लिए याद रखने के लिए कैश ---
client_cache = TTLCache(maxsize=1, ttl=7200)

# --- ग्लोबल वैरिएबल्स ---
nifty_ltp_value = None
ltp_received_event = threading.Event()
# एक स्थायी event loop बनाएं
loop = asyncio.new_event_loop()

# ===================================================================
# कोटक नियो API से संबंधित फंक्शन्स (इनमें कोई बदलाव नहीं)
# ===================================================================
def initialize_and_login(totp):
    try:
        client = NeoAPI(consumer_key=KOTAK_CONSUMER_KEY, consumer_secret=KOTAK_CONSUMER_SECRET, environment='prod')
        client.login(mobilenumber=KOTAK_MOBILE_NUMBER, password=KOTAK_PASSWORD)
        client.session_2fa(OTP=totp)
        logging.info("TOTP के साथ लॉगिन सफल।")
        return client
    except Exception as e:
        logging.error(f"API लॉगिन में त्रुटि: {e}")
        return None

def get_nifty_ltp(client):
    global nifty_ltp_value
    ltp_received_event.clear()
    nifty_ltp_value = None
    def on_message(message):
        global nifty_ltp_value
        if not ltp_received_event.is_set() and message and isinstance(message, list) and len(message) > 0:
            if message[0].get('name') == 'if' and message[0].get('tk') == 'Nifty 50':
                nifty_ltp_value = float(message[0].get('iv'))
                logging.info(f"Nifty LTP Received: {nifty_ltp_value}")
                ltp_received_event.set()
    def on_open(ws):
        inst_tokens = [{"instrument_token": "Nifty 50", "exchange_segment": "nse_cm"}]
        client.subscribe(instrument_tokens=inst_tokens, isIndex=True)
    client.on_message = on_message
    client.on_open = on_open
    ws_thread = threading.Thread(target=client.connect)
    ws_thread.daemon = True
    ws_thread.start()
    ltp_received_event.wait(timeout=10)
    client.close_connection()
    return nifty_ltp_value

def find_tuesday_expiry():
    today = date.today()
    days_ahead = (1 - today.weekday() + 7) % 7
    return today if days_ahead == 0 and today.weekday() == 1 else today + timedelta(days=days_ahead)

def get_trading_symbols(client, ltp, expiry_date):
    try:
        strike_difference = 200
        atm_strike = round(ltp / 50) * 50
        otm_call_strike = atm_strike + strike_difference
        otm_put_strike = atm_strike - strike_difference
        expiry_str = expiry_date.strftime('%d%b%Y').upper()
        
        call_search = client.search_scrip(exchange_segment="nse_fo", symbol="NIFTY", expiry=expiry_str, option_type="CE", strike_price=str(otm_call_strike))
        put_search = client.search_scrip(exchange_segment="nse_fo", symbol="NIFTY", expiry=expiry_str, option_type="PE", strike_price=str(otm_put_strike))
        
        call_symbol = call_search[0]['pTrdSymbol']
        put_symbol = put_search[0]['pTrdSymbol']
        
        if not call_symbol or not put_symbol: raise Exception("Symbol not found.")
        return call_symbol, put_symbol
    except Exception as e:
        logging.error(f"Error finding trading symbols: {e}")
        return None, None

# ===================================================================
# टेलीग्राम कमांड हैंडलर्स (इनमें कोई बदलाव नहीं)
# ===================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('नमस्ते! कृपया पहले लॉगिन करें: /login <6-अंकों-का-TOTP>')

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        totp = context.args[0]
        if not totp.isdigit() or len(totp) != 6:
            await update.message.reply_text('अमान्य TOTP। उदाहरण: /login 123456')
            return
        
        await update.message.reply_text('लॉगिन किया जा रहा है...')
        client = initialize_and_login(totp)
        
        if client:
            client_cache['api_client'] = client
            await update.message.reply_text('✅ लॉगिन सफल! अब आप /trade कमांड का उपयोग कर सकते हैं।')
        else:
            await update.message.reply_text('❌ लॉगिन विफल।')
    except (IndexError, ValueError):
        await update.message.reply_text('उपयोग: /login <6-अंकों-का-TOTP>')

async def trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = client_cache.get('api_client')
    if not client:
        await update.message.reply_text('आप लॉग इन नहीं हैं। कृपया पहले लॉगिन करें: /login <TOTP>')
        return
    await update.message.reply_text('ट्रेड शुरू हो रहा है...')
    await update.message.reply_text("✅ (TEST) ट्रेड सफलतापूर्वक एक्सेक्यूट हुआ।")

# --- बॉट एप्लीकेशन बिल्डर ---
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("login", login_command))
application.add_handler(CommandHandler("trade", trade_command))

# ===================================================================
# वेबहूक के लिए Flask रूट्स
# ===================================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        # काम को स्थायी event loop को भेजें
        asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
        return 'ok'
    except Exception as e:
        logging.error(f"Webhook Error: {e}")
        return 'error'

@app.route('/set_webhook', methods=['GET'])
def set_webhook():
    future = asyncio.run_coroutine_threadsafe(application.bot.set_webhook(url=f'{BOT_URL}/webhook'), loop)
    try:
        success = future.result(timeout=10)
        return "Webhook set!" if success else "Webhook setup failed."
    except Exception as e:
        logging.error(f"Webhook set error: {e}")
        return "Webhook setup failed."

@app.route('/')
def index():
    return 'Bot is running!'

# ###################################################################
# ## बैकग्राउंड में event loop को चलाने का लॉजिक ##
# ###################################################################

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
    
    # बैकग्राउंड में event loop शुरू करें
    thread = threading.Thread(target=run_async_loop, args=(loop,))
    thread.daemon = True
    thread.start()
    
    # एप्लीकेशन को इनिशियलाइज़ करें
    asyncio.run_coroutine_threadsafe(application.initialize(), loop).result()
    
    # अब Flask सर्वर शुरू करें
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
