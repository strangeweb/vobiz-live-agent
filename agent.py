import os
import asyncio
import uuid
import requests
from flask import Flask, request, send_file, url_for
import edge_tts

app = Flask(__name__)

# Directory to store generated audio files
AUDIO_DIR = "static/audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Vobiz API Credentials
VOBIZ_AUTH_ID = "MA_LIWDVOO7"
VOBIZ_AUTH_TOKEN = "lchXw2vls5wuINEcaYgkuRfRXvzghrKzWhQW6xbAqX74DlhUuwLrwlNnlbTW7VOH"
VOBIZ_ACCOUNT_ID = VOBIZ_AUTH_ID
VOBIZ_API_BASE_URL = "https://api.vobiz.ai/api/v1"

# The "Simple Script" logic instead of ChatGPT
def get_bot_response(user_text):
    text = user_text.lower()
    if "hello" in text or "hi" in text:
        return "Hello there! Welcome to our Vobiz voice agent."
    elif "price" in text or "cost" in text:
        return "Our pricing is very affordable. Check our website for more details."
    elif "support" in text or "help" in text:
        return "You can reach our support team at support at example dot com."
    elif "bye" in text:
        return "Thank you for calling. Goodbye!"
    else:
        return "I am a simple voice agent. I did not understand that. Please say hello, price, or help."

# Async function to generate TTS using edge-tts
async def generate_audio(text, filename):
    # Using a common voice, you can change this
    voice = "en-US-GuyNeural"
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filename)

# Pre-generate welcome audio on startup
WELCOME_FILENAME = "welcome.mp3"
WELCOME_FILEPATH = os.path.join(AUDIO_DIR, WELCOME_FILENAME)

def pre_generate_welcome():
    if not os.path.exists(WELCOME_FILEPATH):
        print("Pre-generating welcome audio...")
        asyncio.run(generate_audio("Welcome to the Python Voice Agent. How can I help you today?", WELCOME_FILEPATH))
        print("Welcome audio generated.")

@app.route('/vobiz-webhook', methods=['POST', 'GET'])
def vobiz_webhook():
    """
    This endpoint handles the incoming webhook from Vobiz.ai
    """
    # Log incoming request details for debugging
    print(f"\n--- Incoming Webhook ---")
    print(f"Method: {request.method}")
    print(f"Values: {dict(request.values)}")

    # Assuming Vobiz sends 'SpeechResult' like Twilio or similar payload
    user_speech = request.values.get("SpeechResult", "")
    
    if not user_speech:
        # Initial greeting - use pre-generated file for speed
        bot_reply = "Welcome to the Python Voice Agent. How can I help you today?"
        audio_filename = WELCOME_FILENAME
        print("Serving pre-generated welcome audio.")
    else:
        # Generate response using our simple script instead of ChatGPT
        bot_reply = get_bot_response(user_speech)
        print(f"User said: {user_speech}")
        print(f"Agent replies: {bot_reply}")
        
        # Generate a unique filename for the audio
        audio_filename = f"{uuid.uuid4()}.mp3"
        audio_filepath = os.path.join(AUDIO_DIR, audio_filename)
        
        # Run the async edge-tts generation with error handling
        try:
            asyncio.run(generate_audio(bot_reply, audio_filepath))
            print(f"Audio generated: {audio_filename}")
        except Exception as e:
            print(f"Error generating audio: {e}")
    
    # Get the public URL for the generated audio
    # Using app.config['PUBLIC_URL'] to ensure it's the external ngrok URL
    public_base = app.config.get('PUBLIC_URL', request.host_url.rstrip('/'))
    audio_url = public_base + url_for('serve_audio', filename=audio_filename)
    print(f"Audio URL provided to Vobiz: {audio_url}")
    
    # Create Vobiz XML using <Speak> instead of <Play> for more robustness during testing
    # IMPORTANT: 'action' MUST be an absolute URL, not relative
    action_url = public_base + "/vobiz-webhook"
    
    if "goodbye" in bot_reply.lower() or "bye" in bot_reply.lower():
        vobiz_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Speak>{bot_reply}</Speak><Hangup/></Response>'
    else:
        # Use Gather with Speak nested inside
        vobiz_xml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Gather input="speech" action="{action_url}"><Speak>{bot_reply}</Speak></Gather></Response>'
        
    print(f"Responding with XML: {vobiz_xml}")
    return vobiz_xml, 200, {'Content-Type': 'application/xml'}

@app.route('/static/audio/<filename>')
def serve_audio(filename):
    """Endpoint to serve the generated MP3 files to Vobiz"""
    print(f"--- Audio Request: {filename} ---")
    filepath = os.path.join(AUDIO_DIR, filename)
    if os.path.exists(filepath):
        print(f"Serving file: {filepath}")
        return send_file(filepath, mimetype="audio/mpeg")
    print(f"File NOT found: {filepath}")
    return "File not found", 404

def make_outbound_call(to_number, from_number, webhook_url):
    """
    Function to trigger an outbound call via Vobiz API
    """
    url = f"{VOBIZ_API_BASE_URL}/Account/{VOBIZ_ACCOUNT_ID}/Call/"
    
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
        print(f"Call API Status Code: {response.status_code}")
        print(f"Call API Response: {response.text}")
        return response.json()
    except Exception as e:
        print(f"Error making outbound call: {e}")
        return None

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
        print(f"Using Production Public URL: {app.config['PUBLIC_URL']}")

    if not is_production:
        # Local development setup
        from pyngrok import ngrok
        import threading

        def trigger_call(webhook_url):
            # Small delay to ensure server is up
            import time
            time.sleep(2)
            print("\n--- Triggering Outbound Call (Local Test) ---")
            # make_outbound_call(
            #     to_number="+918707526283", 
            #     from_number="+918071387318", 
            #     webhook_url=webhook_url
            # )

        try:
            # Start ngrok tunnel
            public_url = ngrok.connect(5000).public_url
            app.config['PUBLIC_URL'] = public_url
            print(f"\n--- Local Ngrok Tunnel Active ---")
            print(f"Public URL: {public_url}")
            webhook_url = f"{public_url}/vobiz-webhook"
            
            # Pre-generate the welcome audio
            pre_generate_welcome()
            
            # threading.Thread(target=trigger_call, args=(webhook_url,)).start()
            
            app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
        except Exception as e:
            print(f"Error starting local environment: {e}")
        finally:
            ngrok.kill()
    else:
        # Production setup (Render/Gunicorn)
        print("\n--- Running in PRODUCTION Mode ---")
        pre_generate_welcome()
        # In production, gunicorn usually handles running the app
        # app.run(host='0.0.0.0', port=port)
        # For production use, we usually rely on gunicorn to run it.
        # But we can keep it for flexibility.
        app.run(host='0.0.0.0', port=port)
