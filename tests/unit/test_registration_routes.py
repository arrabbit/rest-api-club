"""Test registration HTTP behavior without MySQL or external services.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

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
)

pytestmark = pytest.mark.unit


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
    test_app = Flask(__name__)
    test_app.config.update(TESTING=True)
    register_error_handlers(test_app)
    test_app.register_blueprint(create_registration_blueprint(repository))
    return test_app.test_client()


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
