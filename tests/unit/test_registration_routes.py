"""Test registration HTTP behavior without MySQL or external services.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from flask import Flask

from app.errors import register_error_handlers
from app.routes.registrations import (
    create_registration_blueprint,
    get_registration_rejection,
    has_available_capacity,
    has_event_started,
    to_utc_datetime,
    utc_now,
)

pytestmark = pytest.mark.unit

# Fixed "now" for booking tests, so results never depend on the real date.
FIXED_NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
FUTURE_START = "2026-12-01T18:00:00Z"


class FakeRegistrationRepository:
    """In-memory stand-in for app/repository.py, using the agreed signatures.

    Unlike a Mock, it remembers writes, so tests can book, cancel and rebook
    and then check what a later request sees. No MySQL is involved.
    """

    def __init__(self):
        """Seed three participants and no events; return None."""
        self.events = {}
        self.participants = {
            1: {"id": 1, "name": "Maya Okafor", "email": "maya@example.com"},
            2: {"id": 2, "name": "Alex Chen", "email": "alex@example.com"},
            3: {"id": 3, "name": "Sam Rivera", "email": "sam@example.com"},
        }
        self.registrations = {}
        self.next_registration_id = 1

    def add_event(self, event_id, capacity=2, start_time=FUTURE_START):
        """Store an event with the given id, capacity and start_time; return None."""
        self.events[event_id] = {
            "id": event_id,
            "title": f"Event {event_id}",
            "location": "Room 101",
            "startTime": start_time,
            "capacity": capacity,
        }

    def get_event(self, event_id):
        """Return the event dict for event_id, or None."""
        return self.events.get(event_id)

    def get_participant(self, participant_id):
        """Return the participant dict for participant_id, or None."""
        return self.participants.get(participant_id)

    def find_registration(self, event_id, participant_id):
        """Return the event_id/participant_id registration, or None."""
        for registration in self.registrations.values():
            if (registration["eventId"], registration["participantId"]) == (
                event_id,
                participant_id,
            ):
                return registration
        return None

    def count_registrations(self, event_id):
        """Return how many registrations event_id currently has."""
        return len(self._rows_for(event_id))

    def create_registration(self, event_id, participant_id):
        """Insert a registration for event_id/participant_id and return it."""
        registration = {
            "id": self.next_registration_id,
            "eventId": event_id,
            "participantId": participant_id,
            "participantName": self.participants[participant_id]["name"],
            "registeredAt": "2026-11-01T12:00:00Z",
        }
        self.registrations[registration["id"]] = registration
        self.next_registration_id += 1
        return dict(registration)

    def delete_registration(self, event_id, registration_id):
        """Delete registration_id only if it belongs to event_id; return bool."""
        registration = self.registrations.get(registration_id)
        if registration is None or registration["eventId"] != event_id:
            return False
        del self.registrations[registration_id]
        return True

    def list_registrations_with_names(self, event_id):
        """Return copies of event_id's registrations, including names."""
        return [dict(row) for row in self._rows_for(event_id)]

    def _rows_for(self, event_id):
        """Return the stored registration rows for event_id."""
        return [
            row for row in self.registrations.values() if row["eventId"] == event_id
        ]


def build_client(repository, clock=lambda: FIXED_NOW):
    """Create a test client around repository with a controllable clock.

    Args:
        repository: Mock or fake repository injected into the blueprint.
        clock: Zero-argument function returning the "current" UTC datetime.

    Returns:
        FlaskClient: In-process client; does not start an HTTP server.
    """
    test_app = Flask(__name__)
    test_app.config.update(TESTING=True)
    register_error_handlers(test_app)
    test_app.register_blueprint(create_registration_blueprint(repository, clock))
    return test_app.test_client()


@pytest.fixture
def fake_repository():
    """Return a fake repository with event 4 (capacity 2, starts in the future)."""
    repository = FakeRegistrationRepository()
    repository.add_event(4)
    return repository


@pytest.fixture
def fake_client(fake_repository):
    """Return a test client wired to fake_repository and FIXED_NOW."""
    return build_client(fake_repository)


def book(client, event_id, participant_id):
    """POST a booking for participant_id to event_id; return the response."""
    return client.post(
        f"/api/v1/events/{event_id}/registrations",
        json={"participantId": participant_id},
    )


@pytest.fixture
def repository():
    """Return a mock repository with only the methods used by listing.

    Args:
        None.

    Returns:
        Mock: Controlled repository responses; no database connections.
    """
    registration_repository = Mock(spec=["get_event", "list_registrations_with_names"])
    registration_repository.get_event.return_value = {"id": 4}
    registration_repository.list_registrations_with_names.return_value = []
    return registration_repository


@pytest.fixture
def client(repository):
    """Create an isolated HTTP client with real routes and error handlers.

    Args:
        repository: Mock database dependency injected into the blueprint.

    Returns:
        FlaskClient: In-process client; does not start an HTTP server.
    """
    return build_client(repository)


def test_list_registrations_includes_participant_names(client, repository):
    """Check populated responses using client and repository fixtures; return None."""
    expected_registration = {
        "id": 7,
        "eventId": 4,
        "participantId": 3,
        "participantName": "Maya Okafor",
        "registeredAt": "2026-10-14T18:00:00Z",
    }
    repository.list_registrations_with_names.return_value = [expected_registration]

    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 200
    assert response.is_json
    assert response.get_json() == {"data": [expected_registration]}
    repository.get_event.assert_called_once_with(4)
    repository.list_registrations_with_names.assert_called_once_with(4)


def test_list_registrations_returns_empty_list(client, repository):
    """Check an empty event using client and repository fixtures; return None."""
    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 200
    assert response.get_json() == {"data": []}
    repository.list_registrations_with_names.assert_called_once_with(4)


def test_list_registrations_rejects_missing_event(client, repository):
    """Check missing-event errors with client/repository fixtures; return None."""
    repository.get_event.return_value = None

    response = client.get("/api/v1/events/99/registrations")

    assert response.status_code == 404
    assert response.get_json() == {
        "error": {
            "code": "EVENT_NOT_FOUND",
            "message": "Event 99 does not exist.",
            "details": {"eventId": 99},
        }
    }
    repository.get_event.assert_called_once_with(99)
    repository.list_registrations_with_names.assert_not_called()


@pytest.mark.parametrize("event_id", ["0", "-1", "abc", "1.5"])
def test_list_registrations_rejects_invalid_event_id(client, repository, event_id):
    """Check invalid path event_id with client/repository fixtures; return None."""
    response = client.get(f"/api/v1/events/{event_id}/registrations")

    assert response.status_code == 404
    assert response.is_json
    assert "error" in response.get_json()
    repository.get_event.assert_not_called()
    repository.list_registrations_with_names.assert_not_called()


def test_list_registrations_keeps_events_separate(client, repository):
    """Check sequential event requests with client/repository fixtures; return None."""
    first_registration = {"id": 7, "eventId": 4, "participantName": "Maya Okafor"}
    second_registration = {"id": 8, "eventId": 5, "participantName": "Alex Chen"}
    repository.get_event.side_effect = [{"id": 4}, {"id": 5}]
    repository.list_registrations_with_names.side_effect = [
        [first_registration],
        [second_registration],
    ]

    first_response = client.get("/api/v1/events/4/registrations")
    second_response = client.get("/api/v1/events/5/registrations")

    assert first_response.status_code == second_response.status_code == 200
    assert first_response.get_json() == {"data": [first_registration]}
    assert second_response.get_json() == {"data": [second_registration]}
    assert [call.args for call in repository.get_event.call_args_list] == [(4,), (5,)]
    assert [
        call.args for call in repository.list_registrations_with_names.call_args_list
    ] == [(4,), (5,)]


def test_list_registrations_hides_repository_errors(client, repository):
    """Check safe failure responses with client/repository fixtures; return None."""
    repository.list_registrations_with_names.side_effect = RuntimeError(
        "SELECT private_column FROM internal_table"
    )

    response = client.get("/api/v1/events/4/registrations")

    assert response.status_code == 500
    assert response.get_json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An unexpected error occurred.",
        }
    }
    assert "private_column" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "event_exists, participant_exists, already_registered, expected_rejection",
    [
        (True, True, False, None),
        (False, True, False, "missing_event"),
        (True, False, False, "missing_participant"),
        (True, True, True, "duplicate_registration"),
        (False, False, False, "missing_event"),
        (False, True, True, "missing_event"),
        (True, False, True, "missing_participant"),
    ],
)
def test_registration_rejection_checks_existence_and_duplicates(
    event_exists, participant_exists, already_registered, expected_rejection
):
    """Check supplied existence/duplicate flags against expected_rejection; return None."""
    rejection = get_registration_rejection(
        event_exists=event_exists,
        participant_exists=participant_exists,
        already_registered=already_registered,
    )

    assert rejection == expected_rejection


@pytest.mark.parametrize(
    "capacity, registration_count, expected_available",
    [
        (1, 0, True),
        (1, 1, False),
        (2, 0, True),
        (2, 1, True),
        (2, 2, False),
        (2, 3, False),
        (10, 9, True),
        (10, 10, False),
    ],
)
def test_available_capacity_checks_last_place_and_full_event(
    capacity, registration_count, expected_available
):
    """Check supplied capacity/count against expected_available; return None."""
    assert (
        has_available_capacity(capacity=capacity, registration_count=registration_count)
        is expected_available
    )


@pytest.mark.parametrize(
    "time_offset, expected_started",
    [
        (timedelta(days=-1), False),
        (timedelta(microseconds=-1), False),
        (timedelta(microseconds=1), True),
        (timedelta(days=1), True),
    ],
)
def test_event_start_checks_before_and_after_boundary(time_offset, expected_started):
    """Check a supplied offset from start against expected_started; return None."""
    event_start_time = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)
    current_time = event_start_time + time_offset

    assert (
        has_event_started(event_start_time=event_start_time, current_time=current_time)
        is expected_started
    )


def test_event_start_rejects_exact_start_under_proposed_policy():
    """Check the provisional exact-start policy with no inputs; return None."""
    event_start_time = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)

    assert has_event_started(
        event_start_time=event_start_time, current_time=event_start_time
    )


@pytest.mark.parametrize("offset_hours", [-7, 0, 5.5])
def test_event_start_compares_instants_across_timezones(offset_hours):
    """Check the same instant in supplied UTC offsets; return None."""
    event_start_time = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)
    current_timezone = timezone(timedelta(hours=offset_hours))
    just_before_start = (event_start_time - timedelta(seconds=1)).astimezone(
        current_timezone
    )
    just_after_start = (event_start_time + timedelta(seconds=1)).astimezone(
        current_timezone
    )

    assert not has_event_started(
        event_start_time=event_start_time, current_time=just_before_start
    )
    assert has_event_started(
        event_start_time=event_start_time, current_time=just_after_start
    )


@pytest.mark.parametrize(
    "naive_start, naive_current", [(True, False), (False, True), (True, True)]
)
def test_event_start_rejects_datetimes_without_timezone(naive_start, naive_current):
    """Remove timezone per supplied flags and check rejection; return None."""
    event_start_time = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)
    current_time = event_start_time - timedelta(seconds=1)
    if naive_start:
        event_start_time = event_start_time.replace(tzinfo=None)
    if naive_current:
        current_time = current_time.replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        has_event_started(event_start_time=event_start_time, current_time=current_time)


@pytest.mark.parametrize(
    "value",
    [
        "2026-12-01T18:00:00Z",
        "2026-12-01T18:00:00+00:00",
        "2026-12-01T11:00:00-07:00",
        datetime(2026, 12, 1, 18, 0),
        datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc),
        datetime(2026, 12, 1, 23, 30, tzinfo=timezone(timedelta(hours=5.5))),
    ],
)
def test_to_utc_datetime_accepts_repository_time_formats(value):
    """Convert each supplied string/datetime form of one instant to UTC; return None."""
    converted = to_utc_datetime(value)

    assert converted == datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)
    assert converted.utcoffset() == timedelta(0)


@pytest.mark.parametrize(
    "value, expected_error",
    [
        ("2026-12-01T18:00:00", ValueError),
        ("not a date", ValueError),
        ("", ValueError),
        (1764612000, TypeError),
        (None, TypeError),
    ],
)
def test_to_utc_datetime_rejects_ambiguous_or_invalid_values(value, expected_error):
    """Check that a supplied invalid value raises expected_error; return None."""
    with pytest.raises(expected_error):
        to_utc_datetime(value)


def test_register_creates_registration(fake_client, fake_repository):
    """Book a free place and check the 201 body and stored row; return None."""
    response = book(fake_client, 4, 1)

    assert response.status_code == 201
    assert response.get_json() == {
        "id": 1,
        "eventId": 4,
        "participantId": 1,
        "participantName": "Maya Okafor",
        "registeredAt": "2026-11-01T12:00:00Z",
    }
    assert fake_repository.count_registrations(4) == 1


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"participantId": None},
        {"participantId": "1"},
        {"participantId": 1.5},
        {"participantId": 1.0},
        {"participantId": True},
        {"participantId": 0},
        {"participantId": -1},
        {"participantId": 1, "registeredAt": "2026-01-01T00:00:00Z"},
        [1],
        "1",
        1,
        None,
    ],
)
def test_register_rejects_invalid_body(fake_client, fake_repository, body):
    """Send a supplied invalid JSON body; expect 400 and no new row; return None."""
    # json.dumps so that None is sent as the literal `null`, not as "no body".
    response = fake_client.post(
        "/api/v1/events/4/registrations",
        data=json.dumps(body),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"
    assert fake_repository.count_registrations(4) == 0


def test_register_rejects_malformed_json(fake_client, fake_repository):
    """Send broken JSON text; expect the shared 400 JSON error; return None."""
    response = fake_client.post(
        "/api/v1/events/4/registrations",
        data='{"participantId": ',
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"
    assert fake_repository.count_registrations(4) == 0


def test_register_rejects_non_json_content_type(fake_client, fake_repository):
    """Send form data instead of JSON; expect 415 JSON error; return None."""
    response = fake_client.post(
        "/api/v1/events/4/registrations", data={"participantId": "1"}
    )

    assert response.status_code == 415
    assert response.get_json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert fake_repository.count_registrations(4) == 0


@pytest.mark.parametrize(
    "event_id, participant_id, expected_code",
    [
        (99, 1, "EVENT_NOT_FOUND"),
        (4, 99, "PARTICIPANT_NOT_FOUND"),
        (99, 99, "EVENT_NOT_FOUND"),
    ],
)
def test_register_rejects_missing_records(
    fake_client, fake_repository, event_id, participant_id, expected_code
):
    """Book with a supplied missing event/participant; expect 404; return None."""
    response = book(fake_client, event_id, participant_id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == expected_code
    assert fake_repository.registrations == {}


@pytest.mark.parametrize("event_id", ["0", "-1", "abc"])
def test_register_rejects_invalid_event_path(fake_client, event_id):
    """POST to a supplied invalid event path ID; expect 404 JSON; return None."""
    response = fake_client.post(
        f"/api/v1/events/{event_id}/registrations", json={"participantId": 1}
    )

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_register_rejects_duplicate(fake_client, fake_repository):
    """Book the same participant twice; expect 409 and one row; return None."""
    book(fake_client, 4, 1)

    response = book(fake_client, 4, 1)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "DUPLICATE_REGISTRATION"
    assert fake_repository.count_registrations(4) == 1


def test_register_rejects_full_event(fake_client, fake_repository):
    """Fill a capacity-2 event, then book a third; expect 409; return None."""
    book(fake_client, 4, 1)
    book(fake_client, 4, 2)

    response = book(fake_client, 4, 3)

    assert response.status_code == 409
    assert response.get_json() == {
        "error": {
            "code": "EVENT_FULL",
            "message": "Event 4 has no spots left.",
            "details": {"eventId": 4, "capacity": 2},
        }
    }
    assert fake_repository.count_registrations(4) == 2


@pytest.mark.parametrize(
    "now_offset, expected_status",
    [
        (timedelta(seconds=-1), 201),
        (timedelta(0), 409),
        (timedelta(seconds=1), 409),
    ],
)
def test_register_checks_start_time_boundary(
    fake_repository, now_offset, expected_status
):
    """Book at a supplied offset from start; check open/closed status; return None."""
    start = datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc)
    client = build_client(fake_repository, clock=lambda: start + now_offset)

    response = book(client, 4, 1)

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.get_json()["error"]["code"] == "EVENT_STARTED"


def test_register_accepts_naive_mysql_start_time(fake_repository):
    """Store a naive datetime start (as MySQL returns it); booking works; return None."""
    fake_repository.add_event(5, start_time=datetime(2026, 12, 1, 18, 0))
    client = build_client(fake_repository)

    assert book(client, 5, 1).status_code == 201


@pytest.mark.parametrize(
    "setup, expected_code",
    [
        ("duplicate_and_full", "DUPLICATE_REGISTRATION"),
        ("started_and_full", "EVENT_STARTED"),
    ],
)
def test_register_reports_rules_in_agreed_order(fake_repository, setup, expected_code):
    """Break two rules at once per setup; expect the earlier rule's code; return None."""
    fake_repository.add_event(6, capacity=1)
    book(build_client(fake_repository), 6, 1)
    clock = lambda: FIXED_NOW  # noqa: E731
    if setup == "started_and_full":
        clock = lambda: datetime(2027, 1, 1, tzinfo=timezone.utc)  # noqa: E731
    participant_id = 1 if setup == "duplicate_and_full" else 2

    response = book(build_client(fake_repository, clock), 6, participant_id)

    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == expected_code


def cancel(client, event_id, registration_id):
    """DELETE registration_id under event_id; return the response."""
    return client.delete(f"/api/v1/events/{event_id}/registrations/{registration_id}")


def test_cancel_removes_registration(fake_client, fake_repository):
    """Cancel an existing booking; expect 204, empty body, row gone; return None."""
    registration_id = book(fake_client, 4, 1).get_json()["id"]

    response = cancel(fake_client, 4, registration_id)

    assert response.status_code == 204
    assert response.get_data() == b""
    assert fake_repository.count_registrations(4) == 0


def test_cancel_twice_does_not_release_extra_place(fake_client, fake_repository):
    """Cancel the same booking twice; second gets 404, count unchanged; return None."""
    first_id = book(fake_client, 4, 1).get_json()["id"]
    book(fake_client, 4, 2)
    cancel(fake_client, 4, first_id)

    response = cancel(fake_client, 4, first_id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "REGISTRATION_NOT_FOUND"
    assert fake_repository.count_registrations(4) == 1


def test_cancel_rejects_registration_from_other_event(fake_client, fake_repository):
    """Cancel event 5's booking via event 4; expect 404, row kept; return None."""
    fake_repository.add_event(5)
    other_id = book(fake_client, 5, 1).get_json()["id"]

    response = cancel(fake_client, 4, other_id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "REGISTRATION_NOT_FOUND"
    assert fake_repository.count_registrations(5) == 1


def test_cancel_rejects_missing_event(fake_client, fake_repository):
    """Cancel under a missing event; expect 404 EVENT_NOT_FOUND; return None."""
    registration_id = book(fake_client, 4, 1).get_json()["id"]

    response = cancel(fake_client, 99, registration_id)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "EVENT_NOT_FOUND"
    assert fake_repository.count_registrations(4) == 1


@pytest.mark.parametrize("registration_id", ["0", "-1", "abc", "999"])
def test_cancel_rejects_invalid_or_unknown_registration(fake_client, registration_id):
    """Cancel a supplied invalid/unknown registration ID; expect 404; return None."""
    response = fake_client.delete(f"/api/v1/events/4/registrations/{registration_id}")

    assert response.status_code == 404
    assert "error" in response.get_json()


def test_cancel_allowed_after_event_starts(fake_repository):
    """Book before start, cancel after start; expect 204 (team assumption)."""
    registration_id = book(build_client(fake_repository), 4, 1).get_json()["id"]
    after_start = build_client(
        fake_repository, clock=lambda: datetime(2027, 1, 1, tzinfo=timezone.utc)
    )

    assert cancel(after_start, 4, registration_id).status_code == 204


def test_capacity_two_walkthrough(fake_client):
    """Spec example: two book, third rejected, one cancels, third books; return None."""
    first = book(fake_client, 4, 1)
    second = book(fake_client, 4, 2)
    rejected = book(fake_client, 4, 3)
    cancelled = cancel(fake_client, 4, first.get_json()["id"])
    third = book(fake_client, 4, 3)
    listing = fake_client.get("/api/v1/events/4/registrations").get_json()["data"]

    assert [first.status_code, second.status_code] == [201, 201]
    assert rejected.status_code == 409
    assert rejected.get_json()["error"]["code"] == "EVENT_FULL"
    assert cancelled.status_code == 204
    assert third.status_code == 201
    assert sorted(row["participantName"] for row in listing) == [
        "Alex Chen",
        "Sam Rivera",
    ]


def test_rebook_after_cancel_creates_new_registration(fake_client, fake_repository):
    """Book, cancel and book again as one participant; expect a new row; return None."""
    first_id = book(fake_client, 4, 1).get_json()["id"]
    cancel(fake_client, 4, first_id)

    rebooked = book(fake_client, 4, 1)

    assert rebooked.status_code == 201
    assert rebooked.get_json()["id"] != first_id
    assert fake_repository.count_registrations(4) == 1


def test_utc_now_returns_current_aware_utc_time():
    """Check the production clock is timezone-aware UTC and current; return None."""
    before = datetime.now(timezone.utc)
    now = utc_now()

    assert now.utcoffset() == timedelta(0)
    assert before <= now <= datetime.now(timezone.utc)
