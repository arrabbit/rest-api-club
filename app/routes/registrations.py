"""Registration routes: list, book and cancel registrations for an event.

Follows docs/api-contract.md: repository rows use snake_case and naive-UTC
or aware datetimes; responses use camelCase and ISO 8601 UTC ending in "Z".

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from app.errors import ApiError


def as_utc(value: datetime) -> datetime:
    """Return a datetime as timezone-aware UTC.

    Args:
        value: Datetime from the repository; naive values are already UTC
            because the MySQL connection uses time_zone "+00:00".

    Returns:
        datetime: The same instant with tzinfo set to UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def registration_to_json(row: dict) -> dict:
    """Convert a repository registration row to its JSON representation.

    Args:
        row: Row with id, event_id, participant_id, participant_name, registered_at.

    Returns:
        dict: camelCase registration with registeredAt as "YYYY-MM-DDTHH:MM:SSZ".
    """
    return {
        "id": row["id"],
        "eventId": row["event_id"],
        "participantId": row["participant_id"],
        "participantName": row["participant_name"],
        "registeredAt": as_utc(row["registered_at"]).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def parse_path_id(raw: str, code: str, label: str) -> int:
    """Return a path ID as a positive integer, or raise the matching 404.

    Args:
        raw: ID text from the URL.
        code: Error code to use, e.g. "EVENT_NOT_FOUND".
        label: Resource name for the message, e.g. "Event".

    Returns:
        int: The parsed ID.

    Raises:
        ApiError: 404 with code if raw is not a positive integer.
    """
    # ASCII digits only, so "-1", "1.5", "abc" and "²" are all rejected.
    if raw.isascii() and raw.isdigit() and int(raw) >= 1:
        return int(raw)
    raise ApiError(404, code, f"{label} {raw} does not exist.")


def parse_participant_id(body) -> int:
    """Return the participant ID from a booking body.

    Args:
        body: Result of request.get_json(silent=True); None if missing or malformed.

    Returns:
        int: The participant ID.

    Raises:
        ApiError: 400 VALIDATION_ERROR listing every problem in details.errors.
    """
    if not isinstance(body, dict):
        errors = [{"field": "body", "reason": "must be a JSON object"}]
    else:
        errors = [
            {"field": field, "reason": "unknown field"}
            for field in sorted(set(body) - {"participantId"})
        ]
        participant_id = body.get("participantId")
        # type() rather than isinstance() so that True/False are rejected.
        if type(participant_id) is not int or participant_id < 1:
            errors.append(
                {"field": "participantId", "reason": "must be a positive integer"}
            )
    if errors:
        raise ApiError(
            400, "VALIDATION_ERROR", "Request body is invalid.", {"errors": errors}
        )
    return body["participantId"]


def require_event(repository, raw_event_id: str) -> tuple[int, dict]:
    """Return the event ID and row, or raise the standard 404.

    Args:
        repository: Object providing get_event.
        raw_event_id: Event ID text from the URL.

    Returns:
        tuple: (event ID, event row).

    Raises:
        ApiError: 404 EVENT_NOT_FOUND if the ID is invalid or the event is absent.
    """
    event_id = parse_path_id(raw_event_id, "EVENT_NOT_FOUND", "Event")
    event = repository.get_event(event_id)
    if event is None:
        raise ApiError(
            404,
            "EVENT_NOT_FOUND",
            f"Event {event_id} does not exist.",
            {"eventId": event_id},
        )
    return event_id, event


def check_registration_allowed(repository, event_id, event, participant_id, now):
    """Apply the booking rules in order and return the participant.

    Args:
        repository: Object providing the agreed repository functions.
        event_id: Existing event's ID.
        event: Existing event's row (start_time, capacity).
        participant_id: Validated participant ID.
        now: Current time as a timezone-aware datetime.

    Returns:
        dict: The participant row.

    Raises:
        ApiError: 404 missing participant; 409 duplicate, started or full.
    """
    details = {"eventId": event_id, "participantId": participant_id}
    participant = repository.get_participant(participant_id)
    if participant is None:
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
    # Team decision: registration closes exactly at the start time.
    if now >= as_utc(event["start_time"]):
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
    return participant


def create_registration_blueprint(repository, clock=lambda: datetime.now(timezone.utc)):
    """Build the registration routes around a repository and a clock.

    Args:
        repository: Object exposing the agreed repository functions.
        clock: Function returning the current UTC time; tests pass a fixed one.

    Returns:
        Blueprint: Routes ready to register with a Flask application.
    """
    blueprint = Blueprint("registrations", __name__, url_prefix="/api/v1")

    @blueprint.get("/events/<event_id>/registrations")
    def list_registrations(event_id: str):
        """List an event's registrations, including participant names.

        Args:
            event_id: Event ID text from the request path.

        Returns:
            Response: JSON {"data": [...]} with status 200.

        Raises:
            ApiError: 404 EVENT_NOT_FOUND if the event does not exist.
        """
        event_id, _ = require_event(repository, event_id)
        rows = repository.list_registrations_with_names(event_id)
        return jsonify({"data": [registration_to_json(row) for row in rows]})

    @blueprint.post("/events/<event_id>/registrations")
    def register_participant(event_id: str):
        """Register the participant named in the JSON body for an event.

        Args:
            event_id: Event ID text from the request path.

        Returns:
            tuple: JSON registration, status 201 and a Location header.

        Raises:
            ApiError: 400 bad body; 404 missing event or participant;
                409 duplicate, started or full event.
        """
        # Contract order: 400 (body) before 404 (resources) before 409 (rules).
        participant_id = parse_participant_id(request.get_json(silent=True))
        event_id, event = require_event(repository, event_id)
        participant = check_registration_allowed(
            repository, event_id, event, participant_id, clock()
        )
        row = repository.create_registration(event_id, participant_id)
        # The name comes from the participant already loaded, in case the
        # repository's insert result does not include it.
        registration = registration_to_json(
            {"participant_name": participant["name"], **row}
        )
        location = f"/api/v1/events/{event_id}/registrations/{registration['id']}"
        return jsonify(registration), 201, {"Location": location}

    @blueprint.delete("/events/<event_id>/registrations/<registration_id>")
    def cancel_registration(event_id: str, registration_id: str):
        """Cancel a registration by deleting its row, which frees one place.

        Args:
            event_id: Event ID text from the request path.
            registration_id: Registration ID text from the request path.

        Returns:
            tuple: Empty body and status 204.

        Raises:
            ApiError: 404 if the event is missing, or the registration is
                missing, already cancelled or belongs to another event.
        """
        event_id, _ = require_event(repository, event_id)
        registration_id = parse_path_id(
            registration_id, "REGISTRATION_NOT_FOUND", "Registration"
        )
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
