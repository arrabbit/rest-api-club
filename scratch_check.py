from datetime import datetime
from flask import Flask
from app.errors import register_error_handlers
from app.routes.events import create_event_blueprint


class Fake:
    def __init__(self):
        self.rows = {4: {"id": 4, "title": "Wheel-throwing basics",
                 "country": "Canada", "province": "Alberta", "city": "Calgary",
                 "address": "Art Studio B, Room 214",
                 "start_time": datetime(2026, 12, 5, 18, 0),
                 "end_time": datetime(2026, 12, 5, 20, 0),
                 "capacity": 2, "registered_count": 0}}

    def list_events(self):
        return list(self.rows.values())

    def get_event(self, event_id):
        return self.rows.get(event_id)


app = Flask(__name__)
register_error_handlers(app)
app.register_blueprint(create_event_blueprint(Fake()))
client = app.test_client()
for path in ["/api/v1/events", "/api/v1/events/4", "/api/v1/events/99", "/api/v1/events/abc"]:
    r = client.get(path)
    print(path, r.status_code, r.get_json())