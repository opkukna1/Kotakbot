import os
import json
import base64
import requests
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request
import io

# --- Step 1: Flask App ko Initialize Karna ---
app = Flask(__name__)

# --- Step 2: Render Environment Variables se Secrets Load Karna ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# --- BADLAV 1: GitHub URL ab yahan seedhe code mein daala jayega ---
# Environment variable se isko hata diya gaya hai.
GITHUB_CSV_URL = "YAHAN_APNI_CSV_FILE_KA_RAW_URL_PASTE_KAREIN"

# --- Step 3: Firebase Initialization (Ismein koi badlav nahi) ---
try:
    firebase_key_b64 = os.getenv('FIREBASE_KEY_JSON_B64')
    if not firebase_key_b64:
        raise ValueError("FIREBASE_KEY_JSON_B64 environment variable nahi mila.")
    
    firebase_key_json_str = base64.b64decode(firebase_key_b64).decode('utf-8')
    service_account_info = json.loads(firebase_key_json_str)
    
    cred = credentials.Certificate(service_account_info)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialization safal raha!")
except Exception as e:
    print(f"CRITICAL: Firebase initialization fail ho gaya: {e}")

# --- Helper Functions (Inmein koi badlav nahi) ---
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram par message bhejne mein error: {e}")

def upload_data_from_github():
    try:
        if GITHUB_CSV_URL == "YAHAN_APNI_CSV_FILE_KA_RAW_URL_PASTE_KAREIN":
             return "*ERROR!* ❌\nCode mein GitHub CSV ka Raw URL nahi daala gaya hai."

        response = requests.get(GITHUB_CSV_URL)
        response.raise_for_status()
        
        csv_data = io.StringIO(response.text)
        df = pd.read_csv(csv_data).fillna('')
        
        collection_name = 'mcqs'
        for index, row in df.iterrows():
            question_data = {
                'question': str(row['Question']),
                'options': [
                    str(row['Option1']), str(row['Option2']),
                    str(row['Option3']), str(row['Option4'])
                ],
                'correctOption': int(row['CorrectOption']),
                'subject': str(row['Subject']),
                'topic': str(row['Topic']),
                'explanation': str(row['Explanation'])
            }
            db.collection(collection_name).add(question_data)
        
        return f"*SAFALTA!* ✅\nKul `{len(df)}` questions Firebase par upload ho gaye hain."
    except Exception as e:
        return f"*ERROR!* ❌\nUpload fail ho gaya. Kaaran: `{e}`"

# --- Webhook Endpoint ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.is_json:
        data = request.get_json()
        try:
            chat_id = str(data['message']['chat']['id'])
            message_text = data['message']['text'].strip()

            # --- BADLAV 2: Chat ID ka security check yahan se hata diya gaya hai ---
            # Ab yeh bot har us insaan ko reply karega jo ise message bhejega.
            # if chat_id != YOUR_CHAT_ID:
            #     return "Unauthorized", 403

            if message_text == '/start':
                send_telegram_message(chat_id, "Welcome! Main aapka Firebase Uploader Bot hoon.\n\nQuestions upload karne ke liye `/add_questions` command ka istemal karein.")
            elif message_text == '/add_questions':
                send_telegram_message(chat_id, "_Aapka command mil gaya hai... ⏳_\n_GitHub se CSV download karke Firebase par upload kiya jaa raha hai..._")
                result = upload_data_from_github()
                send_telegram_message(chat_id, result)
            else:
                send_telegram_message(chat_id, "Amanaya command. Kripya `/start` ya `/add_questions` ka istemal karein.")
        except KeyError:
            pass
    return "OK", 200

# --- Webhook Setup (Ismein koi badlav nahi) ---
def set_webhook():
    if not all([BOT_TOKEN, WEBHOOK_URL]):
        print("ERROR: BOT_TOKEN ya WEBHOOK_URL environment variable nahi mila. Webhook set nahi kiya jaa sakta.")
        return
    
    webhook_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/webhook"
    try:
        response = requests.get(webhook_api_url)
        if response.json().get('ok'):
            print("Webhook safaltapoorvak set ho gaya!")
        else:
            print(f"Webhook set karne mein error: {response.text}")
    except Exception as e:
        print(f"Webhook set API call mein error: {e}")

# --- App ko Chalana ---
if __name__ == '__main__':
    set_webhook()
    # --- BADLAV 3 (Neeche samjhaya gaya hai) ---
    # Render is 'PORT' variable ka istemal karta hai. Port 10000 set nahi karna hai.
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
