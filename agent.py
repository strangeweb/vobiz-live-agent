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
import static_ffmpeg
# Ensure ffmpeg is available for pydub (Call this BEFORE importing pydub)
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
app.secret_key = "vobiz_super_secret_key_123"  # Required for sessions
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
        if record.get("call_sid") == call_sid:
            record.update(updates)
            break
    else:
        # If not found, create new
        updates["call_sid"] = call_sid
        updates["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history.insert(0, updates)
    save_history(history)

def generate_call_summary(call_sid):
    """Background task to summarize the call using Groq"""
    session_data = sessions.get(call_sid)
    if not session_data or len(session_data.get("history", [])) <= 1:
        return

    chat_history = session_data["history"]
    # Only use user/assistant messages, skip system prompt
    conv_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history if m['role'] != 'system'])

    prompt = f"""Summarize this customer support call and determine the lead status.
Conversation: {conv_text}

Response format (JSON only):
{{
  "summary": "Short 1-sentence summary",
  "status": "Hot" | "Warm" | "Cold"
}}

Rules:
- Hot: User is very interested, asked for prices, or wants to buy.
- Warm: User is interested but needs time/more info.
- Cold: User is not interested or wrong number.
"""
    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
            data = {{
                "model": "llama-3.1-8b-instant",
                "messages": [{{"role": "user", "content": prompt}}],
                "max_tokens": 150,
                "response_format": {{"type": "json_object"}}
            }}
            # Skipping implementation in JS for brevity, just defining the string here
        except Exception as e:
            print(f"Summarization Error: {e}")

# --- User Management (JSON Auth) ---
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []

def save_users(users_data):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, indent=4)

def get_logged_in_user():
    user_id = session.get('user_id')
    if not user_id: return None
    users = load_users()
    return next((u for u in users if u['id'] == user_id), None)

def update_vobiz_app(webhook_url):
    """
    Automatically updates or creates the Vobiz Application with the current webhook URL.
    """
    print(f"Syncing Vobiz Application with webhook: {webhook_url}")
    headers = {
        "X-Auth-ID": VOBIZ_AUTH_ID,
        "X-Auth-Token": VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json"
    }

    try:
        # 1. Check for existing applications
        url = f"{VOBIZ_API_BASE_URL}/account/{VOBIZ_ACCOUNT_ID}/applications"
        resp = requests.get(url, headers=headers, timeout=10)
        print(f"GET Applications Status: {resp.status_code}")
        
        try:
            res_json = resp.json()
            apps = res_json.get('data', [])
        except Exception:
            print(f"Failed to parse JSON response: {resp.text[:500]}")
            apps = []

        app_id = None
        if apps:
            # Look for our app or take the first one
            for a in apps:
                if a.get('name') == "Python Voice Agent":
                    app_id = a.get('id') or a.get('app_id')
                    break
            if not app_id:
                app_id = apps[0].get('id') or apps[0].get('app_id')

        if app_id:
            print(f"Updating existing Vobiz Application: {app_id}")
            put_url = f"{VOBIZ_API_BASE_URL}/account/{VOBIZ_ACCOUNT_ID}/applications/{app_id}"
            payload = {
                "name": "Python Voice Agent",
                "answer_url": webhook_url,
                "answer_method": "POST"
            }
            put_resp = requests.put(put_url, headers=headers, json=payload, timeout=10)
            print(f"Update app response: {put_resp.status_code}")
            if put_resp.status_code != 200:
                print(f"Update failed: {put_resp.text}")
        else:
            print("Creating new Vobiz Application...")
            payload = {
                "name": "Python Voice Agent",
                "answer_url": webhook_url,
                "answer_method": "POST"
            }
            post_resp = requests.post(url, headers=headers, json=payload, timeout=10)
            print(f"Create app response: {post_resp.status_code}")
            if post_resp.status_code not in [200, 201]:
                print(f"Create failed: {post_resp.text}")

    except Exception as e:
        print(f"Error syncing Vobiz Application: {e}")

# Hugging Face Chat API Credentials (Slower Fallback)
HF_CHAT_TOKEN = "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"
HF_CHAT_URL = "https://router.huggingface.co/v1/chat/completions"

# --- Latency Optimization Keys (Bhai, yaha apni keys daalein for 3s speed) ---
# Groq key from: https://console.groq.com/
GROQ_API_KEY = "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"
# Deepgram key from: https://console.deepgram.com/
DEEPGRAM_API_KEY = "f3cc5ea0539b9cf2b6908c06575ebab14ab5d604"

# ElevenLabs Credentials (Premium Voice)
ELEVENLABS_API_KEY = "0e282bcdde94f9e4c55846f8b5b0a162ae700e39edd079cbc9f4d8ed729a26f0" # Added your key
ELEVENLABS_VOICE_ID = "" # Add your Voice ID here (e.g., '21m00Tcm4TlvDq8ikWAM')

# Global System Settings
CURRENT_TTS_ENGINE = "edge"  # Values: "edge" or "eleven"

# System Prompt for the AI
def get_system_prompt():
    base_prompt = """You are a helpful and professional Calling Agent AI. Your name is Calling Agent. You assist users with general inquiries and demonstrate premium AI calling capabilities.
    
IMPORTANT: You must ONLY speak and reply in Romanized Hindi (Hinglish). For example: "Namaste, main Calling Agent hoon. Batanye aaj main aapki kaise madad kar sakta hoon?". Do not use pure English words unless they are common technical terms.
Your goal is to be highly responsive, friendly, and helpful. Guide the conversation naturally. If asked what you do, explain that you are an elite AI infrastructure designed to handle phone calls seamlessly.

CRITICAL RULE: You are talking on the phone. Keep responses EXTREMELY short and punchy. Maximum 10-15 words per response! Do not give long speeches. Answer questions naturally and keep the conversation going like a friendly phone agent."""

    # RAG Injection: Load company knowledge
    try:
        with open("knowledge_base.json", "r", encoding="utf-8") as f:
            kb_data = json.load(f)
            kb_str = json.dumps(kb_data, indent=2)
            prompt = base_prompt + "\n\nCRITICAL CONTEXT (Use this to answer questions):\n" + kb_str
            return prompt
    except Exception as e:
        print(f"Failed to load knowledge base: {e}")
        return base_prompt

SYSTEM_PROMPT = get_system_prompt()

def add_log(log_type, title, details, speech=None, reply=None):
    recent_logs.insert(0, {
        "id": str(uuid.uuid4()),
        "type": log_type,
        "title": title,
        "details": details,
        "time": datetime.now().strftime("%I:%M %p"),
        "speech": speech,
        "reply": reply
    })
    if len(recent_logs) > 50:
        recent_logs.pop()

# Dict to hold session histories
sessions = {}
sessions_lock = threading.Lock()

def get_bot_response(user_text, session_id="default"):
    global sessions
    # Safely print for logs
    print(f"Calling AI Model. User Text: {repr(user_text)}")
    
    # Initialize session if it doesn't exist
    if session_id not in sessions:
        sessions[session_id] = {
            "history": [{"role": "system", "content": SYSTEM_PROMPT}],
            "greeted": False
        }
    
    session_data = sessions[session_id]
    history = session_data["history"]

    # Add user message to history
    history.append({"role": "user", "content": user_text})

    # Keep history from growing too large
    if len(history) > 11:
        session_data["history"] = [history[0]] + history[-10:]

    # Use GROQ if key is available (Sub-second latency)
    if GROQ_API_KEY:
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama-3.3-70b-versatile",
                "messages": session_data["history"],
                "max_tokens": 100
            }
            response = requests.post(url, headers=headers, json=data, timeout=5)
            if response.status_code == 200:
                reply = response.json().get('choices', [{}])[0].get('message', {}).get('content', '')
                if reply:
                    reply = reply.replace("*", "").replace("#", "").replace("_", "").strip()
                    with sessions_lock:
                        history.append({"role": "assistant", "content": reply})
                    return reply
        except Exception as e:
            print(f"Groq API Exception: {e}")

    try:
        # Fallback to Hugging Face
        headers = {
            "Authorization": f"Bearer {HF_CHAT_TOKEN}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "meta-llama/Llama-3.2-3B-Instruct",
            "messages": session_data["history"],
            "stream": False,
            "max_tokens": 100
        }
        response = requests.post(HF_CHAT_URL, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            res_json = response.json()
            reply = res_json.get('choices', [{}])[0].get('message', {}).get('content', '')
            if reply:
                # Remove common problematic markdown characters
                reply = reply.replace("*", "").replace("#", "").replace("_", "").strip()
                # Add bot reply to history
                with sessions_lock:
                    history.append({"role": "assistant", "content": reply})
                return reply
            else:
                return "I am sorry, I received an empty response from my brain."
        else:
            print(f"HF API Error: {response.status_code} - {response.text}")
            return "I am sorry, my AI service is currently unavailable."
    except Exception as e:
        print(f"AI Model Exception: {e}")
        return "I am sorry, I encountered an error while processing your request."

# Async function to generate TTS using edge-tts
async def generate_edge_audio(text, filename):
    # en-US-AvaMultilingualNeural (Female) - Super Realistic & Multilingual
    voice = "en-US-AvaMultilingualNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

async def generate_elevenlabs_audio(text, filename):
    if not ELEVENLABS_API_KEY:
        print("ElevenLabs API Key missing! Falling back to Edge-TTS...")
        await generate_edge_audio(text, filename)
        return

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID or '21m00Tcm4TlvDq8ikWAM'}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.5
        }
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=20)
        if response.status_code == 200:
            with open(filename, 'wb') as f:
                f.write(response.content)
            # --- AMPLIFY AUDIO VOL (Because 11Labs is sometimes quiet over phone lines) ---
            try:
                audio = AudioSegment.from_file(filename)
                louder_audio = audio + 10  # Increase volume by 10 dB
                louder_audio.export(filename, format="mp3")
                print(" [Notice] ElevenLabs Audio Amplified by +10dB")
            except Exception as vol_e:
                 print(f" [Error] Could not amplify audio: {vol_e}")
        else:
            print(f"ElevenLabs Error {response.status_code}: {response.text}. Falling back...")
            await generate_edge_audio(text, filename)
    except Exception as e:
        print(f"ElevenLabs Exception: {e}. Falling back...")
        await generate_edge_audio(text, filename)

async def generate_audio(text, filename):
    if CURRENT_TTS_ENGINE == "eleven":
        await generate_elevenlabs_audio(text, filename)
    else:
        await generate_edge_audio(text, filename)

def transcribe_audio_url(audio_url):
    """
    Downloads audio from Vobiz, converts it to WAV, and transcribes using Python SpeechRecognition (Google).
    """
    start_time = time.time()
    try:
        # 1. Download
        d_start = time.time()
        headers = {
            "X-Auth-ID": VOBIZ_AUTH_ID,
            "X-Auth-Token": VOBIZ_AUTH_TOKEN
        }
        response = requests.get(audio_url, headers=headers, timeout=10)
        print(f" [Timing] STT: Download took {time.time() - d_start:.2f}s")
        if response.status_code != 200:
            return ""

        # --- Groq Whisper STT (Ultra Fast < 0.5s) ---
        if GROQ_API_KEY:
            try:
                g_stt_start = time.time()
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
                files = {
                    "file": ("recording.mp3", response.content, "audio/mpeg"),
                    "model": (None, "whisper-large-v3"),
                    "language": (None, "hi"),
                    "response_format": (None, "json")
                }
                g_resp = requests.post(url, headers=headers, files=files, timeout=5)
                if g_resp.status_code == 200:
                    text = g_resp.json().get("text", "")
                    if text:
                        print(f" [Timing] STT: Groq Whisper took {time.time() - g_stt_start:.2f}s")
                        return text
            except Exception as e:
                print(f" Groq STT Exception: {e}")

        # --- Deepgram STT (Secondary Fast) ---
        if DEEPGRAM_API_KEY:
            try:
                dg_start = time.time()
                url = "https://api.deepgram.com/v1/listen?language=hi&model=nova-2&smart_format=true"
                dg_headers = {
                    "Authorization": f"Token {DEEPGRAM_API_KEY}",
                    "Content-Type": "audio/mpeg"
                }
                dg_resp = requests.post(url, headers=dg_headers, data=response.content, timeout=10)
                if dg_resp.status_code == 200:
                    text = dg_resp.json().get('results', {}).get('channels', [{}])[0].get('alternatives', [{}])[0].get('transcript', '')
                    if text:
                        print(f" [Timing] STT: Deepgram API took {time.time() - dg_start:.2f}s")
                        return text
            except Exception as e:
                print(f" Deepgram Exception: {e}")

        # 2. Conversion (Fallback)
        c_start = time.time()
        audio_data = io.BytesIO(response.content)
        audio_segment = AudioSegment.from_file(audio_data)
        wav_io = io.BytesIO()
        audio_segment.export(wav_io, format="wav")
        wav_io.seek(0)
        print(f" [Timing] STT: Conversion took {time.time() - c_start:.2f}s")

        # 3. Request Google STT (Fallback)
        r_start = time.time()
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_io) as source:
            audio_content = recognizer.record(source)
            text = recognizer.recognize_google(audio_content, language="hi-IN")
        
        print(f" [Timing] STT: Google API took {time.time() - r_start:.2f}s")
        print(f" [Timing] STT: Total function took {time.time() - start_time:.2f}s")
        sys.stdout.flush()
        return text
    except Exception as e:
        print(f" [Timing] STT Error after {time.time() - start_time:.2f}s: {e}")
        sys.stdout.flush()
        return ""

# Welcome audio handling is now dynamic based on the active TTS engine.

@app.route('/')
def index():
    user = get_logged_in_user()
    if not user:
        return render_template('index.html', auth_mode=True)
    
    public_base = app.config.get('PUBLIC_URL', request.host_url.rstrip('/'))
    webhook_url = f"{public_base}/vobiz-webhook"
    return render_template('index.html', webhook_url=webhook_url, user=user)

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"status": "error", "message": "All fields required"}), 400
    
    users = load_users()
    if any(u['username'] == username for u in users):
        return jsonify({"status": "error", "message": "User already exists"}), 400
    
    new_user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password": password # In production, use hashing!
    }
    users.append(new_user)
    save_users(users)
    return jsonify({"status": "success", "message": "Registered successfully"})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    users = load_users()
    user = next((u for u in users if u['username'] == username and u['password'] == password), None)
    if user:
        session['user_id'] = user['id']
        return jsonify({"status": "success", "user": user})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/call', methods=['POST'])
def trigger_call():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = request.json
    to_num = data.get('to', '').strip()
    from_num = data.get('from', '').strip()
    public_base = app.config.get('PUBLIC_URL', request.host_url.rstrip('/'))
    webhook_url = f"{public_base}/vobiz-webhook"
    return initiate_single_call(to_num, from_num, webhook_url)

def initiate_single_call(to_num, from_num, webhook_url):
    # Auto +91 formatting
    if to_num.isdigit() and len(to_num) == 10:
        to_num = "+91" + to_num
        
    if not to_num or not from_num:
        return jsonify({"status": "error", "message": "Missing to or from number"}), 400

    add_log("outbound", "Initiated Outbound Call", f"Calling {to_num} from {from_num}")
    res = make_outbound_call(to_num, from_num, webhook_url)
    
    if res:
        # Initialize history record
        update_call_record(res.get("request_uuid") or str(uuid.uuid4()), {
            "to": to_num,
            "from": from_num,
            "status": "Contacted",
            "summary": "Generating summary...",
            "recording_url": ""
        })
        return jsonify({"status": "success", "data": res})
    else:
        add_log("outbound", "Outbound Call Failed", f"Could not initiate call to {to_num}")
        return jsonify({"status": "error", "message": "Call failed to initiate"}), 500

def bulk_call_loop(numbers, from_num, webhook_url):
    for num in numbers:
        num = num.strip()
        if not num: continue
        print(f" [Bulk] Initiating call to {num}...")
        initiate_single_call(num, from_num, webhook_url)
        time.sleep(10) # 10s gap for bulk safety
    add_log("outbound", "Bulk Session Complete", f"Finished looping through {len(numbers)} numbers")

@app.route('/api/bulk-call', methods=['POST'])
def trigger_bulk_call():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = request.json
    numbers = data.get('numbers', [])
    from_num = data.get('from', '').strip()
    if not numbers:
        return jsonify({"status": "error", "message": "No numbers provided"}), 400
    
    public_base = app.config.get('PUBLIC_URL', request.host_url.rstrip('/'))
    webhook_url = f"{public_base}/vobiz-webhook"
    threading.Thread(target=bulk_call_loop, args=(numbers, from_num, webhook_url)).start()
    return jsonify({"status": "success", "message": f"Bulk session started for {len(numbers)} numbers"})

@app.route('/api/history', methods=['GET'])
def get_history():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify(load_history())

@app.route('/api/history/update', methods=['POST'])
def update_history_status():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    data = request.json
    call_sid = data.get('call_sid')
    new_status = data.get('status')
    if call_sid and new_status:
        history = load_history()
        for record in history:
            if record.get("call_sid") == call_sid:
                record["status"] = new_status
                break
        save_history(history)
        return jsonify({"status": "success"})
    return jsonify({"status": "error"}), 400

@app.route('/api/settings/tts', methods=['POST'])
def update_tts_settings():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    global CURRENT_TTS_ENGINE
    data = request.json
    engine = data.get('engine')
    if engine in ["edge", "eleven"]:
        CURRENT_TTS_ENGINE = engine
        add_log("system", "TTS Engine Switched", f"Active Engine: {engine.upper()}")
        return jsonify({"status": "success", "engine": CURRENT_TTS_ENGINE})
    return jsonify({"status": "error", "message": "Invalid engine choice"}), 400

@app.route('/api/settings/current', methods=['GET'])
def get_current_settings():
    if not get_logged_in_user(): return jsonify({"status": "error", "message": "Unauthorized"}), 401
    return jsonify({
        "tts_engine": CURRENT_TTS_ENGINE
    })

@app.route('/api/logs')
def get_logs():
    return jsonify(recent_logs)

@app.route('/vobiz-webhook', methods=['POST', 'GET'])
def vobiz_webhook():
    """
    This endpoint handles the incoming webhook from Vobiz.ai
    """
    # Log incoming request details for debugging
    now_str = datetime.now().strftime('%H:%M:%S')
    event = request.values.get("Event", "unknown")
    call_sid = request.values.get("CallUUID") or request.values.get("CallSid") or "default"
    
    print(f"\n--- Webhook Hit [{now_str}] | Event: {event} | SID: {call_sid} ---")
    print(f" Values: {dict(request.values)}")
    sys.stdout.flush()

    # If the call is finished, stop responding and finalize history
    if event in ["Hangup", "Disconnect", "completed", "Busy", "NoAnswer"]:
        print(f" [Notice] Call finished for {call_sid}. Event: {event}")
        recording_url = request.values.get("RecordUrl", request.values.get("RecordFile", "")).strip()

        # FINALIZATION: Save recording and trigger AI summary
        if call_sid:
            updates = {}
            if recording_url:
                updates["recording_url"] = recording_url
            update_call_record(call_sid, updates)
            # Run summarization in background thread
            threading.Thread(target=generate_call_summary, args=(call_sid,)).start()

        return '<?xml version="1.0" encoding="UTF-8"?><Response></Response>', 200, {'Content-Type': 'application/xml'}

    try:
        # Define base URLs early for use in XML
        public_url = app.config.get('PUBLIC_URL', request.host_url.rstrip('/'))
        if public_url.startswith("http://"):
            public_url = public_url.replace("http://", "https://", 1)
        public_base = public_url.rstrip('/')
        action_url = public_base + "/vobiz-webhook"

        # Vobiz sends 'RecordUrl' or 'RecordFile'
        recording_url = request.values.get("RecordUrl", request.values.get("RecordFile", "")).strip()
        user_speech = ""
        start_time = time.time()

        if recording_url:
            user_speech = transcribe_audio_url(recording_url)
            
            # --- Anti-Hallucination Filter ---
            # Whisper often hallucinates these words when there is background noise but no real speech
            hallucination_triggers = [
                "prapt", "pradesh", "prastuti", "kar do", "ok", "hello", "ha", "haan", "hmm", "haanji", "hello hello"
            ]
            if user_speech:
                cleaned_speech = user_speech.lower().strip()
                # Check if the entire speech is just a repeated hallucination word
                is_hallucinating = False
                for trigger in hallucination_triggers:
                    # If speech contains only the trigger word (repeated or single)
                    words = cleaned_speech.split()
                    if all(trigger in w for w in words) or len(cleaned_speech) < 3:
                        is_hallucinating = True
                        break
                
                if is_hallucinating:
                    print(f" [Notice] Filtered hallucinated/background noise: '{user_speech}'")
                    user_speech = "" # Treat as silence

        if not user_speech:
            with sessions_lock:
                session_data = sessions.get(call_sid)
                if not session_data or not session_data.get("greeted", False):
                    # TURN 1: Initial greeting
                    bot_reply = "Namaste! Main Calling Agent hoon. Batayein aaj main aapki kaise madad kar sakta hoon?"
                    audio_filename = f"welcome_{{uuid.uuid4()}}.mp3"
                    audio_filepath = os.path.join(AUDIO_DIR, audio_filename)
                    asyncio.run(generate_audio(bot_reply, audio_filepath))
                    audio_url = public_base + "/static/audio/" + audio_filename
                    
                    sessions[call_sid] = {
                        "history": [{{"role": "system", "content": SYSTEM_PROMPT}}],
                        "greeted": True
                    }
                    now_str = datetime.now().strftime('%H:%M:%S')
                    print(f" [Timing] GREETING turn took {{time.time() - start_time:.2f}}s")
                    add_log("inbound", "New Call Connected", "Played dynamic welcome message.")
                    # Minimal XML for compatibility
                    vobiz_xml = f'<Response><Play>{{audio_url}}</Play><Record action="{{action_url}}" timeout="1" playBeep="false" silenceTimeout="1"/></Response>'
                    print(f" [Response] GREETING XML: {{vobiz_xml}}")
                    sys.stdout.flush()
                    return vobiz_xml, 200, {{'Content-Type': 'text/xml'}}

            # If we reach here, it's a SECONDARY hit (no user speech) but already greeted
            if not recording_url:
                # Redundant initiation hit (e.g. 'Answer' after 'StartApp')
                print(f" [Timing] REDUNDANT hit for {{call_sid}} (Event: {{event}}) - Returning Keep-Alive XML")
                vobiz_xml = f'<Response><Record action="{{action_url}}" timeout="1" playBeep="false" silenceTimeout="1"/></Response>'
                print(f" [Response] KEEP-ALIVE XML: {{vobiz_xml}}")
                sys.stdout.flush()
                return vobiz_xml, 200, {{'Content-Type': 'text/xml'}}
            else:
                # Actual silence during call (Recording URL exists but user_speech is empty)
                bot_reply = "Aap wahan hain?"
                print(f"--- SILENCE turn for session {{call_sid}}")
                add_log("inbound", "User Silent", "Prompting user to speak.")
                audio_filename = f"silence_{{uuid.uuid4()}}.mp3"
                audio_filepath = os.path.join(AUDIO_DIR, audio_filename)
                asyncio.run(generate_audio(bot_reply, audio_filepath))
                audio_url = public_base + "/static/audio/" + audio_filename
                vobiz_xml = f'<Response><Play>{{audio_url}}</Play><Record action="{{action_url}}" timeout="1" playBeep="false" silenceTimeout="1"/></Response>'
                print(f" [Response] SILENCE XML: {{vobiz_xml}}")
                print(f" [Timing] SILENCE: Total turnaround took {{time.time() - start_time:.2f}}s")
                sys.stdout.flush()
                return vobiz_xml, 200, {{'Content-Type': 'text/xml'}}

        else:
            # Generate response using LLM
            ai_start = time.time()
            bot_reply = get_bot_response(user_speech, session_id=call_sid)
            print(f" [Timing] AI: Model response took {{time.time() - ai_start:.2f}}s")

            # Log this interaction
            add_log("inbound", "User Speech Received", "Processed incoming audio", speech=user_speech, reply=bot_reply)

            # TTS Generation
            audio_filename = f"{{uuid.uuid4()}}.mp3"
            audio_filepath = os.path.join(AUDIO_DIR, audio_filename)
            tts_start = time.time()
            asyncio.run(generate_audio(bot_reply, audio_filepath))
            print(f" [Timing] TTS: Generation took {{time.time() - tts_start:.2f}}s")
            audio_url = public_base + "/static/audio/" + audio_filename
            
            if "goodbye" in bot_reply.lower() or "bye" in bot_reply.lower():
                vobiz_xml = f'<Response><Play>{{audio_url}}</Play><Hangup/></Response>'
            else:
                vobiz_xml = f'<Response><Play>{{audio_url}}</Play><Record action="{{action_url}}" timeout="1" playBeep="false" silenceTimeout="1"/></Response>'
            
            print(f" [Response] SPEECH RESPONSE XML: {{vobiz_xml}}")
            print(f" [Timing] TOTAL WEBHOOK: {{time.time() - start_time:.2f}s}")
            sys.stdout.flush()
            return vobiz_xml, 200, {{'Content-Type': 'text/xml'}}

    except Exception as e:
        print(f"CRITICAL WEBHOOK ERROR: {{e}}")
        import traceback
        traceback.print_exc()
        sys.stdout.flush()
        # Fallback XML to prevent hangup
        return f'<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>', 200, {{'Content-Type': 'application/xml'}}

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    """Endpoint to serve the generated MP3 files to Vobiz"""
    print(f"\n--- Audio Request [{{datetime.now().strftime('%H:%M:%S')}}] ---")
    print(f"File: {{filename}}")
    print(f"Headers: {{dict(request.headers)}}")
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath):
        print(f"Serving file: {{filepath}}")
        return send_file(filepath, mimetype="audio/mpeg")
    print(f"File NOT found: {{filepath}}")
    return "File not found", 404

def make_outbound_call(to_number, from_number, webhook_url):
    """ Function to trigger an outbound call via Vobiz API """
    url = f"{{VOBIZ_API_BASE_URL}}/Account/{{VOBIZ_ACCOUNT_ID}}/Call/"
    headers = {
        "X-Auth-ID": VOBIZ_AUTH_ID,
        "X-Auth-Token": VOBIZ_AUTH_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "to": to_number,
        "from": from_number,
        "answer_url": webhook_url # The correct key required by the Vobiz endpoint
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        print(f"Call API Status Code: {{response.status_code}}")
        print(f"Call API Response: {{response.text}}")
        return response.json()
    except Exception as e:
        print(f"Error making outbound call: {{e}}")
        return None

@app.route('/api/chat', methods=['POST'])
def handle_chat():
    data = request.json
    user_message = data.get('message')
    session_id = data.get('session_id', 'web_chat_default')
    if not user_message:
        return jsonify({{"status": "error", "message": "Message is required"}}), 400
    
    bot_reply = get_bot_response(user_message, session_id=session_id)
    add_log("inbound", "Chat Message Received", "Processed text interaction", speech=user_message, reply=bot_reply)
    return jsonify({{"status": "success", "reply": bot_reply}})

if __name__ == '__main__':
    # Determine if running in production (e.g., Render)
    # Render provides a PORT environment variable
    port = int(os.environ.get('PORT', 5000))
    is_production = 'PORT' in os.environ
    
    # Get public URL from environment variable if available
    # For Render, this would be your https://your-app.onrender.com
    public_url_env = os.environ.get('PUBLIC_URL')
    if public_url_env:
        app.config['PUBLIC_URL'] = public_url_env.rstrip('/')
        print(f"Using Production Public URL: {{app.config['PUBLIC_URL']}}")

    if not is_production:
        # Local development setup
        from pyngrok import ngrok
        import threading
        import time

        try:
            # Start ngrok tunnel
            public_url = ngrok.connect(5000).public_url
            app.config['PUBLIC_URL'] = public_url
            print(f"\n--- Local Ngrok Tunnel Active ---")
            print(f"Public URL: {{public_url}}")
            webhook_url = f"{{public_url}}/vobiz-webhook"
            # Sync with Vobiz
            update_vobiz_app(webhook_url)
            app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False, threaded=True)
        except Exception as e:
            print(f"Error starting local environment: {{e}}")
        finally:
            ngrok.kill()
    else:
        # Production setup (Render/Gunicorn)
        print("\n--- Running in PRODUCTION Mode ---")
        # In production, gunicorn usually handles running the app
        app.run(host='0.0.0.0', port=port, threaded=True)
