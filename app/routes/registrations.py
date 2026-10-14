"""Provide registration routes and independently testable booking rules.

Author: Joseph (JD-d3v)
Date: 2026-10-14
"""

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

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


def to_utc_datetime(value: datetime | str) -> datetime:
    """Convert a repository start time into a timezone-aware UTC datetime.

    Args:
        value: ISO 8601 string with a timezone (e.g. "2026-11-14T18:00:00Z"),
            or a datetime. A naive datetime is treated as UTC because the
            MySQL connection is configured with time_zone "+00:00".

    Returns:
        datetime: The same instant, expressed in UTC.

    Raises:
        ValueError: If a string is not ISO 8601 or has no timezone.
        TypeError: If value is neither a string nor a datetime.
    """
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() is None:
            raise ValueError(f"Timestamp {value!r} has no timezone.")
        return parsed.astimezone(timezone.utc)
    if isinstance(value, datetime):
        # MySQL DATETIME columns come back naive; the connection stores UTC.
        if value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    raise TypeError(f"Expected a datetime or ISO string, got {type(value).__name__}.")


# Maps internal rejection reasons to (status, public error code).
REJECTION_ERRORS = {
    "missing_event": (404, "EVENT_NOT_FOUND"),
    "missing_participant": (404, "PARTICIPANT_NOT_FOUND"),
    "duplicate_registration": (409, "DUPLICATE_REGISTRATION"),
}


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Args:
        None.

    Returns:
        datetime: Current UTC time; the default clock for the routes.
    """
    return datetime.now(timezone.utc)


def parse_participant_id(body) -> int:
    """Validate a booking body and return its participant ID.

    Args:
        body: Decoded JSON request body; must be exactly {"participantId": n}.

    Returns:
        int: Positive participant ID.

    Raises:
        ApiError: 400 if the body is not an object, has missing or unknown
            fields, or participantId is not a positive integer.
    """
    if not isinstance(body, dict):
        raise ApiError(400, "BAD_REQUEST", "Request body must be a JSON object.")
    unknown_fields = sorted(set(body) - {"participantId"})
    if unknown_fields:
        raise ApiError(
            400,
            "BAD_REQUEST",
            "Unknown fields in request body.",
            {"fields": unknown_fields},
        )
    participant_id = body.get("participantId")
    # bool is a subclass of int in Python, so True would otherwise pass as 1.
    if (
        isinstance(participant_id, bool)
        or not isinstance(participant_id, int)
        or participant_id < 1
    ):
        raise ApiError(
            400,
            "BAD_REQUEST",
            "participantId must be a positive integer.",
            {"field": "participantId"},
        )
    return participant_id


def require_event(repository, event_id: int) -> dict:
    """Load an event or raise the standard 404.

    Args:
        repository: Object providing get_event.
        event_id: Event identifier from the request path.

    Returns:
        dict: The stored event.

    Raises:
        ApiError: 404 EVENT_NOT_FOUND if event_id is nonpositive or absent.
    """
    event = repository.get_event(event_id) if event_id >= 1 else None
    if event is None:
        raise ApiError(
            404,
            "EVENT_NOT_FOUND",
            f"Event {event_id} does not exist.",
            {"eventId": event_id},
        )
    return event


def build_rejection_error(reason: str, event_id: int, participant_id: int) -> ApiError:
    """Translate an internal rejection reason into a public ApiError.

    Args:
        reason: Value returned by get_registration_rejection.
        event_id: Requested event.
        participant_id: Requested participant.

    Returns:
        ApiError: Error ready to raise, with the agreed status and code.
    """
    status, code = REJECTION_ERRORS[reason]
    messages = {
        "missing_event": f"Event {event_id} does not exist.",
        "missing_participant": f"Participant {participant_id} does not exist.",
        "duplicate_registration": (
            f"Participant {participant_id} is already registered for event {event_id}."
        ),
    }
    details = {"eventId": event_id, "participantId": participant_id}
    return ApiError(status, code, messages[reason], details)


def check_registration_allowed(repository, event_id, participant_id, current_time):
    """Apply every booking rule in the agreed order, raising on the first failure.

    Order: event exists, participant exists, not a duplicate, not started,
    not full. No rows are written here.

    Args:
        repository: Object providing the registration repository functions.
        event_id: Requested event (already known to be an int from the path).
        participant_id: Validated positive participant ID.
        current_time: Timezone-aware "now" used for the start-time rule.

    Returns:
        None.

    Raises:
        ApiError: 404 or 409 with the specific error code for the failed rule.
    """
    event = repository.get_event(event_id) if event_id >= 1 else None
    participant = repository.get_participant(participant_id)
    # Only look for a duplicate when both records exist; saves a pointless query.
    already_registered = (
        event is not None
        and participant is not None
        and repository.find_registration(event_id, participant_id) is not None
    )
    reason = get_registration_rejection(
        event_exists=event is not None,
        participant_exists=participant is not None,
        already_registered=already_registered,
    )
    if reason is not None:
        raise build_rejection_error(reason, event_id, participant_id)

    start_time = to_utc_datetime(event["startTime"])
    if has_event_started(event_start_time=start_time, current_time=current_time):
        raise ApiError(
            409,
            "EVENT_STARTED",
            f"Event {event_id} has already started.",
            {"eventId": event_id, "startTime": event["startTime"]},
        )

    registration_count = repository.count_registrations(event_id)
    if not has_available_capacity(
        capacity=event["capacity"], registration_count=registration_count
    ):
        raise ApiError(
            409,
            "EVENT_FULL",
            f"Event {event_id} has no spots left.",
            {"eventId": event_id, "capacity": event["capacity"]},
        )


def create_registration_blueprint(repository, clock=utc_now):
    """Build registration routes with a real or test repository.

    Args:
        repository: Object exposing the agreed repository functions.
        clock: Zero-argument function returning the current UTC datetime.
            Tests pass a fixed clock; production uses utc_now.

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
        require_event(repository, event_id)
        registrations = repository.list_registrations_with_names(event_id)
        return jsonify({"data": registrations}), 200

    @registrations_blueprint.post("/events/<int:event_id>/registrations")
    def register_participant(event_id: int):
        """Register one participant for an event after checking every rule.

        Args:
            event_id: Event identifier supplied in the request path.

        Returns:
            tuple: JSON registration and HTTP status 201.

        Raises:
            ApiError: 400 bad body, 404 missing event/participant,
                409 duplicate, started or full event.
        """
        # get_json() raises 415 for a non-JSON content type and 400 for bad JSON;
        # the shared handlers turn both into the standard error shape.
        participant_id = parse_participant_id(request.get_json())
        check_registration_allowed(repository, event_id, participant_id, clock())
        registration = repository.create_registration(event_id, participant_id)
        return jsonify(registration), 201

    return registrations_blueprint
