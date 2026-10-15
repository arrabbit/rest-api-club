"""
events.py
Purpose: Event routes (create, list, get, update, delete) for the Campus
         Events API, plus helpers that shape event data for the contract.
Authors: Jordan Senko
Date created:         2026-10-14
Date last editted:    2026-10-14
"""
from datetime import datetime, timezone
from flask import Blueprint, jsonify
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
    def list_events():
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
        row = repository.get_event(parsed_id)
        if row is None:
            raise ApiError(404, "EVENT_NOT_FOUND", f"No event with id {parsed_id}.", {"eventId": parsed_id})
        return event_to_json(row)

    return blueprint
