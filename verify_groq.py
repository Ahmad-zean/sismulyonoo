from dotenv import load_dotenv
from fastapi.testclient import TestClient

load_dotenv()
import main

key = main.get_valid_api_key()
print('key_ok=', bool(key))
print('key_prefix=', (key or '')[:15])
print('model=', main.get_available_model_name())

client = TestClient(main.app)
resp = client.get('/')
print('home_status=', resp.status_code)
print('has_sample_text=', 'Halo! Saya adalah chatbot' in resp.text or 'Silakan ajukan pertanyaan' in resp.text)

try:
    reply = main.get_bot_response('Halo, apa kabar?')
    print('reply_preview=', (reply or '')[:200])
except Exception as exc:
    print('reply_error=', type(exc).__name__, str(exc)[:200])
