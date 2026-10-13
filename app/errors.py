"""
errors.py
Purpose: Defines ApiError and registers JSON error handlers so every
         4xx and 5xx response uses the same shape:
         {"error": {"code": ..., "message": ..., "details": ...}}
         No stack traces, SQL text or credentials ever reach the client.
Authors: Anna Running Rabbit
Date created:         2026-10-13
Date last editted:    2026-10-13
"""

import logging

import mysql.connector
from flask import jsonify
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

# Maps Flask/werkzeug built-in HTTP errors to our stable error codes.
HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    415: "UNSUPPORTED_MEDIA_TYPE",
}


class ApiError(Exception):
    """
    Exception raised by routes when a request cannot complete normally.

    Parameters:
        status (int): HTTP status code, e.g. 404.
        code (str): Stable machine-readable code, e.g. "EVENT_NOT_FOUND".
        message (str): Human-readable explanation, safe to show clients.
        details (dict | list | None): Optional extra info, safe to expose.
    """

    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def build_error_response(status, code, message, details=None):
    """
    Build the single JSON error shape used by every error response.

    Parameters:
        status (int): HTTP status code.
        code (str): Stable error code.
        message (str): Human-readable message.
        details (dict | list | None): Optional safe details.

    Returns:
        tuple: (Flask JSON response, status code)
    """
    body = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return jsonify(body), status


def handle_api_error(error):
    """
    Convert an ApiError raised by a route into a JSON response.

    Parameters:
        error (ApiError): The raised error.

    Returns:
        tuple: (Flask JSON response, status code)
    """
    return build_error_response(
        error.status, error.code, error.message, error.details
    )


def handle_http_exception(error):
    """
    Convert Flask's built-in HTML errors (unknown route, wrong method,
    malformed JSON) into our JSON shape.

    Parameters:
        error (HTTPException): The werkzeug exception Flask raised.

    Returns:
        tuple: (Flask JSON response, status code)
    """
    code = HTTP_ERROR_CODES.get(error.code, "HTTP_ERROR")
    # error.description is werkzeug's generic text; it never contains internals.
    return build_error_response(error.code, code, error.description)


def handle_integrity_error(error):
    """
    Backstop for database constraint violations (UNIQUE, FOREIGN KEY)
    that slip past route checks. Returns 409 without any SQL text.

    Parameters:
        error (mysql.connector.IntegrityError): The database error.

    Returns:
        tuple: (Flask JSON response, status code)
    """
    # Log the real error on the server only; the client sees a generic message.
    logger.warning("IntegrityError: %s", error)
    return build_error_response(
        409, "CONFLICT", "The request conflicts with existing data."
    )


def handle_unexpected_error(error):
    """
    Catch-all for anything unexpected. Logs the stack trace on the server
    and returns a generic 500 with no internal details.

    Parameters:
        error (Exception): Any unhandled exception.

    Returns:
        tuple: (Flask JSON response, status code)
    """
    logger.exception("Unhandled error: %s", error)
    return build_error_response(
        500, "INTERNAL_ERROR", "An unexpected error occurred."
    )


def register_error_handlers(app):
    """
    Attach every JSON error handler to the Flask app. Called once from
    create_app() in app/__init__.py (owned by E).

    Parameters:
        app (Flask): The Flask application.

    Returns:
        None
    """
    app.register_error_handler(ApiError, handle_api_error)
    app.register_error_handler(HTTPException, handle_http_exception)
    app.register_error_handler(
        mysql.connector.IntegrityError, handle_integrity_error
    )
    # Exception is registered last; Flask still picks the most specific match.
    app.register_error_handler(Exception, handle_unexpected_error)
