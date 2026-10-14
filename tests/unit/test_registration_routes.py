"""Unit tests for the registration routes, using an in-memory fake repository.

No MySQL or network is needed. The clock is fixed so start-time rules
never depend on the real date. The fake returns snake_case rows with
datetimes, as docs/api-contract.md says the real repository will.

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

    def add_event(self, event_id, capacity=2, start_time=datetime(2026, 12, 1, 18, 0)):
        """Store event event_id with capacity and a (naive UTC) start_time."""
        self.events[event_id] = {"start_time": start_time, "capacity": capacity}

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
            r for r in self.for_event(event_id) if r["participant_id"] == participant_id
        ]
        return matches[0] if matches else None

    def count_registrations(self, event_id):
        """Return how many registrations event_id has."""
        return len(self.for_event(event_id))

    def create_registration(self, event_id, participant_id):
        """Insert a registration for event_id/participant_id; return the row without a name."""
        self.rows[self.next_id] = {
            "id": self.next_id,
            "event_id": event_id,
            "participant_id": participant_id,
            "registered_at": datetime(2026, 11, 1, 12, 0),
        }
        self.next_id += 1
        return dict(self.rows[self.next_id - 1])

    def delete_registration(self, event_id, registration_id):
        """Delete registration_id if it belongs to event_id; return whether it did."""
        row = self.rows.get(registration_id)
        if row is None or row["event_id"] != event_id:
            return False
        del self.rows[registration_id]
        return True

    def list_registrations_with_names(self, event_id):
        """Return event_id's registrations joined with participant names."""
        return [
            {**row, "participant_name": self.names[row["participant_id"]]}
            for row in self.for_event(event_id)
        ]

    def for_event(self, event_id):
        """Return the stored rows belonging to event_id."""
        return [r for r in self.rows.values() if r["event_id"] == event_id]


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
        """Ignore event_id and raise a database-like error; never returns."""
        raise RuntimeError("SELECT private_column FROM internal_table")

    monkeypatch.setattr(repo, "list_registrations_with_names", crash)

    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 500
    assert error_code(response) == "INTERNAL_ERROR"
    assert "private_column" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "method, path, expected_code",
    [
        ("get", "/api/v1/events/abc/registrations", "EVENT_NOT_FOUND"),
        ("get", "/api/v1/events/0/registrations", "EVENT_NOT_FOUND"),
        ("get", "/api/v1/events/-1/registrations", "EVENT_NOT_FOUND"),
        ("post", "/api/v1/events/1.5/registrations", "EVENT_NOT_FOUND"),
        ("delete", "/api/v1/events/abc/registrations/1", "EVENT_NOT_FOUND"),
        ("delete", "/api/v1/events/4/registrations/abc", "REGISTRATION_NOT_FOUND"),
        ("delete", "/api/v1/events/4/registrations/0", "REGISTRATION_NOT_FOUND"),
    ],
)
def test_invalid_path_ids_return_specific_404(client, method, path, expected_code):
    """Call a supplied method/path with a bad ID; expect expected_code; return None."""
    response = getattr(client, method)(path, json={"participantId": 1})

    assert response.status_code == 404
    assert error_code(response) == expected_code


# ---- Booking ----


def test_book_creates_registration_with_location(client, repo):
    """Book a free place; expect 201, the row and a Location header; return None."""
    response = book(client, 4, 1)

    assert response.status_code == 201
    assert response.get_json() == {
        "id": 1,
        "eventId": 4,
        "participantId": 1,
        "participantName": "Maya Okafor",
        "registeredAt": "2026-11-01T12:00:00Z",
    }
    assert response.headers["Location"] == "/api/v1/events/4/registrations/1"
    assert repo.count_registrations(4) == 1


BODY_ERROR = [{"field": "body", "reason": "must be a JSON object"}]
ID_ERROR = [{"field": "participantId", "reason": "must be a positive integer"}]


@pytest.mark.parametrize(
    "body, expected_errors",
    [
        ({}, ID_ERROR),
        ({"participantId": None}, ID_ERROR),
        ({"participantId": "1"}, ID_ERROR),
        ({"participantId": 1.0}, ID_ERROR),
        ({"participantId": True}, ID_ERROR),
        ({"participantId": 0}, ID_ERROR),
        ({"participantId": -1}, ID_ERROR),
        (
            {"participantID": 1},
            [{"field": "participantID", "reason": "unknown field"}, *ID_ERROR],
        ),
        (
            {"participantId": 1, "registeredAt": "x"},
            [{"field": "registeredAt", "reason": "unknown field"}],
        ),
        ([1], BODY_ERROR),
        (1, BODY_ERROR),
        (None, BODY_ERROR),
    ],
)
def test_book_rejects_invalid_body(client, repo, body, expected_errors):
    """Send a supplied invalid body; expect 400 listing expected_errors; return None."""
    # json.dumps so that None is sent as the JSON literal null, not "no body".
    response = client.post(
        "/api/v1/events/4/registrations",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert error_code(response) == "VALIDATION_ERROR"
    assert response.get_json()["error"]["details"] == {"errors": expected_errors}
    assert repo.count_registrations(4) == 0


@pytest.mark.parametrize(
    "data, content_type",
    [
        ('{"participantId": ', "application/json"),
        ("participantId=1", "application/x-www-form-urlencoded"),
        ("", None),
    ],
)
def test_book_rejects_malformed_or_non_json(client, repo, data, content_type):
    """Send broken JSON, form data or nothing; expect 400 VALIDATION_ERROR; return None."""
    response = client.post(
        "/api/v1/events/4/registrations", data=data, content_type=content_type
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["details"] == {"errors": BODY_ERROR}
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


def test_book_reads_timezone_aware_start_time(repo):
    """Store the start as an aware -07:00 datetime; same UTC boundary; return None."""
    start = datetime(2026, 12, 1, 11, 0, tzinfo=timezone(timedelta(hours=-7)))
    repo.add_event(5, start_time=start)

    before = book(build_client(repo, now=EVENT_START - timedelta(seconds=1)), 5, 1)
    at_start = book(build_client(repo, now=EVENT_START), 5, 2)

    assert before.status_code == 201
    assert error_code(at_start) == "EVENT_STARTED"


def test_book_follows_contract_check_order(repo):
    """Break two rules at once; expect 400 > 404 > duplicate > started; return None."""
    repo.add_event(6, capacity=1)
    book(build_client(repo), 6, 1)
    after_start = build_client(repo, now=EVENT_START + timedelta(days=1))
    bad_body_missing_event = build_client(repo).post(
        "/api/v1/events/99/registrations", json={"participantId": "x"}
    )

    assert error_code(bad_body_missing_event) == "VALIDATION_ERROR"
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
