from fastapi.testclient import TestClient
from main import app

c = TestClient(app)
r = c.post('/chat', json={'message': 'Halo, apa kabar?'})
print('status=', r.status_code)
print(r.json())
