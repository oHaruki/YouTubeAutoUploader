"""
Video upload functionality for YouTube Auto Uploader
"""
import os
import time
import threading
from datetime import datetime, timedelta
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from models import UploadTask
import youtube_api
import config

# Upload queue
upload_queue = []
upload_thread = None

def add_to_upload_queue(file_path):
    """
    Add a file to the upload queue
    
    Args:
        file_path (str): Path to the video file
        
    Returns:
        UploadTask: The created upload task
    """
    global upload_queue
    
    # Check if this file is already in the queue
    if any(task.file_path == file_path for task in upload_queue):
        return None
        
    # Add to queue
    task = UploadTask(file_path)
    upload_queue.append(task)
    
    # Start processing if not already running
    ensure_upload_thread_running()
    
    return task

def ensure_upload_thread_running():
    """Ensure that the upload queue processing thread is running"""
    global upload_thread
    
    if upload_thread is None or not upload_thread.is_alive():
        upload_thread = threading.Thread(target=process_upload_queue)
        upload_thread.daemon = True
        upload_thread.start()

def process_upload_queue():
    """Process the upload queue in a background thread"""
    while True:
        if not youtube_api.get_youtube_service():
            time.sleep(5)
            continue
        
        # Check upload limit status
        limit_reached, _ = youtube_api.get_upload_limit_status()
        
        # Find next pending task
        next_task = next((t for t in upload_queue if t.status == "pending"), None)
        
        if next_task and not limit_reached:
            # Process this task
            upload_video(next_task)
            
            # If this task failed due to upload limit, set a timer
            if next_task.status == "error" and "uploadLimitExceeded" in (next_task.error or ""):
                app_config = config.load_config()
                reset_hours = app_config.get("upload_limit_duration", 24)
                youtube_api.set_upload_limit_reached(reset_hours)
        
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
    """
    Upload a video to YouTube
    
    Args:
        task (UploadTask): The upload task
    """
    youtube = youtube_api.youtube
    
    if not youtube:
        task.mark_error("YouTube service not available")
        return
        
    try:
        task.mark_uploading()
        
        # Load app configuration
        app_config = config.load_config()
        
        # Prepare metadata
        video_title = app_config.get("title_template", "").format(
            filename=os.path.splitext(task.filename)[0]
        )
        
        tags_list = []
        if app_config.get("tags"):
            tags_list = [tag.strip() for tag in app_config.get("tags", "").split(',')]
            
        body = {
            'snippet': {
                'title': video_title,
                'description': app_config.get("description", ""),
                'tags': tags_list,
                'categoryId': '20'  # Gaming
            },
            'status': {
                'privacyStatus': app_config.get("privacy", "unlisted"),
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Make sure file exists
        if not os.path.exists(task.file_path):
            task.mark_error("File no longer exists")
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
        if app_config.get('selected_channel_id'):
            params['onBehalfOfContentOwner'] = app_config.get('selected_channel_id')
        
        # Start upload
        insert_request = youtube.videos().insert(**params)
        
        # Upload with progress tracking and better retry logic
        response = None
        retry_count = 0
        max_retries = app_config.get('max_retries', 3)
        
        while response is None and retry_count <= max_retries:
            try:
                if task.cancel_requested:
                    insert_request.cancel()
                    task.mark_cancelled()
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
                    current_client_id = youtube_api.active_client_id
                    new_client = youtube_api.handle_upload_limit_error(current_client_id)
                    
                    if new_client:
                        # We switched to a new client, retry the upload from scratch
                        task.status = "pending"
                        task.error = None
                        task.progress = 0
                        return
                    else:
                        # No other clients available, set the limit reached flag
                        reset_hours = app_config.get("upload_limit_duration", 24)
                        youtube_api.set_upload_limit_reached(reset_hours)
                        task.mark_error(f"Upload limit exceeded. Will retry in {reset_hours} hours.")
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
                task.mark_error(f"Upload failed: {error_content}")
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
                
                task.mark_error(f"Unknown error: {str(e)}")
                return
        
        # If we ran out of retries
        if retry_count > max_retries and response is None:
            task.mark_error("Failed after maximum retry attempts")
            return
        
        # Upload completed
        if response:
            task.mark_completed(response['id'])
            
            # Delete file if configured
            if app_config.get("delete_after_upload"):
                delete_video_file(task)
        else:
            task.mark_error("Upload failed - no response received")
            
    except Exception as e:
        task.mark_error(str(e))

def delete_video_file(task):
    """
    Try to delete the video file with multiple attempts
    
    Args:
        task (UploadTask): The upload task
    """
    app_config = config.load_config()
    
    if not app_config.get("delete_after_upload") or task.delete_success:
        return
        
    max_attempts = app_config.get("delete_retry_count", 5)
    retry_delay = app_config.get("delete_retry_delay", 5)
    
    # Schedule deletion attempt in a new thread to not block uploads
    threading.Thread(
        target=_try_delete_file, 
        args=(task, max_attempts, retry_delay)
    ).start()

def _try_delete_file(task, max_attempts, retry_delay):
    """
    Internal function to try file deletion multiple times
    
    Args:
        task (UploadTask): The upload task
        max_attempts (int): Maximum number of deletion attempts
        retry_delay (int): Delay in seconds between attempts
    """
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

def get_upload_queue():
    """
    Get the current upload queue
    
    Returns:
        list: List of upload tasks
    """
    return upload_queue

def cancel_task(task_id):
    """
    Cancel an upload task
    
    Args:
        task_id (str): ID of the task to cancel
        
    Returns:
        bool: True if task was cancelled, False otherwise
    """
    task = next((t for t in upload_queue if t.id == task_id), None)
    
    if not task:
        return False
    
    if task.status == "pending":
        # Remove from queue if pending
        upload_queue.remove(task)
        return True
    elif task.status == "uploading":
        # Request cancellation
        task.cancel_requested = True
        return True
    
    return False

def clear_completed_tasks():
    """
    Remove all completed tasks from the queue
    
    Returns:
        int: Number of tasks removed
    """
    global upload_queue
    
    before_count = len(upload_queue)
    upload_queue = [t for t in upload_queue if t.status != "completed"]
    
    return before_count - len(upload_queue)

def init_uploader():
    """Initialize the uploader - call this at application startup"""
    # Register the upload callback with the file monitor
    import file_monitor
    file_monitor.register_callback(add_to_upload_queue)
    
    # Start the upload thread
    ensure_upload_thread_running()
