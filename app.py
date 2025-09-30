import os
import json
import base64
import requests
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request
import io

# --- Step 1 & 2: Flask App aur Environment Variables (Koi Badlav Nahi) ---
app = Flask(__name__)
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

# --- Helper & File Download Functions (Koi Badlav Nahi) ---
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

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

# --- MUKHYA BADLAV: CSV Upload Function ko Master CSV ke liye poori tarah se badal diya gaya hai ---
def process_and_upload_csv(csv_content_string):
    """
    Yeh function Master CSV ko process karke teen alag collections (subjects, topics, questions)
    mein data upload karta hai. Yeh duplicates ko handle karta hai.
    """
    try:
        csv_data = io.StringIO(csv_content_string)
        df = pd.read_csv(csv_data, engine='python', dtype=str).fillna('')
        
        if df.empty:
            return "*ERROR!* ❌\nCSV file is empty or has a wrong format."

        # Process kiye gaye documents ko track karne ke liye sets
        processed_subjects = set()
        processed_topics = set()
        
        # Counters
        subjects_created = 0
        topics_created = 0
        questions_uploaded = 0
        skipped_rows = []

        # Zaroori columns ki list
        required_columns = ['subjectId', 'subjectName', 'topicId', 'topicName', 'questionText', 'correctAnswerIndex']
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            return f"*ERROR!* ❌\nCSV file is missing required columns: `{', '.join(missing_cols)}`"

        for index, row in df.iterrows():
            # --- Data Nikalna ---
            subject_id = str(row.get('subjectId', '')).strip()
            subject_name = str(row.get('subjectName', '')).strip()
            topic_id = str(row.get('topicId', '')).strip()
            topic_name = str(row.get('topicName', '')).strip()
            question_text = str(row.get('questionText', '')).strip()
            
            # --- Validation ---
            if not all([subject_id, subject_name, topic_id, topic_name, question_text]):
                skipped_rows.append(index + 2)
                continue

            # --- Step 1: Subject ko Process Karna ---
            if subject_id not in processed_subjects:
                subject_data = {'name': subject_name}
                db.collection('subjects').document(subject_id).set(subject_data, merge=True)
                processed_subjects.add(subject_id)
                subjects_created += 1

            # --- Step 2: Topic ko Process Karna ---
            if topic_id not in processed_topics:
                topic_data = {'name': topic_name, 'subjectId': subject_id}
                db.collection('topics').document(topic_id).set(topic_data, merge=True)
                processed_topics.add(topic_id)
                topics_created += 1

            # --- Step 3: Question ko Process Karna ---
            # Dynamic Options ko handle karna
            options = []
            option_columns = sorted([col for col in df.columns if str(col).strip().lower().startswith('option')])
            for col in option_columns:
                option_text = str(row.get(col, '')).strip()
                if option_text:
                    options.append(option_text)
            
            # Correct Answer Index ko int mein convert karna
            try:
                correct_index = int(row.get('correctAnswerIndex'))
            except (ValueError, TypeError):
                skipped_rows.append(index + 2) # Agar index number nahi hai to skip karein
                continue
            
            question_data = {
                'questionText': question_text,
                'options': options,
                'correctAnswerIndex': correct_index,
                'explanation': str(row.get('explanation', '')).strip(),
                'topicId': topic_id
            }
            db.collection('questions').add(question_data)
            questions_uploaded += 1
        
        # Final result message banana
        result_message = (
            f"*SAFALTA!* ✅\nUpload process complete.\n\n"
            f"🔹 *New Subjects Created:* `{subjects_created}`\n"
            f"🔹 *New Topics Created:* `{topics_created}`\n"
            f"🔸 *Total Questions Uploaded:* `{questions_uploaded}`"
        )
        if skipped_rows:
            unique_skipped_rows = sorted(list(set(skipped_rows)))
            skipped_rows_str = ", ".join(map(str, unique_skipped_rows))
            result_message += (f"\n\n*_Soochna:_* `{len(unique_skipped_rows)}` questions were skipped due to missing data "
                               f"or invalid 'correctAnswerIndex'.\n"
                               f"*Please check row numbers:* `{skipped_rows_str}` in your CSV file.")
            
        return result_message
        
    except Exception as e:
        if 'Error tokenizing data' in str(e):
            return f"*ERROR!* ❌\nUpload failed. There is a formatting error in your CSV file.\n\n*Technical Reason:* `{e}`"
        return f"*ERROR!* ❌\nUpload failed. Reason: `{e}`"


# --- Webhook and App Run (Koi Badlav Nahi) ---
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
                        "Please send me your master `.csv` file, and I will create subjects, topics, and questions from it."
                    )
                    send_telegram_message(chat_id, welcome_message)
                else:
                    send_telegram_message(chat_id, "Invalid command. Please send a CSV file.")
            
            elif 'document' in message:
                document = message['document']
                if document.get('mime_type') == 'text/csv' or document.get('file_name', '').endswith('.csv'):
                    send_telegram_message(chat_id, "_File received... ⏳_\n_Processing data and creating collections..._")
                    
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

if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
