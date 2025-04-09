"""
Main routes for the YouTube Auto Uploader web interface
"""
from flask import render_template
from . import main_bp
import youtube_api
import file_monitor
import config

@main_bp.route('/')
def index():
    """Main dashboard page"""
    # Get current application state
    app_config = config.load_config()
    is_authenticated = youtube_api.youtube is not None
    is_monitoring = file_monitor.get_monitoring_status()
    upload_limit_reached, upload_limit_reset_time = youtube_api.get_upload_limit_status()
    
    return render_template('index.html', 
                          is_authenticated=is_authenticated,
                          is_monitoring=is_monitoring,
                          config=app_config,
                          upload_limit_reached=upload_limit_reached,
                          upload_limit_reset_time=upload_limit_reset_time)
