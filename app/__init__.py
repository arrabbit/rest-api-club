"""
__init__.py
Purpose: Application factory. Builds the Flask app, registers JSON error
         handlers, and exposes a health route (GET /api) like the one from
         the Sept 15 activity. Temporary skeleton so the VM can be deployed;
         E owns this file and adds the event and registration blueprints.
Authors: Anna Running Rabbit, Team member E (owner)
Date created:         2026-10-13
Date last editted:    2026-10-13
"""

from flask import Flask, jsonify

from app.errors import register_error_handlers


def create_app():
    """
    Build and configure the Flask application.

    Parameters:
        None

    Returns:
        Flask: The configured application, ready for gunicorn or tests.
    """
    app = Flask(__name__)
    register_error_handlers(app)

    @app.get("/api")
    def health():
        """
        Health check used to confirm the deployed API is running.

        Parameters:
            None

        Returns:
            tuple: (JSON status message, 200)
        """
        return jsonify({"status": "ok", "message": "Campus Events API is running"}), 200

    # E: register the events and registrations blueprints here, e.g.
    # app.register_blueprint(events_bp)

    return app
