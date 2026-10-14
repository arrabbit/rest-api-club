"""
__init__.py
Purpose: Application factory. Builds the Flask app, registers JSON error
         handlers, and exposes a health route (GET /api) like the one from
         the Sept 15 activity. Temporary skeleton so the VM can be deployed;
         E owns this file and adds the event and registration blueprints.
Authors: Precious (owner), Anna Running Rabbit (created skeleton)
Date created:         2026-10-13
Date last edited:    2026-10-13
"""

from flask import Flask, jsonify
from app.config import is_debug_enabled
from app.errors import register_error_handlers


def create_app(test_config=None):
    """
    Build and configure the Flask application.

    Parameters:
        None

    Returns:
        Flask: The configured application, ready for gunicorn or tests.
    """
    app = Flask(__name__)
    
    app.config["DEBUG"] = is_debug_enabled()
    # coordinate with D: their comment says the deployed debugger cannot turn on accidentally, 
    # but the function still enables debug if FLASK_DEBUG=1
    
    if test_config is not None:
        app.cofig.update(test_config)
        
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
        return jsonify({
            "status": "ok", 
            "message": "Campus Events API is running"
        }), 200
        
    
    from app.routes.events import create_event_blueprint
    from app import repository
    from app.routes.registrations import create_registration_blueprint
    
    app.register_blueprint(create_registration_blueprint(repository))
    app.register_blueprint(create_event_blueprint)

    return app
