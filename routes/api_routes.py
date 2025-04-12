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
            try:
                # Replace backslashes with forward slashes on Windows for consistency
                if os.name == 'nt':  # Windows
                    watch_folder = watch_folder.replace('\\', '/')
                
                # Expand user directory if it contains a tilde
                if '~' in watch_folder:
                    watch_folder = os.path.expanduser(watch_folder)
                
                # Get absolute path
                watch_folder = os.path.abspath(watch_folder)
                
                print(f"[DEBUG] Normalized watch folder path: {watch_folder}")
                
                # Update the path in the data
                data['watch_folder'] = watch_folder
            except Exception as e:
                print(f"[DEBUG] Error normalizing path: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Error processing path: {str(e)}'
                })
            
            # Verify the folder exists or try to create it
            try:
                if not os.path.exists(watch_folder):
                    print(f"[DEBUG] Creating watch folder: {watch_folder}")
                    os.makedirs(watch_folder, exist_ok=True)
                    
                # Verify the folder is writable and readable
                if not os.access(watch_folder, os.R_OK | os.W_OK):
                    return jsonify({
                        'success': False,
                        'error': f"Folder exists but is not accessible (permission denied): {watch_folder}"
                    })
                    
            except Exception as e:
                print(f"[DEBUG] Failed to create watch folder: {e}")
                return jsonify({
                    'success': False,
                    'error': f"Failed to create or access folder: {str(e)}"
                })
        
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
    import file_monitor  # Import here to avoid circular imports
    
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
            'error': 'No folder selected for monitoring'
        })
    
    # Log the monitoring attempt
    print(f"[DEBUG] API: Attempting to start monitoring for folder: {watch_folder}")
    
    # Normalize the path
    try:
        watch_folder = os.path.abspath(os.path.expanduser(watch_folder))
        print(f"[DEBUG] API: Normalized watch folder path: {watch_folder}")
    except Exception as e:
        print(f"[DEBUG] API: Error normalizing path: {e}")
        return jsonify({
            'success': False,
            'error': f'Error normalizing path: {str(e)}'
        })
    
    # Check if the folder is valid
    if not os.path.exists(watch_folder):
        print(f"[DEBUG] API: Watch folder does not exist: {watch_folder}")
        return jsonify({
            'success': False,
            'error': f'Folder does not exist: {watch_folder}'
        })
    
    if not os.path.isdir(watch_folder):
        print(f"[DEBUG] API: Path is not a directory: {watch_folder}")
        return jsonify({
            'success': False,
            'error': f'Path is not a directory: {watch_folder}'
        })
    
    # Check if the folder is accessible
    if not os.access(watch_folder, os.R_OK):
        print(f"[DEBUG] API: Folder is not readable: {watch_folder}")
        return jsonify({
            'success': False,
            'error': f'Folder is not readable (permission denied): {watch_folder}'
        })
    
    # Store the normalized path back in the config
    app_config['watch_folder'] = watch_folder
    config.save_config(app_config)
    
    # Try to start monitoring
    result = file_monitor.start_monitoring(
        watch_folder,
        app_config.get('check_existing_files', True)
    )
    
    if not result:
        print(f"[DEBUG] API: Failed to start monitoring for folder: {watch_folder}")
        return jsonify({
            'success': False,
            'error': f'Failed to start monitoring for folder: {watch_folder}. Check if the folder exists and is accessible.'
        })
    
    print(f"[DEBUG] API: Successfully started monitoring for folder: {watch_folder}")
    return jsonify({
        'success': True
    })

@api_bp.route('/monitor/stop', methods=['POST'])
def api_stop_monitoring():
    """Stop monitoring the watch folder"""
    import file_monitor  # Import here to avoid circular imports
    
    try:
        result = file_monitor.stop_monitoring()
        
        if result:
            print(f"[DEBUG] API: Successfully stopped monitoring")
            return jsonify({
                'success': True
            })
        else:
            print(f"[DEBUG] API: Failed to stop monitoring")
            return jsonify({
                'success': False,
                'error': 'Failed to stop monitoring'
            })
    except Exception as e:
        print(f"[DEBUG] API: Error stopping monitoring: {e}")
        return jsonify({
            'success': False,
            'error': f'Error stopping monitoring: {str(e)}'
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

@api_bp.route('/folder/verify', methods=['POST'])
def api_verify_folder_path():
    """Verify if a folder path is valid for monitoring"""
    data = request.json
    folder_path = data.get('folder_path', '')
    
    if not folder_path:
        return jsonify({
            'success': False,
            'error': 'No folder path provided'
        })
    
    print(f"[DEBUG] Verifying folder path: {folder_path}")
    
    # Normalize path handling
    try:
        # Replace backslashes with forward slashes on Windows for consistency
        if os.name == 'nt':  # Windows
            folder_path = folder_path.replace('\\', '/')
            
        # Expand user directory if needed
        if '~' in folder_path:
            folder_path = os.path.expanduser(folder_path)
            
        # Get absolute path
        folder_path = os.path.abspath(folder_path)
        
        print(f"[DEBUG] Normalized path: {folder_path}")
    except Exception as e:
        print(f"[DEBUG] Error normalizing path: {e}")
        return jsonify({
            'success': False,
            'error': f'Error processing path: {str(e)}',
            'folder_path': folder_path
        })
    
    # Check if folder exists
    if not os.path.exists(folder_path):
        print(f"[DEBUG] Folder does not exist: {folder_path}")
        return jsonify({
            'success': False,
            'error': f'Folder does not exist: {folder_path}',
            'folder_path': folder_path
        })
    
    # Check if it's actually a directory
    if not os.path.isdir(folder_path):
        print(f"[DEBUG] Not a folder: {folder_path}")
        return jsonify({
            'success': False,
            'error': f'Not a folder: {folder_path}',
            'folder_path': folder_path
        })
    
    # Check if it's readable
    if not os.access(folder_path, os.R_OK):
        print(f"[DEBUG] Folder not readable: {folder_path}")
        return jsonify({
            'success': False,
            'error': f'Folder is not readable (permission denied): {folder_path}',
            'folder_path': folder_path
        })
    
    # Check for video files in the folder
    video_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.mkv', '.flv', '.webm', '.m4v']
    has_videos = False
    
    try:
        for filename in os.listdir(folder_path):
            if any(filename.lower().endswith(ext) for ext in video_extensions):
                has_videos = True
                break
                
        if not has_videos:
            print(f"[DEBUG] No video files found in folder: {folder_path}")
            return jsonify({
                'success': True,
                'warning': True,
                'message': 'Folder is valid but no video files were found',
                'folder_path': folder_path
            })
    except Exception as e:
        print(f"[DEBUG] Error checking for video files: {e}")
        # Continue anyway - this is just an advisory check
    
    print(f"[DEBUG] Folder verified successfully: {folder_path}")
    return jsonify({
        'success': True,
        'folder_path': folder_path,
        'message': 'Folder is valid and accessible'
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
    
    # Get the path from the form data
    folder_path = request.form.get('folder_path', '')
    
    if not folder_path:
        # Fallback to extracting from a temp file if no path provided
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        
        temp_file_path = os.path.join(temp_dir, filename)
        
        try:
            # Save the file temporarily
            file.save(temp_file_path)
            
            # Get the directory of the file
            folder_path = os.path.dirname(os.path.abspath(temp_file_path))
            
            # Remove the temporary 'temp' directory from the path
            folder_path = folder_path.replace(os.path.join(os.getcwd(), 'temp'), '')
            
            # Remove the file
            os.remove(temp_file_path)
            
            # If the extracted path is invalid, use a fallback
            if not folder_path or folder_path == '/':
                # Use a more reliable default path
                if os.name == 'nt':  # Windows
                    folder_path = os.path.join(os.path.expanduser('~'), 'Videos')
                else:  # Mac/Linux
                    folder_path = os.path.expanduser('~/Videos')
        except Exception as e:
            print(f"Error extracting folder path: {e}")
            # Use a default path on error
            if os.name == 'nt':  # Windows
                folder_path = os.path.join(os.path.expanduser('~'), 'Videos')
            else:  # Mac/Linux
                folder_path = os.path.expanduser('~/Videos')
    
    # Normalize the path for the OS
    if os.name == 'nt':
        folder_path = folder_path.replace('\\', '/')
    
    # Check if the path exists, try to create it if it doesn't
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path, exist_ok=True)
            print(f"Created folder path: {folder_path}")
        except Exception as e:
            print(f"Error creating folder path: {e}")
            # Return error if we can't create the folder
            return jsonify({
                'success': False,
                'error': f"Unable to create folder: {str(e)}"
            })
    
    # Verify the folder is accessible
    if not os.access(folder_path, os.R_OK):
        return jsonify({
            'success': False,
            'error': f"Folder is not readable (permission denied): {folder_path}"
        })
    
    return jsonify({
        'success': True,
        'folder_path': folder_path
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
    
@api_bp.route('/updates/check', methods=['GET'])
def check_for_updates():
    """Check for available updates"""
    import auto_updater
    
    try:
        update_available, latest_version, download_url, release_notes = auto_updater.check_for_update()
        current_version = auto_updater.get_current_version()
        
        return jsonify({
            'success': True,
            'update_available': update_available,
            'current_version': current_version,
            'latest_version': latest_version,
            'release_notes': release_notes,
            'auto_update_enabled': auto_updater.is_auto_update_enabled()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@api_bp.route('/updates/apply', methods=['POST'])
def apply_update():
    """Download and apply available update"""
    import auto_updater
    
    try:
        update_available, latest_version, download_url, release_notes = auto_updater.check_for_update()
        
        if not update_available:
            return jsonify({
                'success': False,
                'error': 'No updates available'
            })
        
        zip_path = auto_updater.download_update(download_url)
        if not zip_path:
            return jsonify({
                'success': False,
                'error': 'Failed to download update'
            })
        
        success = auto_updater.apply_update(zip_path, latest_version)
        if not success:
            return jsonify({
                'success': False,
                'error': 'Failed to apply update'
            })
        
        return jsonify({
            'success': True,
            'message': f'Updated to version {latest_version}',
            'require_restart': True
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@api_bp.route('/updates/settings', methods=['POST'])
def update_settings():
    """Update auto-update settings"""
    import auto_updater
    
    try:
        data = request.json
        enabled = data.get('auto_update_enabled', True)
        
        auto_updater.set_auto_update_enabled(enabled)
        
        return jsonify({
            'success': True,
            'auto_update_enabled': enabled
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@api_bp.route('/updates/restart', methods=['POST'])
def restart_app():
    """Restart the application"""
    import auto_updater
    import threading
    
    def delayed_restart():
        # Wait a moment for the response to be sent
        time.sleep(1)
        auto_updater.restart_application()
    
    # Start restart in a separate thread
    threading.Thread(target=delayed_restart).start()
    
    return jsonify({
        'success': True,
        'message': 'Restarting application...'
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