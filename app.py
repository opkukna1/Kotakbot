import os
import json
import base64
import requests
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request
import io

# --- Step 1: Flask App ko Initialize Karna (Koi Badlav Nahi) ---
app = Flask(__name__)

# --- Step 2: Environment Variables se Secrets Load Karna (Koi Badlav Nahi) ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# --- Step 3: Firebase Initialization (Koi Badlav Nahi) ---
try:
    firebase_key_b64 = os.getenv('FIREBASE_KEY_JSON_B64')
    if not firebase_key_b64:
        raise ValueError("FIREBASE_KEY_JSON_B64 environment variable not found.")
    
    firebase_key_json_str = base64.b64decode(firebase_key_b64).decode('utf-8')
    service_account_info = json.loads(firebase_key_json_str)
    
    cred = credentials.Certificate(service_account_info)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialization successful!")
except Exception as e:
    print(f"CRITICAL: Firebase initialization failed: {e}")

# --- Helper Function (Koi Badlav Nahi) ---
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

# --- File Download Function (Koi Badlav Nahi) ---
def get_csv_content_from_telegram(file_id):
    try:
        get_file_path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(get_file_path_url)
        response.raise_for_status()
        file_path = response.json()['result']['file_path']
        
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        download_response = requests.get(download_url)
        download_response.raise_for_status()
        
        return download_response.text
    except Exception as e:
        print(f"Error downloading file from Telegram: {e}")
        return None

# --- MUKHYA BADLAV: CSV Upload function ko naye 'correctAnswer' logic ke liye update kiya gaya hai ---
def process_and_upload_csv(csv_content_string):
    """
    Yeh function CSV data ko process karke Firebase par upload karta hai.
    Yeh 'CorrectIndex' column ki value ko seedhe 'correctAnswer' field mein save karta hai.
    """
    try:
        csv_data = io.StringIO(csv_content_string)
        df = pd.read_csv(csv_data, engine='python', dtype=str).fillna('')
        
        if df.empty:
            return "*ERROR!* ❌\nCSV file is empty or has a wrong format."

        uploaded_count = 0
        skipped_rows = []

        for index, row in df.iterrows():
            subject = str(row.get('Subject', '')).strip()
            topic = str(row.get('Topic', '')).strip()
            # 'CorrectIndex' column se seedhe answer text le rahe hain
            correct_answer_text = str(row.get('CorrectIndex', '')).strip()

            # --- VALIDATION ---
            # Agar Subject, Topic, ya answer text mein se kuchh bhi khali hai, to skip karein
            if not subject or not topic or not correct_answer_text:
                skipped_rows.append(index + 2)
                continue

            # Dynamic Options ko handle karna
            options = []
            option_columns = sorted([col for col in df.columns if str(col).strip().startswith('Option')])
            for col in option_columns:
                option_text = str(row.get(col, '')).strip()
                if option_text:
                    options.append(option_text)
            
            # Question data tayyar karna naye format mein
            question_data = {
                'question': str(row.get('Question', '')),
                'options': options,
                'correctAnswer': correct_answer_text, # <-- YEH MUKHYA BADLAV HAI
                'explanation': str(row.get('Explanation', ''))
            }

            db.collection(subject).document(topic).collection('questions').add(question_data)
            uploaded_count += 1
        
        # Final result message banana
        result_message = f"*SAFALTA!* ✅\nTotal `{uploaded_count}` questions have been uploaded to Firebase."
        if skipped_rows:
            unique_skipped_rows = sorted(list(set(skipped_rows)))
            skipped_rows_str = ", ".join(map(str, unique_skipped_rows))
            result_message += (f"\n\n*_Soochna:_* `{len(unique_skipped_rows)}` questions were skipped due to missing 'Subject', 'Topic', "
                               f"or a blank correct answer.\n"
                               f"*Please check row numbers:* `{skipped_rows_str}` in your CSV file.")
            
        return result_message
        
    except Exception as e:
        if 'Error tokenizing data' in str(e):
            return f"*ERROR!* ❌\nUpload failed. There is a formatting error in your CSV file.\n\n*Technical Reason:* `{e}`"
        return f"*ERROR!* ❌\nUpload failed. Reason: `{e}`"


# --- Webhook (Koi Badlav Nahi) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.is_json:
        data = request.get_json()
        try:
            message = data.get('message', {})
            chat_id = str(message['chat']['id'])

            if 'text' in message:
                message_text = message['text'].strip()
                if message_text == '/start':
                    welcome_message = (
                        "Welcome! I am your Firebase Uploader Bot.\n\n"
                        "Please send me your `.csv` file with questions, and I will upload it to Firebase in the correct format."
                    )
                    send_telegram_message(chat_id, welcome_message)
                else:
                    send_telegram_message(chat_id, "Invalid command. Please use `/start` or send a CSV file directly.")
            
            elif 'document' in message:
                document = message['document']
                if document.get('mime_type') == 'text/csv' or document.get('file_name', '').endswith('.csv'):
                    send_telegram_message(chat_id, "_File received... ⏳_\n_Processing data and uploading to Firebase..._")
                    
                    file_id = document['file_id']
                    csv_content = get_csv_content_from_telegram(file_id)
                    
                    if csv_content:
                        result = process_and_upload_csv(csv_content)
                        send_telegram_message(chat_id, result)
                    else:
                        send_telegram_message(chat_id, "*ERROR!* ❌\nCould not download the file from Telegram.")
                else:
                    send_telegram_message(chat_id, "*ERROR!* ❌\nPlease send only files in `.csv` format.")
        
        except KeyError:
            pass
            
    return "OK", 200

# --- Webhook Setup (Koi Badlav Nahi) ---
def set_webhook():
    if not all([BOT_TOKEN, WEBHOOK_URL]):
        print("ERROR: BOT_TOKEN or WEBHOOK_URL environment variable not set. Cannot set webhook.")
        return
    
    webhook_api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}/webhook"
    try:
        response = requests.get(webhook_api_url)
        if response.json().get('ok'):
            print("Webhook set successfully!")
        else:
            print(f"Error setting webhook: {response.text}")
    except Exception as e:
        print(f"Error in webhook API call: {e}")

# --- App ko Chalana (Koi Badlav Nahi) ---
if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
