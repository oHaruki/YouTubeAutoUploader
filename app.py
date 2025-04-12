"""
YouTube Auto Uploader - Main Application Entry Point

A tool for automatically uploading videos to YouTube from a watched folder.
"""
import os
import sys
import threading
import logging

# Enable insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask

# Import modules
import config
import youtube_api
import uploader
import file_monitor
import auto_updater
from routes import register_blueprints

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('app')

def check_for_updates():
    """Check for updates in a separate thread"""
    try:
        if auto_updater.is_auto_update_enabled():
            logger.info("Checking for updates...")
            updated, new_version, error_message = auto_updater.run_update()
            
            if updated:
                logger.info(f"Updated to version {new_version}, restarting...")
                auto_updater.restart_application()
            elif error_message:
                logger.info(f"Update check result: {error_message}")
        else:
            logger.info("Auto-update is disabled")
    except Exception as e:
        logger.error(f"Error during update check: {e}")

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

def create_version_json():
    """Create the version.json file if it doesn't exist"""
    if not os.path.exists('version.json'):
        auto_updater.get_current_version()
        logger.info("Created version.json file")

def run_app():
    """Run the Flask application"""
    # Create version file if needed
    create_version_json()
    
    # Check for updates on startup (in a separate thread)
    threading.Thread(target=check_for_updates).start()
    
    # Create and initialize the app
    app = create_app()
    init_app()
    
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    run_app()