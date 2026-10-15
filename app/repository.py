import mysql.connector

from app.config import get_db_settings


def get_connection():
    """
    Open a new MySQL connection using the settings in the environment.

    Parameters: none

    Returns: MySQLConnection
    An open connection. The caller must close it.
    """
    return mysql.connector.connect(**get_db_settings())


# Events
def create_event(title, location, start_time, capacity):
    """
    Insert a new event. The route has already validated the inputs.

    Parameters: title (str), location (str), start_time (datetime, UTC),
    capacity (int, greater than 0)

    Returns: dict
    Row with keys: id, title, location, capacity, start_time.
    """
    raise NotImplementedError


def update_event(event_id, changes):
    """
    Update an existing event. The route has already checked that the
    event exists and that the new values are valid.

    Parameters: event_id (int), changes (dict of any of title, location,
    start_time, capacity mapped to their new values)

    Returns: dict
    The updated row with keys: id, title, location, capacity, start_time.
    """
    raise NotImplementedError


def delete_event(event_id):
    """
    Delete an event. The route checks first that it has no registrations;
    the foreign key also blocks the delete if it does.

    Parameters: event_id (int)

    Returns: None
    """
    raise NotImplementedError


def list_events():
    """
    Return every event, ordered by start time.

    Parameters: none

    Returns: list[dict]
    Rows with keys: id, title, location, capacity, start_time.
    An empty list if there are no events.
    """
    raise NotImplementedError


def get_event(event_id):
    """
    Look up an event by its ID.

    Parameters: event_id (int)

    Returns: dict | None
    Row with keys: id, title, location, capacity, start_time.
    None if no event has that ID.
    """
    raise NotImplementedError


# Participants
def get_participant(participant_id):
    """
    Look up a seeded participant by their ID.

    Parameters: participant_id (int)

    Returns: dict | None
    Row with keys: id, name, email.
    None if no participant has that ID.
    """
    raise NotImplementedError


# Registration
def create_registration(event_id, participant_id):
    """
    Book one place on an event for a participant. The route has already
    checked every booking rule.

    Parameters: event_id (int), participant_id (int)

    Returns: dict
    The new row with keys: id, event_id, participant_id, registered_at.
    """
    raise NotImplementedError


def delete_registration(event_id, registration_id):
    """
    Cancel a registration. Both IDs must match, so a registration can't
    be cancelled through the wrong event.

    Parameters: event_id (int), registration_id (int)

    Returns: bool
    True if a row was deleted. False if nothing matched (never existed,
    already cancelled, or belongs to another event).
    """
    raise NotImplementedError


def list_registrations_with_names(event_id):
    """
    List an event's registrations with each participant's name, using a
    JOIN on participants.

    Parameters: event_id (int)

    Returns: list[dict]
    Rows with keys: id, event_id, participant_id, registered_at,
    participant_name. Oldest first. An empty list if there are none.
    """
    raise NotImplementedError


def count_registrations(event_id):
    """
    Count how many registrations an event currently has.

    Parameters: event_id (int)

    Returns: int
    The number of registrations, 0 if there are none.
    """
    raise NotImplementedError
    

def find_registration(event_id, participant_id):
    """
    Find a participant's registration for an event. Used to reject
    duplicate bookings.

    Parameters: event_id (int), participant_id (int)

    Returns: dict | None
    Row with keys: id, event_id, participant_id, registered_at.
    None if they aren't registered for that event.
    """
    raise NotImplementedError
