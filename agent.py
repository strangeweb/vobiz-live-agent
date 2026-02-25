import os
import asyncio
import uuid
import requests
import json
import sys
import io
import time
import shutil
import threading
import static_ffmpeg # Ensure ffmpeg is available for pydub (Call this BEFORE importing pydub)
static_ffmpeg.add_paths()
import speech_recognition as sr
from pydub import AudioSegment
from datetime import datetime
import edge_tts
from flask import Flask, request, send_file, url_for, render_template, jsonify, session, redirect


# Force UTF-8 encoding for Windows console to handle Hindi characters
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# Explicitly tell pydub where ffmpeg is
ffmpeg_path = shutil.which('ffmpeg')
if ffmpeg_path:
    AudioSegment.converter = ffmpeg_path


app = Flask(__name__)
app.secret_key = "vobiz_super_secret_key_123" # Required for sessions
app.config['PUBLIC_URL'] = "https://vobiz-agent.onrender.com"


# Directory to store generated audio files
AUDIO_DIR = "static/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)


# Vobiz API Credentials (NEW ACCOUNT)
VOBIZ_AUTH_ID = "MA_B8NHLT9R"
VOBIZ_AUTH_TOKEN = "ZbJmVtvYjFUF7BvAqsdxXeukSchSpoZ8iKJbH5f7vdiyG8bZERMKIypVbYK2wEnZ"
VOBIZ_ACCOUNT_ID = VOBIZ_AUTH_ID
VOBIZ_API_BASE_URL = "https://api.vobiz.ai/api/v1"


import threading
import time


# --- Dashboard Data Stores ---
recent_logs = []
HISTORY_FILE = "history.json"


def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def save_history(history_data):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history_data, f, indent=4)


def update_call_record(call_sid, updates):
    history = load_history()
    for record in history:
# Force final commit: Fix hallucination error prapt
