import os
import time
import json
import shutil
import pickle
import threading
import glob
import random
from pathlib import Path
from datetime import datetime, timedelta

# Enable insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

from flask import Flask, render_template, request, jsonify, redirect, url_for
import google.oauth2.credentials
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpRequest
from googleapiclient.errors import HttpError
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure OAuth 2.0 credentials
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# Directories for multiple API projects
API_CREDENTIALS_DIR = 'credentials'  # Directory to store multiple client secrets
TOKENS_DIR = 'tokens'  # Directory to store multiple tokens

# Create necessary directories
os.makedirs(API_CREDENTIALS_DIR, exist_ok=True)
os.makedirs(TOKENS_DIR, exist_ok=True)

# Legacy path for backward compatibility
CLIENT_SECRETS_FILE = 'client_secret.json'
TOKEN_PICKLE_FILE = 'token.pickle'
CONFIG_FILE = 'config.json'

# Create Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

# Global variables
upload_queue = []
observer = None
is_monitoring = False
upload_limit_reached = False
upload_limit_reset_time = None
config = {}

# YouTube API clients
youtube_clients = {}
active_client_id = None
youtube = None  # This will always refer to the current active client

class UploadTask:
    def __init__(self, file_path):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.file_size = os.path.getsize(file_path)
        self.id = str(int(time.time() * 1000))
        self.status = "pending"
        self.progress = 0
        self.video_id = None
        self.video_url = None
        self.start_time = None
        self.end_time = None
        self.error = None
        self.cancel_requested = False
        self.delete_attempts = 0
        self.delete_success = False

class VideoEventHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and is_video_file(event.src_path):
            # Wait a short time to ensure the file is completely written
            time.sleep(3)
            
            # Add to upload queue
            add_to_upload_queue(event.src_path)

def load_config():
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
        except:
            return default_config
    return default_config

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def get_available_api_projects():
    """Get a list of available API projects based on client secret files"""
    # First, check if old-style client secret exists and migrate it
    if os.path.exists(CLIENT_SECRETS_FILE):
        new_path = os.path.join(API_CREDENTIALS_DIR, 'client_secret_default.json')
        shutil.copy(CLIENT_SECRETS_FILE, new_path)
        os.rename(CLIENT_SECRETS_FILE, f"{CLIENT_SECRETS_FILE}.bak")
        
        # Also migrate token if it exists
        if os.path.exists(TOKEN_PICKLE_FILE):
            new_token_path = os.path.join(TOKENS_DIR, 'token_default.pickle')
            shutil.copy(TOKEN_PICKLE_FILE, new_token_path)
            os.rename(TOKEN_PICKLE_FILE, f"{TOKEN_PICKLE_FILE}.bak")
    
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
    """
    # Store the original execute method
    original_execute = HttpRequest.execute
    
    # Create a patched execute method with retry logic
    def _patched_execute(self, *args, **kwargs):
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
    """Select an API project to use"""
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
    """Try to switch to a different API client when hitting upload limits"""
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
    """Get an authenticated YouTube service, try all available projects if needed"""
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

def add_to_upload_queue(file_path):
    global upload_queue
    
    # Check if this file is already in the queue
    if any(task.file_path == file_path for task in upload_queue):
        return
        
    # Add to queue
    task = UploadTask(file_path)
    upload_queue.append(task)
    
    # Start processing if not already running
    ensure_upload_thread_running()
    
    return task

def start_monitoring():
    global observer, is_monitoring
    
    if is_monitoring or not config.get("watch_folder"):
        return False
        
    watch_folder = config.get("watch_folder")
    if not os.path.exists(watch_folder):
        return False
        
    try:
        # Set up watchdog observer
        event_handler = VideoEventHandler()
        observer = Observer()
        observer.schedule(event_handler, watch_folder, recursive=False)
        observer.start()
        
        is_monitoring = True
        
        # Check for existing files
        if config.get("check_existing_files"):
            for filename in os.listdir(watch_folder):
                file_path = os.path.join(watch_folder, filename)
                if is_video_file(file_path) and os.path.isfile(file_path):
                    add_to_upload_queue(file_path)
        
        # Make sure upload thread is running
        ensure_upload_thread_running()
        
        return True
    except Exception as e:
        print(f"Error starting monitoring: {e}")
        return False

def stop_monitoring():
    global observer, is_monitoring
    
    if not is_monitoring:
        return True
        
    try:
        if observer:
            observer.stop()
            observer.join()
            observer = None
            
        is_monitoring = False
        return True
    except Exception as e:
        print(f"Error stopping monitoring: {e}")
        return False

def is_video_file(file_path):
    video_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.mkv', '.flv']
    return any(file_path.lower().endswith(ext) for ext in video_extensions)

def ensure_upload_thread_running():
    global upload_thread
    
    if 'upload_thread' not in globals() or not globals()['upload_thread'] or not globals()['upload_thread'].is_alive():
        upload_thread = threading.Thread(target=process_upload_queue)
        upload_thread.daemon = True
        upload_thread.start()

def process_upload_queue():
    global upload_queue, upload_limit_reached, upload_limit_reset_time, youtube
    
    while True:
        if not get_youtube_service():
            time.sleep(5)
            continue
            
        # Reset upload limit if time has passed
        if upload_limit_reached and upload_limit_reset_time and datetime.now() > upload_limit_reset_time:
            upload_limit_reached = False
            upload_limit_reset_time = None
            
        # Find next pending task
        next_task = next((t for t in upload_queue if t.status == "pending"), None)
        
        if next_task and not upload_limit_reached:
            # Process this task
            upload_video(next_task)
            
            # If this task failed due to upload limit, set a timer
            if next_task.status == "error" and "uploadLimitExceeded" in (next_task.error or ""):
                upload_limit_reached = True
                reset_hours = config.get("upload_limit_duration", 24)
                upload_limit_reset_time = datetime.now() + timedelta(hours=reset_hours)
        
        # Clean up completed tasks
        cleanup_tasks()
        
        # Short delay
        time.sleep(1)

def cleanup_tasks():
    """Clean up tasks that have been completed and deleted"""
    global upload_queue
    
    # Keep tasks that don't meet cleanup criteria
    upload_queue = [t for t in upload_queue if not (
        t.status == "completed" and 
        t.delete_success and
        (datetime.now() - datetime.fromtimestamp(t.end_time or 0)).total_seconds() > 3600
    )]

def upload_video(task):
    global youtube, active_client_id
    
    if not youtube:
        task.status = "error"
        task.error = "YouTube service not available"
        return
        
    try:
        task.status = "uploading"
        task.progress = 0
        task.start_time = time.time()
        
        # Prepare metadata
        video_title = config.get("title_template", "").format(
            filename=os.path.splitext(task.filename)[0]
        )
        
        tags_list = []
        if config.get("tags"):
            tags_list = [tag.strip() for tag in config.get("tags", "").split(',')]
            
        body = {
            'snippet': {
                'title': video_title,
                'description': config.get("description", ""),
                'tags': tags_list,
                'categoryId': '20'  # Gaming
            },
            'status': {
                'privacyStatus': config.get("privacy", "unlisted"),
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Make sure file exists
        if not os.path.exists(task.file_path):
            task.status = "error"
            task.error = "File no longer exists"
            return
        
        # Get file size for better chunking
        file_size = os.path.getsize(task.file_path)
        
        # Use larger chunk size for bigger files (4MB for files >100MB, 1MB otherwise)
        chunk_size = 4 * 1024 * 1024 if file_size > 100 * 1024 * 1024 else 1024 * 1024
            
        # Prepare upload with optimized settings
        media = MediaFileUpload(
            task.file_path, 
            chunksize=chunk_size,
            resumable=True
        )
        
        # Create the upload request with channel ID if available
        params = {
            'part': ','.join(body.keys()),
            'body': body,
            'media_body': media
        }
        
        # Add the onBehalfOfContentOwner parameter if we have a selected channel
        if config.get('selected_channel_id'):
            params['onBehalfOfContentOwner'] = config.get('selected_channel_id')
        
        # Start upload
        insert_request = youtube.videos().insert(**params)
        
        # Upload with progress tracking and better retry logic
        response = None
        retry_count = 0
        max_retries = config.get('max_retries', 3)
        
        while response is None and retry_count <= max_retries:
            try:
                if task.cancel_requested:
                    insert_request.cancel()
                    task.status = "cancelled"
                    return
                    
                status, response = insert_request.next_chunk()
                if status:
                    task.progress = int(status.progress() * 100)
                    # Reset retry counter on successful chunk
                    retry_count = 0
            except HttpError as e:
                error_content = str(e)
                
                # Check for upload limit exceeded
                if "uploadLimitExceeded" in error_content:
                    # Try to switch to another API client
                    current_client_id = active_client_id
                    new_client = handle_upload_limit_error(current_client_id)
                    
                    if new_client:
                        # We switched to a new client, retry the upload from scratch
                        task.status = "pending"
                        task.error = None
                        task.progress = 0
                        return
                    else:
                        # No other clients available, set the limit reached flag
                        global upload_limit_reached, upload_limit_reset_time
                        upload_limit_reached = True
                        reset_hours = config.get("upload_limit_duration", 24)
                        upload_limit_reset_time = datetime.now() + timedelta(hours=reset_hours)
                        task.status = "error"
                        task.error = f"Upload limit exceeded. Will retry in {reset_hours} hours."
                        return
                
                # Check for SSL or network errors that can be retried
                if "SSL" in error_content or "connection" in error_content.lower() or "timeout" in error_content.lower():
                    retry_count += 1
                    print(f"Network error during upload, retry {retry_count}/{max_retries}: {error_content}")
                    if retry_count <= max_retries:
                        # Add exponential backoff before retry
                        wait_time = 2 ** retry_count
                        print(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                
                # For other errors, stop trying
                task.status = "error"
                task.error = f"Upload failed: {error_content}"
                return
                
            except Exception as e:
                # For general exceptions, also implement retry logic
                retry_count += 1
                print(f"Error during upload, retry {retry_count}/{max_retries}: {str(e)}")
                if retry_count <= max_retries:
                    # Add exponential backoff before retry
                    wait_time = 2 ** retry_count
                    print(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                
                task.status = "error"
                task.error = f"Unknown error: {str(e)}"
                return
        
        # If we ran out of retries
        if retry_count > max_retries and response is None:
            task.status = "error"
            task.error = "Failed after maximum retry attempts"
            return
        
        # Upload completed
        if response:
            task.video_id = response['id']
            task.video_url = f"https://youtu.be/{task.video_id}"
            task.status = "completed"
            task.progress = 100
            task.end_time = time.time()
            
            # Delete file if configured
            if config.get("delete_after_upload"):
                delete_video_file(task)
        else:
            task.status = "error"
            task.error = "Upload failed - no response received"
            
    except Exception as e:
        task.status = "error"
        task.error = str(e)

def delete_video_file(task):
    """Try to delete the video file with multiple attempts"""
    if not config.get("delete_after_upload") or task.delete_success:
        return
        
    max_attempts = config.get("delete_retry_count", 5)
    retry_delay = config.get("delete_retry_delay", 5)
    
    # Schedule deletion attempt in a new thread to not block uploads
    threading.Thread(
        target=_try_delete_file, 
        args=(task, max_attempts, retry_delay)
    ).start()

def _try_delete_file(task, max_attempts, retry_delay):
    """Internal function to try file deletion multiple times"""
    for attempt in range(max_attempts):
        try:
            # Ensure file exists
            if not os.path.exists(task.file_path):
                task.delete_success = True
                return
                
            # Try to delete
            os.remove(task.file_path)
            
            # If we reach here, deletion was successful
            task.delete_success = True
            return
            
        except Exception as e:
            # Mark the attempt
            task.delete_attempts += 1
            
            # Wait before retrying
            time.sleep(retry_delay)
    
    # If we get here, all attempts failed
    task.error = f"Failed to delete file after {max_attempts} attempts"

@app.route('/')
def index():
    return render_template('index.html', 
                          is_authenticated=youtube is not None,
                          is_monitoring=is_monitoring,
                          config=config,
                          upload_limit_reached=upload_limit_reached,
                          upload_limit_reset_time=upload_limit_reset_time)

@app.route('/auth')
def auth():
    # Check if we have any projects
    projects = get_available_api_projects()
    
    if not projects:
        return render_template('error.html', 
                               error="No API projects found",
                               message="Please add an API project first")
    
    # Default to first project if none specified
    project = projects[0]
    
    # Create flow instance
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        project['file_path'], SCOPES)
    
    # Set the redirect URI to the /oauth2callback endpoint
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Redirect the user to the authorization URL
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    global youtube
    
    # Default authentication - use the first project
    projects = get_available_api_projects()
    if not projects:
        return render_template('error.html', 
                               error="No API projects found",
                               message="Please add an API project first")
                               
    project = projects[0]
    
    # Create flow instance
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        project['file_path'], SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('oauth2callback', _external=True)
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    # Store credentials
    credentials = flow.credentials
    with open(project['token_path'], 'wb') as token:
        pickle.dump(credentials, token)
    
    # Build the service
    client_builder = get_youtube_api_with_retry()
    youtube = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    youtube_clients[project['id']] = youtube
    active_client_id = project['id']
    
    return redirect('/')

@app.route('/auth/project/<project_id>')
def auth_project(project_id):
    """Authenticate a specific API project"""
    projects = get_available_api_projects()
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    
    if not selected_project:
        return render_template('error.html', 
                               error=f"Project '{project_id}' not found",
                               message="Please check your credentials directory")
    
    # Create flow instance for this project
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        selected_project['file_path'], SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('oauth2callback_project', project_id=project_id, _external=True)
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Redirect the user to the authorization URL
    return redirect(auth_url)

@app.route('/oauth2callback/project/<project_id>')
def oauth2callback_project(project_id):
    """OAuth callback for a specific project"""
    projects = get_available_api_projects()
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    
    if not selected_project:
        return render_template('error.html', 
                               error=f"Project '{project_id}' not found",
                               message="Authorization failed")
    
    # Create flow instance for this project
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        selected_project['file_path'], SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('oauth2callback_project', project_id=project_id, _external=True)
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    # Store credentials
    credentials = flow.credentials
    with open(selected_project['token_path'], 'wb') as token:
        pickle.dump(credentials, token)
    
    # Build and store the service
    client_builder = get_youtube_api_with_retry()
    client = client_builder(API_SERVICE_NAME, API_VERSION, credentials=credentials)
    youtube_clients[project_id] = client
    
    # Set as active client
    global youtube, active_client_id
    youtube = client
    active_client_id = project_id
    
    return redirect('/')

@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    global config
    
    if request.method == 'POST':
        # Update settings
        data = request.json
        
        # Validate folder exists
        if 'watch_folder' in data and data['watch_folder']:
            if not os.path.exists(data['watch_folder']):
                return jsonify({
                    'success': False,
                    'error': 'Folder does not exist'
                })
        
        # Update config
        config.update(data)
        save_config()
        
        return jsonify({
            'success': True,
            'config': config
        })
    else:
        # Return current settings
        return jsonify({
            'success': True,
            'config': config
        })

@app.route('/api/theme', methods=['POST'])
def toggle_theme():
    """Toggle between light and dark theme"""
    data = request.json
    theme = data.get('theme')
    
    if theme not in ['light', 'dark']:
        return jsonify({
            'success': False,
            'error': 'Invalid theme'
        })
    
    config['theme'] = theme
    save_config()
    
    return jsonify({
        'success': True,
        'theme': theme
    })

@app.route('/api/monitor/start', methods=['POST'])
def api_start_monitoring():
    if not get_youtube_service():
        return jsonify({
            'success': False,
            'error': 'Not authenticated with YouTube'
        })
    
    if not config.get('watch_folder'):
        return jsonify({
            'success': False,
            'error': 'No folder selected'
        })
    
    result = start_monitoring()
    
    return jsonify({
        'success': result,
        'error': None if result else 'Failed to start monitoring'
    })

@app.route('/api/monitor/stop', methods=['POST'])
def api_stop_monitoring():
    result = stop_monitoring()
    
    return jsonify({
        'success': result,
        'error': None if result else 'Failed to stop monitoring'
    })

@app.route('/api/queue', methods=['GET'])
def api_get_queue():
    # Return the queue with relevant info
    queue_data = []
    
    for task in upload_queue:
        queue_data.append({
            'id': task.id,
            'filename': task.filename,
            'file_size': task.file_size,
            'status': task.status,
            'progress': task.progress,
            'video_url': task.video_url,
            'error': task.error,
            'start_time': task.start_time,
            'end_time': task.end_time,
            'delete_success': task.delete_success
        })
    
    return jsonify({
        'success': True,
        'queue': queue_data,
        'is_monitoring': is_monitoring,
        'upload_limit_reached': upload_limit_reached,
        'upload_limit_reset_time': upload_limit_reset_time.isoformat() if upload_limit_reset_time else None
    })

@app.route('/api/queue/clear-completed', methods=['POST'])
def api_clear_completed():
    global upload_queue
    
    # Filter out completed tasks
    upload_queue = [t for t in upload_queue if t.status != "completed"]
    
    return jsonify({
        'success': True
    })

@app.route('/api/task/<task_id>/cancel', methods=['POST'])
def api_cancel_task(task_id):
    task = next((t for t in upload_queue if t.id == task_id), None)
    
    if not task:
        return jsonify({
            'success': False,
            'error': 'Task not found'
        })
    
    if task.status == "pending":
        # Remove from queue if pending
        upload_queue.remove(task)
    elif task.status == "uploading":
        # Request cancellation
        task.cancel_requested = True
    else:
        return jsonify({
            'success': False,
            'error': 'Cannot cancel task in current state'
        })
    
    return jsonify({
        'success': True
    })

@app.route('/api/folder/browse', methods=['GET'])
def api_browse_folders():
    start_path = request.args.get('path', os.path.expanduser('~'))
    
    # Sanitize and make sure it exists
    if not os.path.exists(start_path):
        start_path = os.path.expanduser('~')
    
    # Get directories
    try:
        dirs = [d for d in os.listdir(start_path) if os.path.isdir(os.path.join(start_path, d))]
        dirs.sort()
        
        parent = os.path.dirname(start_path) if start_path != '/' else None
        
        return jsonify({
            'success': True,
            'current_path': start_path,
            'parent': parent,
            'directories': dirs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify({
        'is_authenticated': youtube is not None,
        'is_monitoring': is_monitoring,
        'upload_limit_reached': upload_limit_reached,
        'upload_limit_reset_time': upload_limit_reset_time.isoformat() if upload_limit_reset_time else None,
        'watch_folder': config.get('watch_folder', ''),
        'theme': config.get('theme', 'light')
    })

@app.route('/api/channels', methods=['GET'])
def api_get_channels():
    """Get all YouTube channels associated with the authenticated account"""
    if not youtube:
        return jsonify({
            'success': False,
            'error': 'Not authenticated with YouTube'
        })
    
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
        
        return jsonify({
            'success': True,
            'channels': channels,
            'selected_channel': config.get('selected_channel_id')
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/channels/select', methods=['POST'])
def api_select_channel():
    """Set the active channel for uploads"""
    if not youtube:
        return jsonify({
            'success': False,
            'error': 'Not authenticated with YouTube'
        })
    
    data = request.json
    channel_id = data.get('channel_id')
    
    if not channel_id:
        return jsonify({
            'success': False,
            'error': 'No channel ID provided'
        })
    
    # Store selected channel in config
    config['selected_channel_id'] = channel_id
    save_config()
    
    return jsonify({
        'success': True
    })

@app.route('/api/projects', methods=['GET'])
def api_get_projects():
    """Get all available API projects"""
    projects = get_available_api_projects()
    
    # Check which ones are authenticated
    authenticated_projects = []
    for project in projects:
        is_authenticated = os.path.exists(project['token_path'])
        
        # Try to get client name by reading the client secret file
        project_name = project['id']
        try:
            with open(project['file_path'], 'r') as f:
                client_data = json.load(f)
                # Extract project name from client ID or other fields
                web_or_installed = next(iter(client_data.values()))
                if 'client_id' in web_or_installed:
                    project_name = web_or_installed.get('project_id', project['id'])
        except:
            pass
        
        authenticated_projects.append({
            'id': project['id'],
            'name': project_name,
            'is_authenticated': is_authenticated,
            'is_active': project['id'] == active_client_id
        })
    
    return jsonify({
        'success': True,
        'projects': authenticated_projects
    })

@app.route('/api/projects/select', methods=['POST'])
def api_select_project():
    """Select an API project to use"""
    data = request.json
    project_id = data.get('project_id')
    
    if not project_id:
        return jsonify({
            'success': False,
            'error': 'No project ID provided'
        })
    
    # Try to select this project
    client = select_api_project(project_id)
    
    if client:
        return jsonify({
            'success': True
        })
    else:
        # Project needs authentication
        return jsonify({
            'success': False,
            'error': 'Project not authenticated',
            'needs_auth': True,
            'project_id': project_id
        })

@app.route('/api/projects/add', methods=['POST'])
def api_add_project():
    """Register a new client secret file"""
    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'error': 'No file uploaded'
        })
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({
            'success': False,
            'error': 'No file selected'
        })
    
    if not file.filename.endswith('.json'):
        return jsonify({
            'success': False,
            'error': 'File must be a JSON file'
        })
    
    # Generate a unique ID for this project
    project_id = f"project_{int(time.time())}"
    
    # Save the file
    file_path = os.path.join(API_CREDENTIALS_DIR, f'client_secret_{project_id}.json')
    file.save(file_path)
    
    return jsonify({
        'success': True,
        'project_id': project_id
    })

def run_app():
    # Load config
    global config
    config = load_config()
    
    # Try to get YouTube service
    get_youtube_service()
    
    # Run the Flask app
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    run_app()