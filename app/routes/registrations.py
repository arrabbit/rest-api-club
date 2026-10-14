"""Registration routes: list, book and cancel registrations for an event.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.errors import ApiError


def parse_participant_id(body) -> int:
    """Return the participant ID from a booking body.

    Args:
        body: Decoded JSON body; must be exactly {"participantId": <int >= 1>}.

    Returns:
        int: The participant ID.

    Raises:
        ApiError: 400 naming the problem: not an object, unknown fields
            (listed in details), or a missing/invalid participantId.
    """
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object.")
    unknown_fields = sorted(set(body) - {"participantId"})
    if unknown_fields:
        raise ApiError(
            400,
            "BAD_REQUEST",
            "Request body has unknown fields.",
            {"fields": unknown_fields},
        )
    participant_id = body.get("participantId")
    # type() is used rather than isinstance() so that True/False are rejected.
    if type(participant_id) is not int or participant_id < 1:
        raise ApiError(
            400,
            "BAD_REQUEST",
            "participantId is required and must be a positive integer.",
            {"fields": ["participantId"]},
        )
    return participant_id


def require_event(repository, event_id: int) -> dict:
    """Return the event, or raise the standard 404.

    Args:
        repository: Object providing get_event.
        event_id: Event ID from the request path.

    Returns:
        dict: The stored event.

    Raises:
        ApiError: 404 EVENT_NOT_FOUND if the event does not exist.
    """
    event = repository.get_event(event_id)
    if event is None:
        raise ApiError(
            404,
            "EVENT_NOT_FOUND",
            f"Event {event_id} does not exist.",
            {"eventId": event_id},
        )
    return event


def check_registration_allowed(repository, event_id, participant_id, now):
    """Apply the booking rules in order, raising on the first one that fails.

    Args:
        repository: Object providing the agreed repository functions.
        event_id: Event ID from the request path.
        participant_id: Validated participant ID.
        now: Current time as a timezone-aware datetime.

    Returns:
        None.

    Raises:
        ApiError: 404 missing event/participant; 409 duplicate, started or full.
    """
    event = require_event(repository, event_id)
    details = {"eventId": event_id, "participantId": participant_id}
    if repository.get_participant(participant_id) is None:
        raise ApiError(
            404,
            "PARTICIPANT_NOT_FOUND",
            f"Participant {participant_id} does not exist.",
            details,
        )
    if repository.find_registration(event_id, participant_id) is not None:
        raise ApiError(
            409,
            "DUPLICATE_REGISTRATION",
            f"Participant {participant_id} is already registered for event {event_id}.",
            details,
        )

    start_time = event["startTime"]
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if start_time.tzinfo is None:
        # MySQL DATETIME comes back without a timezone; the connection uses UTC.
        start_time = start_time.replace(tzinfo=timezone.utc)
    # Team decision: registration closes exactly at the start time.
    if now >= start_time:
        raise ApiError(
            409, "EVENT_STARTED", f"Event {event_id} has already started.", details
        )

    if repository.count_registrations(event_id) >= event["capacity"]:
        raise ApiError(
            409,
            "EVENT_FULL",
            f"Event {event_id} has no spots left.",
            {"eventId": event_id, "capacity": event["capacity"]},
        )


def create_registration_blueprint(repository, clock=lambda: datetime.now(timezone.utc)):
    """Build the registration routes around a repository and a clock.

    Args:
        repository: Object exposing the agreed repository functions.
        clock: Function returning the current UTC time; tests pass a fixed one.

    Returns:
        Blueprint: Routes ready to register with a Flask application.
    """
    blueprint = Blueprint("registrations", __name__, url_prefix="/api/v1")

    @blueprint.get("/events/<int:event_id>/registrations")
    def list_registrations(event_id: int):
        """List an event's registrations, including participant names.

        Args:
            event_id: Event ID from the request path.

        Returns:
            Response: JSON {"data": [...]} with status 200.

        Raises:
            ApiError: 404 EVENT_NOT_FOUND if the event does not exist.
        """
        require_event(repository, event_id)
        return jsonify({"data": repository.list_registrations_with_names(event_id)})

    @blueprint.post("/events/<int:event_id>/registrations")
    def register_participant(event_id: int):
        """Register the participant named in the JSON body for an event.

        Args:
            event_id: Event ID from the request path.

        Returns:
            tuple: JSON registration and status 201.

        Raises:
            ApiError: 400 bad body; 404 missing event or participant;
                409 duplicate, started or full event.
        """
        # get_json() raises 415 (not JSON) or 400 (malformed); errors.py formats both.
        participant_id = parse_participant_id(request.get_json())
        check_registration_allowed(repository, event_id, participant_id, clock())
        return jsonify(repository.create_registration(event_id, participant_id)), 201

    @blueprint.delete("/events/<int:event_id>/registrations/<int:registration_id>")
    def cancel_registration(event_id: int, registration_id: int):
        """Cancel a registration by deleting its row, which frees one place.

        Args:
            event_id: Event ID from the request path.
            registration_id: Registration ID from the request path.

        Returns:
            tuple: Empty body and status 204.

        Raises:
            ApiError: 404 if the event is missing, or the registration is
                missing, already cancelled or belongs to another event.
        """
        require_event(repository, event_id)
        # Deleting the row (no stored counter) means a repeated cancel finds
        # nothing and cannot free a second place. Cancelling after start is allowed.
        if not repository.delete_registration(event_id, registration_id):
            raise ApiError(
                404,
                "REGISTRATION_NOT_FOUND",
                f"Registration {registration_id} does not exist for event {event_id}.",
                {"eventId": event_id, "registrationId": registration_id},
            )
        return "", 204

    return blueprint
