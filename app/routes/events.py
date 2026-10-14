"""
events.py
Purpose: Event routes (create, list, get, update, delete) for the Campus
         Events API, plus helpers that shape event data for the contract.
Authors: Jordan Senko
Date created:         2026-10-14
Date last editted:    2026-10-14
"""

from datetime import timezone
from app.errors import ApiError

def event_to_json(row: dict) -> dict:
    """
    Turn a repository row (snake_case) into the API event (camelCase).

    Parameters:
        row (dict): id, title, location, start_time, capacity, registered_count.

    Returns:
        dict: The seven event fields.
    """

    start_time = row["start_time"]
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=timezone.utc)
    else:
        start_time = start_time.astimezone(timezone.utc)
    spots_left = row["capacity"] - row["registered_count"]
    
    return {
        "id": row["id"],
        "title": row["title"],
        "location": row["location"],
        "startTime": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    # TODO