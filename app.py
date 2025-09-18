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

# --- Step 2: Environment Variables se Secrets Load Karna ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# --- BADLAV 1: GitHub URL ko hata diya gaya hai ---
# Ab iski zaroorat nahi hai.
# GITHUB_CSV_URL = "https://github.com/opkukna1/Kotakbot/blob/main/questions.csv"

# --- Step 3: Firebase Initialization (Koi Badlav Nahi) ---
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

# --- Helper Function (Koi Badlav Nahi) ---
def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Telegram par message bhejne mein error: {e}")

# --- BADLAV 2: Naya function jo Telegram se file download karega ---
def get_csv_content_from_telegram(file_id):
    """
    Yeh function file_id ka istemal karke Telegram se file ka content download karta hai.
    """
    try:
        # Step 1: file_path haasil karna
        get_file_path_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}"
        response = requests.get(get_file_path_url)
        response.raise_for_status()
        file_path = response.json()['result']['file_path']
        
        # Step 2: file_path se file download karna
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        download_response = requests.get(download_url)
        download_response.raise_for_status()
        
        # File ka content text format mein return karna
        return download_response.text
    except Exception as e:
        print(f"Telegram se file download karne mein error: {e}")
        return None

# --- BADLAV 3: Puraane function ko update karke naya function banaya gaya hai ---
def process_and_upload_csv(csv_content_string):
    """
    Yeh function CSV data (string format mein) ko process karke Firebase par upload karta hai.
    """
    try:
        csv_data = io.StringIO(csv_content_string)
        # C parser error se bachne ke liye engine='python' ka istemal
        df = pd.read_csv(csv_data, engine='python').fillna('')
        
        if df.empty:
            return "*ERROR!* ❌\nCSV file khali hai ya format galat hai."

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
        # Line number wali error ko behtar tareeke se dikhana
        if 'Error tokenizing data' in str(e):
            return f"*ERROR!* ❌\nUpload fail ho gaya. Aapki CSV file mein formatting ki galti hai.\n\n*Technical Kaaran:* `{e}`"
        return f"*ERROR!* ❌\nUpload fail ho gaya. Kaaran: `{e}`"

# --- BADLAV 4: Webhook ko poori tarah se update kiya gaya hai ---
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.is_json:
        data = request.get_json()
        try:
            message = data.get('message', {})
            chat_id = str(message['chat']['id'])

            # Case 1: Agar user ne koi text message bheja hai
            if 'text' in message:
                message_text = message['text'].strip()
                if message_text == '/start':
                    welcome_message = (
                        "Welcome! Main aapka Firebase Uploader Bot hoon.\n\n"
                        "Kripya mujhe `questions.csv` file seedhe yahan bhejein aur main use Firebase par upload kar doonga."
                    )
                    send_telegram_message(chat_id, welcome_message)
                else:
                    send_telegram_message(chat_id, "Amanaya command. Kripya `/start` command dein ya seedhe CSV file bhejein.")
            
            # Case 2: Agar user ne koi document (file) bheja hai
            elif 'document' in message:
                document = message['document']
                # Check karein ki file CSV hai ya nahi
                if document.get('mime_type') == 'text/csv' or document.get('file_name', '').endswith('.csv'):
                    send_telegram_message(chat_id, "_Aapki file mil gayi hai... ⏳_\n_Data ko process karke Firebase par upload kiya jaa raha hai..._")
                    
                    file_id = document['file_id']
                    csv_content = get_csv_content_from_telegram(file_id)
                    
                    if csv_content:
                        result = process_and_upload_csv(csv_content)
                        send_telegram_message(chat_id, result)
                    else:
                        send_telegram_message(chat_id, "*ERROR!* ❌\nTelegram se file download nahi ho payi.")
                else:
                    send_telegram_message(chat_id, "*ERROR!* ❌\nKripya sirf `.csv` format ki file hi bhejein.")
        
        except KeyError:
            # Agar message format alag ho to error na aaye
            pass
            
    return "OK", 200

# --- Webhook Setup (Koi Badlav Nahi) ---
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

# --- App ko Chalana (Koi Badlav Nahi) ---
if __name__ == '__main__':
    set_webhook()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
