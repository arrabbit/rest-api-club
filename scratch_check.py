"""
scratch_check.py
Purpose: Throwaway manual check of the event routes. Uses Flask's test client
         and an in-memory fake repository, so no MySQL is needed.
         Run from the repo root:  python scratch_check.py
         Do not commit this file.
"""
from datetime import datetime, timezone

from flask import Flask

from app.errors import ApiError, register_error_handlers
from app.routes import events

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class Fake:
    """In-memory stand-in for app/repository.py (same row shapes)."""

    def __init__(self):
        self.rows = {
            4: {
                "id": 4, "title": "Wheel-throwing basics",
                "country": "Canada", "province": "Alberta", "city": "Calgary",
                "address": "Art Studio B, Room 214",
                "start_time": datetime(2026, 12, 5, 18, 0, 0),
                "end_time": datetime(2026, 12, 5, 20, 0, 0),
                "capacity": 2, "registered_count": 0,
            }
        }
        self.next_id = 5

    def list_events(self):
        return list(self.rows.values())

    def get_event(self, event_id):
        return self.rows.get(event_id)

    def create_event(self, title, country, province, city, address,
                     start_time, end_time, capacity):
        # Like the real repository: returns the stored columns, but no
        # registered_count (the route adds that itself).
        row = {
            "id": self.next_id, "title": title, "country": country,
            "province": province, "city": city, "address": address,
            "start_time": start_time, "end_time": end_time, "capacity": capacity,
        }
        self.rows[self.next_id] = dict(row, registered_count=0)
        self.next_id += 1
        return row

    def update_event(self, event_id, changes):
        # Like the real repository: apply the changes, return the stored columns.
        self.rows[event_id].update(changes)
        return {k: v for k, v in self.rows[event_id].items() if k != "registered_count"}

    def delete_event(self, event_id):
        del self.rows[event_id]

    def count_registrations(self, event_id):
        return self.rows[event_id]["registered_count"]


def stand_in_validator(body):
    """TEMP stand-in for Precious's validate_event_create (used only if the route module has none)."""
    wanted = ["title", "country", "province", "city", "address",
              "startTime", "endTime", "capacity"]
    missing = [name for name in wanted if name not in body]
    if missing:
        raise ApiError(400, "VALIDATION_ERROR", "Request body is invalid.",
                       {"errors": [{"field": n, "reason": "is required"} for n in missing]})
    return {
        "title": body["title"], "country": body["country"],
        "province": body["province"], "city": body["city"],
        "address": body["address"],
        "start_time": datetime.strptime(body["startTime"], TIME_FORMAT),
        "end_time": datetime.strptime(body["endTime"], TIME_FORMAT),
        "capacity": body["capacity"],
    }


def stand_in_patch_validator(body):
    """TEMP stand-in for Precious's validate_event_patch (used only if the route module has none)."""
    names = {"title": "title", "country": "country", "province": "province",
             "city": "city", "address": "address", "capacity": "capacity",
             "startTime": "start_time", "endTime": "end_time"}
    unknown = [key for key in body if key not in names]
    if not body or unknown:
        raise ApiError(400, "VALIDATION_ERROR", "Request body is invalid.",
                       {"errors": [{"field": key, "reason": "unknown field"} for key in unknown]
                        or [{"field": "body", "reason": "must not be empty"}]})
    changes = {}
    for key, value in body.items():
        if key in ("startTime", "endTime"):
            value = datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)
        changes[names[key]] = value
    return changes


def build_client():
    """Build a Flask app around the fake repository and return a test client."""
    if not hasattr(events, "validate_event_create"):
        events.validate_event_create = stand_in_validator
    if not hasattr(events, "validate_event_patch"):
        events.validate_event_patch = stand_in_patch_validator
    fake = Fake()
    app = Flask(__name__)
    register_error_handlers(app)
    app.register_blueprint(events.create_event_blueprint(fake))
    return app.test_client(), fake


def show(label, response):
    """Print one response: status, Location header (if any) and body."""
    print(f"\n{label}")
    print("  status  :", response.status_code)
    if response.headers.get("Location"):
        print("  Location:", response.headers["Location"])
    print("  body    :", response.get_data(as_text=True).strip())


def main():
    client, fake = build_client()
    base = "/api/v1/events"
    new_event = {
        "title": "Intro to glazing", "country": "Canada", "province": "Alberta",
        "city": "Calgary", "address": "Art Studio B, Room 214",
        "startTime": "2026-12-12T18:00:00Z", "endTime": "2026-12-12T20:00:00Z",
        "capacity": 10,
    }

    show("GET list (expect 200, data with 1 event)", client.get(base))
    show("GET /4 (expect 200)", client.get(f"{base}/4"))
    show("GET /99 (expect 404 EVENT_NOT_FOUND)", client.get(f"{base}/99"))
    show("GET /abc (expect 404 EVENT_NOT_FOUND)", client.get(f"{base}/abc"))
    show("POST valid (expect 201, Location /api/v1/events/5, registeredCount 0)",
         client.post(base, json=new_event))
    show("GET /5 (expect 200, the event just created)", client.get(f"{base}/5"))
    show("POST not JSON (expect 400 VALIDATION_ERROR)",
         client.post(base, data="not json", content_type="application/json"))
    show("POST JSON array (expect 400 VALIDATION_ERROR)", client.post(base, json=[1, 2]))
    show("POST missing fields (expect 400 VALIDATION_ERROR with details)",
         client.post(base, json={"title": "Only a title"}))

    # ---- PATCH (Step 5) ----
    show("PATCH /4 title only (expect 200, title changed, everything else same)",
         client.patch(f"{base}/4", json={"title": "Renamed"}))
    show("PATCH /4 empty body (expect 400 VALIDATION_ERROR)", client.patch(f"{base}/4", json={}))
    show("PATCH /99 (expect 404 EVENT_NOT_FOUND)", client.patch(f"{base}/99", json={"title": "x"}))
    show("PATCH /abc (expect 404 EVENT_NOT_FOUND)", client.patch(f"{base}/abc", json={"title": "x"}))
    show("PATCH /4 endTime before stored startTime (expect 400, field endTime)",
         client.patch(f"{base}/4", json={"endTime": "2026-12-05T17:00:00Z"}))
    show("PATCH /4 startTime after stored endTime (expect 400)",
         client.patch(f"{base}/4", json={"startTime": "2026-12-05T21:00:00Z"}))
    show("PATCH /4 both times, valid new range (expect 200)",
         client.patch(f"{base}/4", json={"startTime": "2026-12-06T18:00:00Z",
                                         "endTime": "2026-12-06T20:00:00Z"}))
    fake.rows[4]["registered_count"] = 2   # pretend two people have registered
    show("PATCH /4 capacity 1 with 2 registered (expect 409 CAPACITY_BELOW_REGISTRATIONS)",
         client.patch(f"{base}/4", json={"capacity": 1}))
    show("PATCH /4 capacity 2 with 2 registered (expect 200, spotsLeft 0)",
         client.patch(f"{base}/4", json={"capacity": 2}))

    # ---- DELETE (Step 6) ----
    show("DELETE /99 (expect 404 EVENT_NOT_FOUND)", client.delete(f"{base}/99"))
    show("DELETE /abc (expect 404 EVENT_NOT_FOUND)", client.delete(f"{base}/abc"))
    show("DELETE /4 with 2 registered (expect 409 EVENT_HAS_REGISTRATIONS, details eventId 4 / registeredCount 2)",
         client.delete(f"{base}/4"))
    show("GET /4 afterwards (expect 200: the event must still exist)", client.get(f"{base}/4"))
    fake.rows[4]["registered_count"] = 0   # everyone cancelled
    show("DELETE /4 with 0 registered (expect 204 and an empty body)", client.delete(f"{base}/4"))
    show("GET /4 afterwards (expect 404 EVENT_NOT_FOUND)", client.get(f"{base}/4"))


if __name__ == "__main__":
    main()
