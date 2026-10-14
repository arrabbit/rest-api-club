"""Provide registration routes and independently testable booking rules.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from datetime import datetime

from flask import Blueprint, jsonify

from app.errors import ApiError


def get_registration_rejection(
    *, event_exists: bool, participant_exists: bool, already_registered: bool
) -> str | None:
    """Check resource existence and duplicate registration without database access.

    Args:
        event_exists: Whether the requested event exists.
        participant_exists: Whether the requested participant exists.
        already_registered: Whether this participant is registered for this event.

    Returns:
        str | None: Internal rejection reason, or None when these checks pass.
            Time and capacity must still be checked before creating a booking.
    """
    if not event_exists:
        return "missing_event"
    if not participant_exists:
        return "missing_participant"
    if already_registered:
        return "duplicate_registration"
    return None


def has_available_capacity(*, capacity: int, registration_count: int) -> bool:
    """Check whether the current registration count leaves room for one person.

    Args:
        capacity: Validated positive integer maximum number of registrations.
        registration_count: Nonnegative integer count of current registrations.

    Returns:
        bool: True when another registration fits; False when full or overfull.
    """
    return registration_count < capacity


def has_event_started(*, event_start_time: datetime, current_time: datetime) -> bool:
    """Compare explicit instants without reading the clock or database.

    Args:
        event_start_time: Timezone-aware scheduled event start.
        current_time: Timezone-aware time at which to evaluate booking eligibility.

    Returns:
        bool: True at or after start, under the proposed exact-start policy.

    Raises:
        ValueError: If either datetime lacks timezone information.
    """
    if event_start_time.utcoffset() is None or current_time.utcoffset() is None:
        raise ValueError("Booking time comparisons require timezone-aware datetimes.")

    # Provisional team decision: registration closes exactly when the event starts.
    return current_time >= event_start_time


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
