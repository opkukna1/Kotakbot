# -*- coding: utf-8 -*-

import re
import json
import csv
import io
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Bot Token ---
BOT_TOKEN = os.getenv('BOT_TOKEN') # Your bot token

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Firebase Initialization ---
try:
    firebase_key_b64 = os.getenv('FIREBASE_KEY_JSON_B64')
    if not firebase_key_b64: raise ValueError("FIREBASE_KEY_JSON_B64 not found.")
    firebase_key_json_str = base64.b64decode(firebase_key_b64).decode('utf-8')
    service_account_info = json.loads(firebase_key_json_str)
    cred = credentials.Certificate(service_account_info)
    if not firebase_admin._apps: firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase initialization successful!")
except Exception as e:
    print(f"CRITICAL: Firebase initialization failed: {e}")

# --- Helper & File Download Functions ---
def send_telegram_message(chat_id, text):
    # ... (function content is unchanged)
    
def get_csv_content_from_telegram(file_id):
    # ... (function content is unchanged)

# --- CSV Upload Function ---
def process_and_upload_csv(csv_content_string):
    try:
        csv_data = io.StringIO(csv_content_string)
        df = pd.read_csv(csv_data, engine='python', dtype=str).fillna('')
        
        if df.empty: return "*ERROR!* ❌\nCSV file is empty or has a wrong format."

        processed_test_series = set()
        processed_subjects = set()
        processed_topics = set()
        
        test_series_created = 0
        subjects_created = 0
        topics_created = 0
        questions_uploaded = 0
        skipped_rows = []

        required_columns = ['testSeriesId', 'testSeriesName', 'subjectId', 'subjectName', 'topicId', 'topicName', 'questionText', 'correctAnswerIndex']
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            return f"*ERROR!* ❌\nCSV file is missing required columns: `{', '.join(missing_cols)}`"

        for index, row in df.iterrows():
            test_series_id = str(row.get('testSeriesId', '')).strip()
            test_series_name = str(row.get('testSeriesName', '')).strip()
            subject_id = str(row.get('subjectId', '')).strip()
            subject_name = str(row.get('subjectName', '')).strip()
            topic_id = str(row.get('topicId', '')).strip()
            topic_name = str(row.get('topicName', '')).strip()
            question_text = str(row.get('questionText', '')).strip()
            
            if not all([test_series_id, test_series_name, subject_id, subject_name, topic_id, topic_name, question_text]):
                skipped_rows.append(index + 2)
                continue

            if test_series_id not in processed_test_series:
                test_series_data = {'name': test_series_name, 'description': str(row.get('testSeriesDescription', '')).strip()}
                db.collection('testSeries').document(test_series_id).set(test_series_data, merge=True)
                processed_test_series.add(test_series_id)
                test_series_created += 1

            if subject_id not in processed_subjects:
                subject_data = {'name': subject_name, 'testSeriesId': test_series_id}
                db.collection('subjects').document(subject_id).set(subject_data, merge=True)
                processed_subjects.add(subject_id)
                subjects_created += 1

            if topic_id not in processed_topics:
                topic_data = {'name': topic_name, 'subjectId': subject_id}
                db.collection('topics').document(topic_id).set(topic_data, merge=True)
                processed_topics.add(topic_id)
                topics_created += 1

            # THIS LINE HANDLES option0, option1, etc. AUTOMATICALLY
            options = []
            option_columns = sorted([col for col in df.columns if str(col).strip().lower().startswith('option')])
            for col in option_columns:
                option_text = str(row.get(col, '')).strip()
                if option_text: options.append(option_text)
            
            try:
                correct_index = int(row.get('correctAnswerIndex'))
            except (ValueError, TypeError):
                skipped_rows.append(index + 2)
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
        
        result_message = (
            f"*SAFALTA!* ✅\nUpload process complete.\n\n"
            f"💠 *New Test Series Created:* `{test_series_created}`\n"
            f"🔹 *New Subjects Created:* `{subjects_created}`\n"
            f"🔸 *New Topics Created:* `{topics_created}`\n"
            f"▪️ *Total Questions Uploaded:* `{questions_uploaded}`"
        )
        if skipped_rows:
            # ... (skipped rows message is unchanged)
            
        return result_message
        
    except Exception as e:
        # ... (error handling is unchanged)
        
# --- Webhook and App Run (Koi Badlav Nahi) ---
# ... (rest of the file is unchanged)
