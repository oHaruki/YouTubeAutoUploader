"""
YouTube API integration for YouTube Auto Uploader
"""
import os
import glob
import pickle
import random
import shutil
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpRequest
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request

# YouTube API constants
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Directories for API credentials
API_CREDENTIALS_DIR = 'credentials'
TOKENS_DIR = 'tokens'

# Legacy paths for backward compatibility
CLIENT_SECRETS_FILE = 'client_secret.json'
TOKEN_PICKLE_FILE = 'token.pickle'

# Create necessary directories
os.makedirs(API_CREDENTIALS_DIR, exist_ok=True)
os.makedirs(TOKENS_DIR, exist_ok=True)

# Track YouTube clients and active client
youtube_clients = {}
active_client_id = None
youtube = None  # Current active client

# Track upload limits
upload_limit_reached = False
upload_limit_reset_time = None

def migrate_legacy_credentials():
    """Migrate legacy credentials to the new directory structure"""
    # Check if old-style client secret exists and migrate it
    if os.path.exists(CLIENT_SECRETS_FILE):
        new_path = os.path.join(API_CREDENTIALS_DIR, 'client_secret_default.json')
        shutil.copy(CLIENT_SECRETS_FILE, new_path)
        os.rename(CLIENT_SECRETS_FILE, f"{CLIENT_SECRETS_FILE}.bak")
        
        # Also migrate token if it exists
        if os.path.exists(TOKEN_PICKLE_FILE):
            new_token_path = os.path.join(TOKENS_DIR, 'token_default.pickle')
            shutil.copy(TOKEN_PICKLE_FILE, new_token_path)
            os.rename(TOKEN_PICKLE_FILE, f"{TOKEN_PICKLE_FILE}.bak")

def get_available_api_projects():
    """
    Get a list of available API projects based on client secret files
    
    Returns:
        list: List of dictionaries containing project information
    """
    # First check if legacy credentials exist and migrate them
    migrate_legacy_credentials()
    
    # Look for all client secret files in the credentials directory
    client_files = glob.glob(os.path.join(API_CREDENTIALS_DIR, 'client_secret_*.json'))
    
    # Extract project IDs from filenames
    projects = []
    for file_path in client_files:
        filename = os.path.basename(file_path)
        # Extract project ID from filename (format: client_secret_PROJECT_ID.json)
        if '_' in filename and '.' in filename:
            parts = filename.split('_', 1)[1].split('.')[0]
            projects.append({
                'id': parts,
                'file_path': file_path,
                'token_path': os.path.join(TOKENS_DIR, f'token_{parts}.pickle')
            })
    
    return projects

def get_youtube_api_with_retry():
    """
    Creates YouTube API client with retry capabilities for transient network issues
    
    Returns:
        function: A function to build YouTube API clients with retry logic
    """
    # Store the original execute method
    original_execute = HttpRequest.execute
    
    # Create a patched execute method with retry logic
    def _patched_execute(self, *args, **kwargs):
        from config import load_config
        
        config = load_config()
        max_retries = config.get('max_retries', 3)
        retry_count = 0
        
        while retry_count <= max_retries:
            try:
                return original_execute(self, *args, **kwargs)
            except HttpError as e:
                # Don't retry for most HTTP errors
                if e.resp.status < 500:
                    raise
                retry_count += 1
                if retry_count > max_retries:
                    raise
                # Exponential backoff
                time.sleep(2 ** retry_count)
            except Exception as e:
                error_str = str(e).lower()
                # Retry on network errors
                if ("ssl" in error_str or 
                   "connection" in error_str or 
                   "timeout" in error_str or 
                   "broken pipe" in error_str):
                    retry_count += 1
                    if retry_count > max_retries:
                        raise
                    # Exponential backoff
                    time.sleep(2 ** retry_count)
                else:
                    # Don't retry for other types of errors
                    raise
    
    # Patch the execute method
    HttpRequest.execute = _patched_execute
    
    # All subsequent API calls will use our patched execute method
    return build

def select_api_project(project_id=None):
    """
    Select an API project to use
    
    Args:
        project_id (str, optional): ID of the project to select. If None, try to find an authenticated project.
        
    Returns:
        object: YouTube API client if successful, None otherwise
    """
    global youtube, active_client_id
    
    projects = get_available_api_projects()
    
    if not projects:
        return None
    
    # If no specific project requested, try to use the one that's already authenticated
    if project_id is None:
        # First check if we have a previously authenticated project
        for project in projects:
            if os.path.exists(project['token_path']):
                project_id = project['id']
                break
        
        # If still no project, pick a random one
        if project_id is None and projects:
            project = random.choice(projects)
            project_id = project['id']
    
    # Find the selected project
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    if not selected_project:
        return None
    
    # If we already have this client loaded, activate it
    if project_id in youtube_clients:
        youtube = youtube_clients[project_id]
        active_client_id = project_id
        return youtube
    
    # Try to authenticate with this project
    client_file = selected_project['file_path']
    token_file = selected_project['token_path']
    
    if os.path.exists(token_file):
        try:
            with open(token_file, 'rb') as token:
                credentials = pickle.load(token)
                
                # Refresh if needed
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    
                    # Save refreshed token
                    with open(token_file, 'wb') as token_out:
                        pickle.dump(credentials, token_out)
                
                # Use our improved builder with retry logic
                client_builder = get_youtube_api_with_retry()
                client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
                
                youtube_clients[project_id] = client
                youtube = client
                active_client_id = project_id
                return client
        except Exception as e:
            print(f"Error loading credentials for project {project_id}: {e}")
    
    return None

def handle_upload_limit_error(previous_client_id):
    """
    Try to switch to a different API client when hitting upload limits
    
    Args:
        previous_client_id (str): ID of the client that hit the upload limit
        
    Returns:
        object: New YouTube API client if available, None otherwise
    """
    # Mark current client as limited
    if previous_client_id:
        youtube_clients.pop(previous_client_id, None)
    
    # Try to find another authenticated client
    projects = get_available_api_projects()
    for project in projects:
        if project['id'] != previous_client_id and os.path.exists(project['token_path']):
            return select_api_project(project['id'])
    
    return None

def get_youtube_service():
    """
    Get an authenticated YouTube service, try all available projects if needed
    
    Returns:
        object: YouTube API client if successful, None otherwise
    """
    global youtube
    
    # If we already have a YouTube client, return it
    if youtube:
        return youtube
    
    # Try to authenticate with each available project
    projects = get_available_api_projects()
    
    if not projects:
        # No projects available
        return None
    
    # Try each project until one works
    for project in projects:
        client = select_api_project(project['id'])
        if client:
            return client
    
    return None

def set_upload_limit_reached(duration_hours=24):
    """
    Set the upload limit reached flag and calculate reset time
    
    Args:
        duration_hours (int): Number of hours to wait before resetting
    """
    global upload_limit_reached, upload_limit_reset_time
    upload_limit_reached = True
    upload_limit_reset_time = datetime.now() + timedelta(hours=duration_hours)

def get_upload_limit_status():
    """
    Get the current upload limit status
    
    Returns:
        tuple: (is_limit_reached, reset_time)
    """
    # Reset upload limit if time has passed
    global upload_limit_reached, upload_limit_reset_time
    
    if upload_limit_reached and upload_limit_reset_time and datetime.now() > upload_limit_reset_time:
        upload_limit_reached = False
        upload_limit_reset_time = None
        
    return (upload_limit_reached, upload_limit_reset_time)

def get_channel_list():
    """
    Get the list of YouTube channels for the authenticated user
    
    Returns:
        list: List of channel dictionaries if successful, empty list otherwise
    """
    if not youtube:
        return []
    
    try:
        # Request channels list from YouTube API
        channels_response = youtube.channels().list(
            part='snippet,contentDetails',
            mine=True
        ).execute()
        
        channels = []
        for channel in channels_response.get('items', []):
            channels.append({
                'id': channel['id'],
                'title': channel['snippet']['title'],
                'thumbnail': channel['snippet']['thumbnails']['default']['url'],
                'uploads_playlist': channel['contentDetails']['relatedPlaylists']['uploads']
            })
        
        return channels
    except Exception as e:
        print(f"Error getting channel list: {e}")
        return []
