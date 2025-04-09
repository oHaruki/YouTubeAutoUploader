"""
Routes package initialization
"""
from flask import Blueprint

# Create Blueprints for different route groups
main_bp = Blueprint('main', __name__)
api_bp = Blueprint('api', __name__, url_prefix='/api')
auth_bp = Blueprint('auth', __name__)

# Import the route modules to register them with the blueprints
from . import main_routes, api_routes, auth_routes

def register_blueprints(app):
    """
    Register all blueprints with the Flask app
    
    Args:
        app: Flask application instance
    """
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
