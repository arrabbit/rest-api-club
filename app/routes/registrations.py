"""Provide registration routes using an injected database repository.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from flask import Blueprint, jsonify

from app.errors import ApiError


def create_registration_blueprint(repository):
    """Build registration routes with a real or test repository.

    Args:
        repository: Object with get_event and list_registrations_with_names.

    Returns:
        Blueprint: Routes ready to register with a Flask application.
    """
    registrations_blueprint = Blueprint("registrations", __name__, url_prefix="/api/v1")

    @registrations_blueprint.get("/events/<int:event_id>/registrations")
    def list_registrations(event_id: int):
        """List an existing event's registrations, including participant names.

        Args:
            event_id: Event identifier supplied in the request path.

        Returns:
            tuple: JSON registration list and HTTP status 200.

        Raises:
            ApiError: If the event ID is nonpositive or the event is absent.
        """
        if event_id < 1 or repository.get_event(event_id) is None:
            raise ApiError(
                404,
                "EVENT_NOT_FOUND",
                f"Event {event_id} does not exist.",
                {"eventId": event_id},
            )

        registrations = repository.list_registrations_with_names(event_id)
        return jsonify({"data": registrations}), 200

    return registrations_blueprint
