"""
API routes for YouTube Auto Uploader
"""
import os
import time
import json
from datetime import datetime
from flask import request, jsonify

from . import api_bp
import config
import youtube_api
import uploader
import file_monitor

#----------------
# Settings routes
#----------------
@api_bp.route('/settings', methods=['GET', 'POST'])
def settings():
    """Get or update application settings"""
    if request.method == 'POST':
        # Update settings
        data = request.json
        
        # Special handling for watch_folder path
        if 'watch_folder' in data and data['watch_folder']:
            watch_folder = data['watch_folder']
            
            # Normalize path 
            # Replace backslashes with forward slashes on Windows
            if os.name == 'nt':
                watch_folder = watch_folder.replace('\\', '/')
            
            # Expand user directory if it contains a tilde
            if '~' in watch_folder:
                watch_folder = os.path.expanduser(watch_folder)
            
            # Update the path in the data
            data['watch_folder'] = watch_folder
            
            # Try to create the directory if it doesn't exist
            try:
                if not os.path.exists(watch_folder):
                    print(f"[DEBUG] Creating watch folder: {watch_folder}")
                    os.makedirs(watch_folder, exist_ok=True)
            except Exception as e:
                print(f"[DEBUG] Failed to create watch folder: {e}")
                # Continue anyway - we'll handle the error during monitoring
        
        # Update config
        updated_config = config.update_config(data)
        
        return jsonify({
            'success': True,
            'config': updated_config
        })
    else:
        # Return current settings
        return jsonify({
            'success': True,
            'config': config.load_config()
        })

@api_bp.route('/theme', methods=['POST'])
def toggle_theme():
    """Toggle between light and dark theme"""
    data = request.json
    theme = data.get('theme')
    
    if theme not in ['light', 'dark']:
        return jsonify({
            'success': False,
            'error': 'Invalid theme'
        })
    
    # Update theme in config
    app_config = config.load_config()
    app_config['theme'] = theme
    config.save_config(app_config)
    
    return jsonify({
        'success': True,
        'theme': theme
    })

#------------------
# Monitoring routes
#------------------
@api_bp.route('/monitor/start', methods=['POST'])
def api_start_monitoring():
    """Start monitoring the watch folder"""
    if not youtube_api.get_youtube_service():
        return jsonify({
            'success': False,
            'error': 'Not authenticated with YouTube'
        })
    
    app_config = config.load_config()
    watch_folder = app_config.get('watch_folder')
    
    if not watch_folder:
        return jsonify({
            'success': False,
            'error': 'No folder selected'
        })
    
    # Log the monitoring attempt
    print(f"[DEBUG] API: Attempting to start monitoring for folder: {watch_folder}")
    
    # Check if the folder is valid
    if not os.path.exists(watch_folder):
        # Try to expand user directory if it contains a tilde
        if '~' in watch_folder:
            expanded_path = os.path.expanduser(watch_folder)
            if os.path.exists(expanded_path):
                watch_folder = expanded_path
                # Update the config with the expanded path
                app_config['watch_folder'] = expanded_path
                config.save_config(app_config)
                print(f"[DEBUG] API: Updated path with expanded user directory: {expanded_path}")
            else:
                print(f"[DEBUG] API: Expanded path does not exist: {expanded_path}")
        else:
            print(f"[DEBUG] API: Watch folder does not exist: {watch_folder}")
    
    # Try to start monitoring
    result = file_monitor.start_monitoring(
        watch_folder,
        app_config.get('check_existing_files', True)
    )
    
    if not result:
        print(f"[DEBUG] API: Failed to start monitoring for folder: {watch_folder}")
        return jsonify({
            'success': False,
            'error': f'Failed to start monitoring for folder: {watch_folder}'
        })
    
    print(f"[DEBUG] API: Successfully started monitoring for folder: {watch_folder}")
    return jsonify({
        'success': True
    })

@api_bp.route('/monitor/stop', methods=['POST'])
def api_stop_monitoring():
    """Stop monitoring the watch folder"""
    result = file_monitor.stop_monitoring()
    
    return jsonify({
        'success': result,
        'error': None if result else 'Failed to stop monitoring'
    })

#--------------
# Queue routes
#--------------
@api_bp.route('/queue', methods=['GET'])
def api_get_queue():
    """Get the current upload queue"""
    # Get queue data with relevant info
    queue = uploader.get_upload_queue()
    queue_data = [task.to_dict() for task in queue]
    
    # Get upload limit info
    limit_reached, limit_reset_time = youtube_api.get_upload_limit_status()
    
    return jsonify({
        'success': True,
        'queue': queue_data,
        'is_monitoring': file_monitor.get_monitoring_status(),
        'upload_limit_reached': limit_reached,
        'upload_limit_reset_time': limit_reset_time.isoformat() if limit_reset_time else None
    })

@api_bp.route('/queue/clear-completed', methods=['POST'])
def api_clear_completed():
    """Clear completed tasks from the queue"""
    uploader.clear_completed_tasks()
    
    return jsonify({
        'success': True
    })

@api_bp.route('/task/<task_id>/cancel', methods=['POST'])
def api_cancel_task(task_id):
    """Cancel a specific task"""
    result = uploader.cancel_task(task_id)
    
    if not result:
        return jsonify({
            'success': False,
            'error': 'Task not found or cannot be cancelled'
        })
    
    return jsonify({
        'success': True
    })

#--------------
# Folder routes
#--------------
@api_bp.route('/folder/browse', methods=['GET'])
def api_browse_folders():
    """Browse directories for folder selection"""
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

@api_bp.route('/folder/extract-path', methods=['POST'])
def api_extract_folder_path():
    """Extract the folder path from an uploaded file"""
    if 'folder_file' not in request.files:
        return jsonify({
            'success': False,
            'error': 'No file provided'
        })
    
    file = request.files['folder_file']
    
    # Get the filename
    filename = file.filename
    
    # Create a temporary file to save the uploaded file
    temp_dir = os.path.join(os.getcwd(), 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    temp_file_path = os.path.join(temp_dir, filename)
    
    try:
        # Save the file temporarily
        file.save(temp_file_path)
        
        # Get the directory of the file
        folder_path = os.path.dirname(os.path.abspath(temp_file_path))
        
        # Remove the temporary 'temp' directory from the path
        # We want the original folder path, not our temp location
        folder_path = folder_path.replace(os.path.join(os.getcwd(), 'temp'), '')
        
        # If we're on Windows, paths might have backslashes
        if os.name == 'nt':
            folder_path = folder_path.replace('\\', '/')
        
        # Remove the file
        os.remove(temp_file_path)
        
        # Check if the extracted path is valid
        # If it seems like we didn't get a proper path, try another approach
        if not folder_path or folder_path == '/':
            # Get the directory using a different method based on the OS
            if os.name == 'nt':  # Windows
                folder_path = os.path.join(os.path.expanduser('~'), 'Documents')
            else:  # Mac/Linux
                folder_path = os.path.expanduser('~')
        
        return jsonify({
            'success': True,
            'folder_path': folder_path
        })
    except Exception as e:
        # Clean up temp file if it exists
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        print(f"Error extracting folder path: {e}")
        return jsonify({
            'success': False,
            'error': f"Error extracting folder path: {str(e)}"
        })

#--------------
# Status routes
#--------------
@api_bp.route('/status', methods=['GET'])
def api_status():
    """Get the current application status"""
    app_config = config.load_config()
    limit_reached, limit_reset_time = youtube_api.get_upload_limit_status()
    
    return jsonify({
        'is_authenticated': youtube_api.youtube is not None,
        'is_monitoring': file_monitor.get_monitoring_status(),
        'upload_limit_reached': limit_reached,
        'upload_limit_reset_time': limit_reset_time.isoformat() if limit_reset_time else None,
        'watch_folder': app_config.get('watch_folder', ''),
        'theme': app_config.get('theme', 'light')
    })

#----------------
# Channels routes
#----------------
@api_bp.route('/channels', methods=['GET'])
def api_get_channels():
    """Get all YouTube channels associated with the authenticated account"""
    if not youtube_api.youtube:
        return jsonify({
            'success': False,
            'error': 'Not authenticated with YouTube'
        })
    
    channels = youtube_api.get_channel_list()
    app_config = config.load_config()
    
    return jsonify({
        'success': True,
        'channels': channels,
        'selected_channel': app_config.get('selected_channel_id')
    })

@api_bp.route('/channels/select', methods=['POST'])
def api_select_channel():
    """Set the active channel for uploads"""
    if not youtube_api.youtube:
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
    app_config = config.load_config()
    app_config['selected_channel_id'] = channel_id
    config.save_config(app_config)
    
    return jsonify({
        'success': True
    })

#----------------
# Projects routes
#----------------
@api_bp.route('/projects', methods=['GET'])
def api_get_projects():
    """Get all available API projects"""
    projects = youtube_api.get_available_api_projects()
    
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
            'is_active': project['id'] == youtube_api.active_client_id
        })
    
    return jsonify({
        'success': True,
        'projects': authenticated_projects
    })

@api_bp.route('/projects/select', methods=['POST'])
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
    client = youtube_api.select_api_project(project_id)
    
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

@api_bp.route('/projects/add', methods=['POST'])
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
    file_path = os.path.join(youtube_api.API_CREDENTIALS_DIR, f'client_secret_{project_id}.json')
    file.save(file_path)
    
    return jsonify({
        'success': True,
        'project_id': project_id
    })