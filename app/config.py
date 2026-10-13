"""
config.py
Purpose: Reads all settings from environment variables (loaded from a
         .env file that is never committed). No credentials live in code.
         Pattern follows the Sept 17 activity's require_env/get_db.
Authors: Anna Running Rabbit
Date created:         2026-10-13
Date last editted:    2026-10-13
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env sits in the repo root locally; on the VM it can live outside the
# repo, pointed to by ENV_FILE (e.g. /etc/campus-events/campus.env).
DEFAULT_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(os.environ.get("ENV_FILE", DEFAULT_ENV_FILE))


def require_env(name):
    """
    Return a required environment variable or fail with a clear message.

    Parameters:
        name (str): Variable name, e.g. "MYSQL_USER".

    Returns:
        str: The variable's value.

    Raises:
        RuntimeError: If the variable is missing or empty.
    """
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Copy .env.example to .env and fill it in."
        )
    return value


def get_db_settings():
    """
    Collect MySQL connection settings for repository.py (owned by C).

    Parameters:
        None

    Returns:
        dict: Keyword arguments for mysql.connector.connect().
    """
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
        "user": require_env("MYSQL_USER"),
        "password": require_env("MYSQL_PASSWORD"),
        "database": require_env("MYSQL_DATABASE"),
        # Keeps DATETIME comparisons in UTC regardless of server timezone.
        "time_zone": "+00:00",
    }


def is_debug_enabled():
    """
    Report whether Flask debug mode is on. Defaults to off so the
    deployed VM can never show the debugger by accident.

    Parameters:
        None

    Returns:
        bool: True only if FLASK_DEBUG is explicitly "1".
    """
    return os.environ.get("FLASK_DEBUG", "0") == "1"
