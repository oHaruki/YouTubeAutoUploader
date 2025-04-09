"""
YouTube Auto Uploader - Main Application Entry Point

A tool for automatically uploading videos to YouTube from a watched folder.
"""
import os

# Enable insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask

# Import modules
import config
import youtube_api
import uploader
import file_monitor
from routes import register_blueprints

def create_app():
    """
    Create and configure the Flask application
    
    Returns:
        Flask: The configured Flask application
    """
    # Create Flask app
    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    
    # Register route blueprints
    register_blueprints(app)
    
    return app

def init_app():
    """Initialize the application components"""
    # Load configuration
    app_config = config.load_config()
    
    # Initialize YouTube API
    youtube_api.get_youtube_service()
    
    # Initialize uploader
    uploader.init_uploader()
    
    # Start monitoring if configured
    if app_config.get('watch_folder') and youtube_api.get_youtube_service():
        file_monitor.start_monitoring(
            app_config.get('watch_folder'),
            app_config.get('check_existing_files', True)
        )

def run_app():
    """Run the Flask application"""
    # Create and initialize the app
    app = create_app()
    init_app()
    
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    run_app()
