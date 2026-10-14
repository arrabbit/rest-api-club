"""Test registration HTTP behavior without MySQL or external services.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from unittest.mock import Mock

import pytest
from flask import Flask

from app.errors import register_error_handlers
from app.routes.registrations import create_registration_blueprint

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
