"""Unit tests for the registration routes, using an in-memory fake repository.

No MySQL or network is needed. The clock is fixed so start-time rules
never depend on the real date.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from app.errors import register_error_handlers
from app.routes.registrations import create_registration_blueprint

pytestmark = pytest.mark.unit

FIXED_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
EVENT_START = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)


class FakeRepository:
    """In-memory stand-in for app/repository.py with the agreed signatures."""

    def __init__(self):
        """Start with three participants, no events and no registrations."""
        self.events = {}
        self.names = {1: "Maya Okafor", 2: "Alex Chen", 3: "Sam Rivera"}
        self.rows = {}
        self.next_id = 1

    def add_event(self, event_id, capacity=2, start_time="2026-12-01T18:00:00Z"):
        """Store event event_id with the given capacity and start_time."""
        self.events[event_id] = {"startTime": start_time, "capacity": capacity}

    def get_event(self, event_id):
        """Return event event_id, or None."""
        return self.events.get(event_id)

    def get_participant(self, participant_id):
        """Return participant participant_id, or None."""
        name = self.names.get(participant_id)
        return name and {"id": participant_id, "name": name}

    def find_registration(self, event_id, participant_id):
        """Return event_id's registration for participant_id, or None."""
        matches = [
            r for r in self.for_event(event_id) if r["participantId"] == participant_id
        ]
        return matches[0] if matches else None

    def count_registrations(self, event_id):
        """Return how many registrations event_id has."""
        return len(self.for_event(event_id))

    def create_registration(self, event_id, participant_id):
        """Insert and return a registration for event_id and participant_id."""
        row = {
            "id": self.next_id,
            "eventId": event_id,
            "participantId": participant_id,
            "participantName": self.names[participant_id],
            "registeredAt": "2026-11-01T12:00:00Z",
        }
        self.rows[self.next_id] = row
        self.next_id += 1
        return row

    def delete_registration(self, event_id, registration_id):
        """Delete registration_id if it belongs to event_id; return whether it did."""
        row = self.rows.get(registration_id)
        if row is None or row["eventId"] != event_id:
            return False
        del self.rows[registration_id]
        return True

    def list_registrations_with_names(self, event_id):
        """Return event_id's registrations, including participant names."""
        return self.for_event(event_id)

    def for_event(self, event_id):
        """Return the stored rows belonging to event_id."""
        return [r for r in self.rows.values() if r["eventId"] == event_id]


def build_client(repository, now=FIXED_NOW):
    """Return a test client for the routes, with repository and a clock fixed at now."""
    app = Flask(__name__)
    register_error_handlers(app)
    app.register_blueprint(create_registration_blueprint(repository, lambda: now))
    return app.test_client()


@pytest.fixture
def repo():
    """Return a fake repository holding event 4 (capacity 2, in the future)."""
    repository = FakeRepository()
    repository.add_event(4)
    return repository


@pytest.fixture
def client(repo):
    """Return a test client wired to repo."""
    return build_client(repo)


def book(client, event_id, participant_id):
    """POST a booking of participant_id to event_id; return the response."""
    return client.post(
        f"/api/v1/events/{event_id}/registrations",
        json={"participantId": participant_id},
    )


def cancel(client, event_id, registration_id):
    """DELETE registration_id under event_id; return the response."""
    return client.delete(f"/api/v1/events/{event_id}/registrations/{registration_id}")


def error_code(response):
    """Return the error code from a JSON error response."""
    return response.get_json()["error"]["code"]


# ---- Listing ----


def test_list_returns_only_that_events_registrations_with_names(client, repo):
    """Book into two events; each listing shows only its own rows; return None."""
    repo.add_event(5)
    book(client, 4, 1)
    book(client, 5, 2)

    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 200
    assert response.get_json() == {
        "data": [
            {
                "id": 1,
                "eventId": 4,
                "participantId": 1,
                "participantName": "Maya Okafor",
                "registeredAt": "2026-11-01T12:00:00Z",
            }
        ]
    }


def test_list_empty_event_returns_empty_data(client):
    """List an event with no bookings; expect 200 and an empty array; return None."""
    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 200
    assert response.get_json() == {"data": []}


def test_list_missing_event_returns_404(client):
    """List a missing event; expect the standard 404 error body; return None."""
    response = client.get("/api/v1/events/99/registrations")

    assert response.status_code == 404
    assert response.get_json() == {
        "error": {
            "code": "EVENT_NOT_FOUND",
            "message": "Event 99 does not exist.",
            "details": {"eventId": 99},
        }
    }


def test_repository_failure_returns_generic_500(client, repo, monkeypatch):
    """Make the repository crash; expect a 500 that hides the details; return None."""

    def crash(event_id):
        raise RuntimeError("SELECT private_column FROM internal_table")

    monkeypatch.setattr(repo, "list_registrations_with_names", crash)

    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 500
    assert error_code(response) == "INTERNAL_ERROR"
    assert "private_column" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/api/v1/events/abc/registrations"),
        ("get", "/api/v1/events/-1/registrations"),
        ("post", "/api/v1/events/1.5/registrations"),
        ("delete", "/api/v1/events/4/registrations/abc"),
        ("delete", "/api/v1/events/4/registrations/-1"),
    ],
)
def test_non_integer_path_ids_return_json_404(client, method, path):
    """Call a supplied method/path with a bad ID; expect a JSON 404; return None."""
    response = getattr(client, method)(path, json={"participantId": 1})

    assert response.status_code == 404
    assert "error" in response.get_json()


# ---- Booking ----


def test_book_creates_registration(client, repo):
    """Book a free place; expect 201 with the new row; return None."""
    response = book(client, 4, 1)

    assert response.status_code == 201
    assert response.get_json()["participantName"] == "Maya Okafor"
    assert repo.count_registrations(4) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"participantId": None},
        {"participantId": "1"},
        {"participantId": 1.0},
        {"participantId": True},
        {"participantId": 0},
        {"participantId": -1},
        {"participantId": 1, "registeredAt": "2026-01-01T00:00:00Z"},
        [1],
        1,
        None,
    ],
)
def test_book_rejects_invalid_body(client, repo, body):
    """Send a supplied invalid JSON body; expect 400 and no row; return None."""
    # json.dumps so that None is sent as the JSON literal null, not "no body".
    response = client.post(
        "/api/v1/events/4/registrations",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert error_code(response) == "BAD_REQUEST"
    assert repo.count_registrations(4) == 0


@pytest.mark.parametrize(
    "data, content_type, expected_status",
    [
        ('{"participantId": ', "application/json", 400),
        ("participantId=1", "application/x-www-form-urlencoded", 415),
    ],
)
def test_book_rejects_malformed_or_non_json(
    client, repo, data, content_type, expected_status
):
    """Send broken JSON or form data; expect a JSON 400/415 error; return None."""
    response = client.post(
        "/api/v1/events/4/registrations", data=data, content_type=content_type
    )

    assert response.status_code == expected_status
    assert "error" in response.get_json()
    assert repo.count_registrations(4) == 0


@pytest.mark.parametrize(
    "event_id, participant_id, expected_code",
    [
        (99, 1, "EVENT_NOT_FOUND"),
        (4, 99, "PARTICIPANT_NOT_FOUND"),
        (99, 99, "EVENT_NOT_FOUND"),
    ],
)
def test_book_missing_event_or_participant_returns_404(
    client, repo, event_id, participant_id, expected_code
):
    """Book with a supplied missing record; expect 404 and no row; return None."""
    response = book(client, event_id, participant_id)

    assert response.status_code == 404
    assert error_code(response) == expected_code
    assert repo.rows == {}


def test_book_duplicate_returns_409(client, repo):
    """Book the same participant twice; expect 409 and one row; return None."""
    book(client, 4, 1)

    response = book(client, 4, 1)

    assert response.status_code == 409
    assert error_code(response) == "DUPLICATE_REGISTRATION"
    assert repo.count_registrations(4) == 1


def test_book_full_event_returns_409(client, repo):
    """Fill the capacity-2 event, then book a third; expect 409; return None."""
    book(client, 4, 1)
    book(client, 4, 2)

    response = book(client, 4, 3)

    assert response.status_code == 409
    assert response.get_json()["error"] == {
        "code": "EVENT_FULL",
        "message": "Event 4 has no spots left.",
        "details": {"eventId": 4, "capacity": 2},
    }
    assert repo.count_registrations(4) == 2


@pytest.mark.parametrize(
    "offset, expected_status",
    [
        (timedelta(seconds=-1), 201),
        (timedelta(0), 409),
        (timedelta(seconds=1), 409),
    ],
)
def test_book_closes_at_start_time(repo, offset, expected_status):
    """Book at a supplied offset from the start; expect open/closed; return None."""
    response = book(build_client(repo, now=EVENT_START + offset), 4, 1)

    assert response.status_code == expected_status
    if expected_status == 409:
        assert error_code(response) == "EVENT_STARTED"


@pytest.mark.parametrize(
    "start_time",
    [
        "2026-12-01T11:00:00-07:00",
        datetime(2026, 12, 1, 18, 0),
    ],
)
def test_book_reads_offset_and_mysql_start_times(repo, start_time):
    """Store a supplied start form (offset string / naive MySQL value); return None."""
    repo.add_event(5, start_time=start_time)

    before = book(build_client(repo, now=EVENT_START - timedelta(seconds=1)), 5, 1)
    at_start = book(build_client(repo, now=EVENT_START), 5, 2)

    assert before.status_code == 201
    assert error_code(at_start) == "EVENT_STARTED"


def test_book_reports_earlier_rule_when_two_fail(repo):
    """Break duplicate+full, then started+full; expect the earlier rule; return None."""
    repo.add_event(6, capacity=1)
    book(build_client(repo), 6, 1)
    after_start = build_client(repo, now=EVENT_START + timedelta(days=1))

    assert error_code(book(build_client(repo), 6, 1)) == "DUPLICATE_REGISTRATION"
    assert error_code(book(after_start, 6, 2)) == "EVENT_STARTED"


# ---- Cancellation ----


def test_cancel_deletes_registration(client, repo):
    """Cancel a booking; expect 204, empty body and the row gone; return None."""
    registration_id = book(client, 4, 1).get_json()["id"]

    response = cancel(client, 4, registration_id)

    assert response.status_code == 204
    assert response.get_data() == b""
    assert repo.count_registrations(4) == 0


def test_cancel_twice_does_not_free_extra_place(client, repo):
    """Cancel the same booking twice; second is 404, count unchanged; return None."""
    first_id = book(client, 4, 1).get_json()["id"]
    book(client, 4, 2)
    cancel(client, 4, first_id)

    response = cancel(client, 4, first_id)

    assert response.status_code == 404
    assert error_code(response) == "REGISTRATION_NOT_FOUND"
    assert repo.count_registrations(4) == 1


def test_cancel_registration_of_other_event_returns_404(client, repo):
    """Cancel event 5's booking through event 4; expect 404, row kept; return None."""
    repo.add_event(5)
    other_id = book(client, 5, 1).get_json()["id"]

    response = cancel(client, 4, other_id)

    assert error_code(response) == "REGISTRATION_NOT_FOUND"
    assert repo.count_registrations(5) == 1


def test_cancel_under_missing_event_returns_404(client, repo):
    """Cancel under a missing event; expect EVENT_NOT_FOUND, row kept; return None."""
    registration_id = book(client, 4, 1).get_json()["id"]

    response = cancel(client, 99, registration_id)

    assert error_code(response) == "EVENT_NOT_FOUND"
    assert repo.count_registrations(4) == 1


def test_cancel_allowed_after_event_starts(repo):
    """Book before start, cancel after start; expect 204 (team assumption)."""
    registration_id = book(build_client(repo), 4, 1).get_json()["id"]
    after_start = build_client(repo, now=EVENT_START + timedelta(days=1))

    assert cancel(after_start, 4, registration_id).status_code == 204


# ---- Scenarios from the assignment ----


def test_capacity_two_walkthrough(client):
    """Spec example: two book, third rejected, one cancels, third books; return None."""
    first = book(client, 4, 1)
    second = book(client, 4, 2)
    rejected = book(client, 4, 3)
    cancelled = cancel(client, 4, first.get_json()["id"])
    third = book(client, 4, 3)
    names = [
        row["participantName"]
        for row in client.get("/api/v1/events/4/registrations").get_json()["data"]
    ]

    assert [first.status_code, second.status_code] == [201, 201]
    assert error_code(rejected) == "EVENT_FULL"
    assert cancelled.status_code == 204
    assert third.status_code == 201
    assert sorted(names) == ["Alex Chen", "Sam Rivera"]


def test_rebook_after_cancel(client, repo):
    """Book, cancel and book again as one participant; expect 201; return None."""
    first_id = book(client, 4, 1).get_json()["id"]
    cancel(client, 4, first_id)

    rebooked = book(client, 4, 1)

    assert rebooked.status_code == 201
    assert rebooked.get_json()["id"] != first_id
    assert repo.count_registrations(4) == 1
