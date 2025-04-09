"""
Configuration management for YouTube Auto Uploader
"""
import os
import json

# Default configuration path
CONFIG_FILE = 'config.json'

def load_config():
    """
    Load the application configuration from config.json file
    
    Returns:
        dict: The application configuration
    """
    default_config = {
        "watch_folder": "",
        "title_template": "Gameplay video - {filename}",
        "description": "Automatically uploaded gameplay video",
        "tags": "gameplay, gaming, auto-upload",
        "privacy": "unlisted",
        "delete_after_upload": True,
        "check_existing_files": True,
        "max_retries": 3,
        "upload_limit_duration": 24,  # hours
        "delete_retry_delay": 5,  # seconds
        "delete_retry_count": 5,  # times
        "selected_channel_id": None,  # Selected YouTube channel ID
        "theme": "light"  # Default theme
    }
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return {**default_config, **json.load(f)}
        except Exception as e:
            print(f"Error loading config: {e}")
            return default_config
    return default_config

def save_config(config):
    """
    Save the application configuration to config.json file
    
    Args:
        config (dict): The configuration to save
    """
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def update_config(settings):
    """
    Update the configuration with new settings
    
    Args:
        settings (dict): New settings to apply
        
    Returns:
        dict: The updated configuration
    """
    config = load_config()
    config.update(settings)
    save_config(config)
    return config
