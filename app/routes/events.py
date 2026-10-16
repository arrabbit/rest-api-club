"""
events.py
Purpose: Event routes (create, list, get, update, delete) for the Campus
         Events API, plus helpers that shape event data for the contract.
Authors: Jordan Senko
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from app.errors import ApiError

def as_utc(value: datetime) -> datetime:
    """
    Return a datetime as timezone-aware UTC.

    Parameters:
        value (datetime): Datetime from the repository.

    Returns:
        datetime: The same instant with tzinfo set to UTC.
    """
    # A naive value is already UTC: app/config.py sets the MySQL session to "+00:00".
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def event_to_json(row: dict) -> dict:
    """
    Turn a repository row (snake_case) into the API event (camelCase).

    Parameters:
        row (dict): id, title, country, province, city, address, start_time,
            end_time, capacity, registered_count.

    Returns:
        dict: The event fields, with startTime and endTime as
            "YYYY-MM-DDTHH:MM:SSZ" and spotsLeft computed.
    """
    start_time = as_utc(row["start_time"])
    end_time = as_utc(row["end_time"])
    spots_left = row["capacity"] - row["registered_count"]

    return {
        "id": row["id"],
        "title": row["title"],
        "country": row["country"], # addition in place of location
        "province": row["province"], # addition in place of location
        "city": row["city"], # addition in place of location
        "address": row["address"], # addition in place of location
        "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": end_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "capacity": row["capacity"],
        "registeredCount": row["registered_count"],
        "spotsLeft": spots_left
    }

def load_event(repository, event_id: int) -> dict:
    """Return the event row, or raise 404 EVENT_NOT_FOUND."""
    event = repository.get_event(event_id)
    if event is None:
        raise ApiError(404, "EVENT_NOT_FOUND", f"No event with id {event_id}.", {"eventId": event_id})
    return event

def parse_event_id(raw: str) -> int:
    """
    Convert the {eventId} part of a URL into a positive integer.

    Parameters:
        raw (str): The text taken from the URL.

    Returns:
        int: The event id.

    Raises:
        ApiError: 404 EVENT_NOT_FOUND if raw is not a positive whole number.
    """
    if not raw.isdecimal():
        raise ApiError(404, "EVENT_NOT_FOUND", f"No event with id {raw}.", {"eventId": raw})
    event_id = int(raw)
    if event_id < 1:
        raise ApiError(404, "EVENT_NOT_FOUND", f"No event with id {raw}.", {"eventId": raw})
    return event_id

def read_json_body() -> dict:
    """Return the request body as a dict, or raise a 400 ApiError."""
    body = request.get_json(silent=True)

    if not isinstance(body, dict):
        raise ApiError(400, "VALIDATION_ERROR", "Request body must be a JSON object",
                       {"errors": [{"field": "body", "reason": "request body is not a JSON object."}]})
    return body

def check_time_order(row: dict, changes: dict) -> None:
    """Raise a 400 if the merged startTime/endTime would not be in order."""

    start = as_utc(changes.get("start_time", row["start_time"]))
    end = as_utc(changes.get("end_time", row["end_time"]))

    if end <= start:
        raise ApiError(400, "VALIDATION_ERROR", f"Invalid start and end times. Start time: {start}, End time: {end}",
                       {"errors": [{"field": "endTime",  "reason": "must be after startTime"}]})

def check_capacity(event_id: int, changes: dict, repository) -> None:
    """Raise a 409 if the new capacity is below the current registrations."""

    new_cap = changes.get("capacity")
    if new_cap is not None:
        registered = repository.count_registrations(event_id)

        if new_cap < registered:
            raise ApiError(409, "CAPACITY_BELOW_REGISTRATIONS", f"Too many registrants. Club capacity: {new_cap}, Attempted registrants: {registered}",
                           {"errors": [{"field": "capacity",  "reason": "num of registrants exceeds club capacity"}]})

def check_no_registrations(event_id: int, repository) -> None:
    """Raise a 409 if the event still has registrations."""

    registered = repository.count_registrations(event_id)
    if registered > 0:
        raise ApiError(409, "EVENT_HAS_REGISTRATIONS", f"This event has {registered} registrants and so cannot be deleted.",
                       {"eventId": event_id, "registeredCount": registered})

def create_event_blueprint(repository):
    """
    Build the event routes around a repository.

    Parameters:
        repository: Object with list_events() and get_event(event_id).

    Returns:
        Blueprint: Routes ready to register with a Flask application.
    """
    blueprint = Blueprint("events", __name__, url_prefix="/api/v1/events")

    @blueprint.get("")
    def list_events(): # list_events() is referred to as a "flask view"
        """
        List all events.

        Parameters:
            None

        Returns:
            Response: JSON {"data": [...]} with status 200.
        """
        rows = repository.list_events()
        data = []
        for row in rows:
            json_event = event_to_json(row)
            data.append(json_event)
        return jsonify({"data": data})

    @blueprint.get("/<event_id>")
    def get_event(event_id: str):
        """
        Return one event.

        Parameters:
            event_id (str): Event ID text from the request path.

        Returns:
            dict: The event as JSON, with status 200.

        Raises:
            ApiError: 404 EVENT_NOT_FOUND if the id is invalid or no event has it.
        """
        parsed_id = parse_event_id(event_id)
        return load_event(repository, parsed_id)

    @blueprint.post("")
    def create_event():
        """
        POST /api/v1/events creates an event.
        """
        body = read_json_body()
        fields = validate_event_create(body) # TEMP: returns a clean dict; Precious' function
        row = repository.create_event(fields["title"], fields["country"], fields["province"], fields["city"], 
                                fields["address"], fields["start_time"], fields["end_time"], fields["capacity"])
        row["registered_count"] = 0
        response = jsonify(event_to_json(row))
        response.status_code = 201
        response.headers["Location"] = f"/api/v1/events/{row['id']}"
        return response

    @blueprint.patch("/<event_id>")
    def update_event(event_id: str):
        """PATCH /api/v1/events/<event_id> updates some fields of an event."""
        parsed_id = parse_event_id(event_id)
        body = read_json_body()
        changes = validate_event_patch(body) # TEMP: Precious' function
        row = load_event(repository, parsed_id)

        check_time_order(row, changes)
        check_capacity(parsed_id, changes, repository)

        repository.update_event(parsed_id, changes)
        return load_event(repository, parsed_id)

    @blueprint.delete("/<event_id>")
    def delete_event(event_id: str):
        """DELETE /api/v1/events/<event_id> deletes an event with no registrations."""

        parsed_id = parse_event_id(event_id)
        load_event(repository, parsed_id)
        
        check_no_registrations(parsed_id, repository)
        repository.delete_event(parsed_id)
        return "", 204

    return blueprint
