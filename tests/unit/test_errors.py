"""
test_errors.py
Purpose: Unit tests for app/errors.py. Checks that every error path
         (ApiError, unknown route, wrong method, malformed JSON,
         IntegrityError, unexpected crash) returns the same JSON shape
         and never leaks internals. No database needed.
Authors: Anna Running Rabbit
Date Created:      2026-10-13
Date Last Editted: 2026-10-13
"""

import mysql.connector
import pytest
from flask import Flask, request
from app.errors import ApiError, register_error_handlers

pytestmark = pytest.mark.unit

def build_test_app():
    """
    Build a tiny Flask app with routes that trigger each error type.

    Parameters:
        None

    Returns:
        Flask: App with error handlers registered
    """
    app = Flask(__name__)
    register_error_handlers(app)

    @app.get("/raise-api-error")
    def raise_api_error():
        raise ApiError(404, "EVENT_NOT_FOUND", "No event with id 99.",
                       {"eventId": 99})

    @app.post("/needs-json")
    def needs_json():
        return request.get_json()  # bad JSON makes Flask raise 400

    @app.get("/raise-integrity")
    def raise_integrity():
        raise mysql.connector.IntegrityError(
            msg="Duplicate entry '4-3' for key 'uq_event_participant'")

    @app.get("/crash")
    def crash():
        raise ZeroDivisionError("secret password=hunter2")

    return app


@pytest.fixture
def client():
    """
    Provide a Flask test client (same pattern as the Oct 1 activity).

    Parameters:
        None

    Returns:
        FlaskClient: In-process test client
    """
    app = build_test_app()
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
    with app.test_client() as test_client:
        yield test_client


def test_api_error_uses_standard_shape(client):
    response = client.get("/raise-api-error")
    assert response.status_code == 404
    assert response.get_json() == {"error": {
        "code": "EVENT_NOT_FOUND",
        "message": "No event with id 99.",
        "details": {"eventId": 99},
    }}


@pytest.mark.parametrize("method, path, status, code", [
    ("get", "/no-such-route", 404, "NOT_FOUND"),
    ("delete", "/raise-api-error", 405, "METHOD_NOT_ALLOWED"),
])
def test_builtin_errors_return_json_not_html(client, method, path, status,
                                             code):
    response = getattr(client, method)(path)
    assert response.status_code == status
    assert response.is_json
    assert response.get_json()["error"]["code"] == code


def test_malformed_json_returns_json_400(client):
    response = client.post("/needs-json", data="{bad",
                           content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "BAD_REQUEST"


def test_integrity_error_returns_409_without_sql(client):
    response = client.get("/raise-integrity")
    assert response.status_code == 409
    assert "Duplicate entry" not in response.get_data(as_text=True)


def test_unexpected_error_returns_generic_500(client):
    response = client.get("/crash")
    body = response.get_data(as_text=True)
    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in body
    assert "Traceback" not in body