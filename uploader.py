"""
Video upload functionality for YouTube Auto Uploader - Debug Version
"""
import os
import time
import logging
import threading
from datetime import datetime, timedelta
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from models import UploadTask
import youtube_api
import config

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('uploader')

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
    
    # Normalize the file path to ensure consistent handling
    try:
        file_path = os.path.abspath(os.path.expanduser(file_path))
        logger.info(f"Adding file to upload queue: {file_path}")
    except Exception as e:
        logger.error(f"Error normalizing file path: {e}")
        return None
    
    # Verify file exists and is accessible
    if not os.path.exists(file_path):
        logger.error(f"File does not exist: {file_path}")
        return None
    
    if not os.path.isfile(file_path):
        logger.error(f"Path is not a file: {file_path}")
        return None
        
    # Check file size - don't add empty files
    try:
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.error(f"File is empty (0 bytes): {file_path}")
            return None
        logger.info(f"File size: {file_size} bytes")
    except Exception as e:
        logger.error(f"Error checking file size: {e}")
        return None
        
    # Check if this file is already in the queue
    for task in upload_queue:
        if os.path.samefile(task.file_path, file_path):
            logger.warning(f"File already in queue: {file_path}, status: {task.status}")
            return None
        
    # Add to queue
    try:
        task = UploadTask(file_path)
        
        # Double check task was created correctly
        if not task or not task.id:
            logger.error(f"Failed to create task for file: {file_path}")
            return None
            
        upload_queue.append(task)
        logger.info(f"Added to queue: {task.filename} (ID: {task.id})")
        
        # Start processing if not already running
        ensure_upload_thread_running()
        
        return task
    except Exception as e:
        logger.error(f"Error adding file to queue: {e}")
        return None

def ensure_upload_thread_running():
    """Ensure that the upload queue processing thread is running"""
    global upload_thread
    
    if upload_thread is None or not upload_thread.is_alive():
        logger.info("Starting upload queue processing thread")
        upload_thread = threading.Thread(target=process_upload_queue)
        upload_thread.daemon = True
        upload_thread.start()

def process_upload_queue():
    """Process the upload queue in a background thread"""
    logger.info("Upload queue processing thread started")
    
    while True:
        try:
            # Log current queue status
            pending_count = len([t for t in upload_queue if t.status == "pending"])
            uploading_count = len([t for t in upload_queue if t.status == "uploading"])
            completed_count = len([t for t in upload_queue if t.status == "completed"])
            error_count = len([t for t in upload_queue if t.status == "error"])
            
            logger.debug(f"Queue status: {len(upload_queue)} total, {pending_count} pending, " + 
                         f"{uploading_count} uploading, {completed_count} completed, {error_count} error")
            
            if not youtube_api.get_youtube_service():
                logger.warning("YouTube service not available, waiting...")
                time.sleep(5)
                continue
            
            # Check upload limit status
            limit_reached, limit_reset_time = youtube_api.get_upload_limit_status()
            if limit_reached:
                if limit_reset_time:
                    reset_time_str = limit_reset_time.strftime('%Y-%m-%d %H:%M:%S')
                    logger.warning(f"Upload limit reached, reset time: {reset_time_str}")
                else:
                    logger.warning("Upload limit reached, no reset time available")
            
            # Find next pending task
            next_task = next((t for t in upload_queue if t.status == "pending"), None)
            
            if next_task and not limit_reached:
                logger.info(f"Processing task: {next_task.filename} (ID: {next_task.id})")
                # Process this task
                upload_video(next_task)
                
                # If this task failed due to upload limit, set a timer
                if next_task.status == "error" and next_task.error and "uploadLimitExceeded" in next_task.error:
                    app_config = config.load_config()
                    reset_hours = app_config.get("upload_limit_duration", 24)
                    logger.warning(f"Upload limit detected, setting reset timer for {reset_hours} hours")
                    youtube_api.set_upload_limit_reached(reset_hours)
            elif next_task and limit_reached:
                logger.info("Pending task exists but upload limit reached, waiting...")
            else:
                # No pending tasks
                logger.debug("No pending tasks in queue")
            
            # Clean up completed tasks
            cleanup_tasks()
            
            # Short delay
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error in upload queue processing: {e}")
            time.sleep(5)

def cleanup_tasks():
    """Clean up tasks that have been completed and deleted"""
    global upload_queue
    
    # Keep tasks that don't meet cleanup criteria
    old_count = len(upload_queue)
    upload_queue = [t for t in upload_queue if not (
        t.status == "completed" and 
        t.delete_success and
        (datetime.now() - datetime.fromtimestamp(t.end_time or 0)).total_seconds() > 3600
    )]
    
    new_count = len(upload_queue)
    if old_count != new_count:
        logger.info(f"Cleaned up {old_count - new_count} completed tasks")

def upload_video(task):
    """
    Upload a video to YouTube
    
    Args:
        task (UploadTask): The upload task
    """
    youtube = youtube_api.youtube
    
    if not youtube:
        task.mark_error("YouTube service not available")
        logger.error("YouTube service not available")
        return
        
    try:
        task.mark_uploading()
        logger.info(f"Starting upload for {task.filename}")
        
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
            logger.error(f"File no longer exists: {task.file_path}")
            return
        
        # Get file size for better chunking
        file_size = os.path.getsize(task.file_path)
        logger.info(f"File size: {file_size} bytes")
        
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
        selected_channel_id = app_config.get('selected_channel_id')
        if selected_channel_id:
            logger.info(f"Uploading on behalf of channel: {selected_channel_id}")
            params['onBehalfOfContentOwner'] = selected_channel_id
        
        # Start upload
        logger.info(f"Creating YouTube upload request for {task.filename}")
        insert_request = youtube.videos().insert(**params)
        
        # Upload with progress tracking and better retry logic
        response = None
        retry_count = 0
        max_retries = app_config.get('max_retries', 3)
        
        while response is None and retry_count <= max_retries:
            try:
                if task.cancel_requested:
                    logger.info(f"Upload cancelled for {task.filename}")
                    insert_request.cancel()
                    task.mark_cancelled()
                    return
                    
                status, response = insert_request.next_chunk()
                if status:
                    task.progress = int(status.progress() * 100)
                    logger.debug(f"Upload progress for {task.filename}: {task.progress}%")
                    # Reset retry counter on successful chunk
                    retry_count = 0
            except HttpError as e:
                error_content = str(e)
                logger.error(f"HTTP error during upload: {error_content}")
                
                # Check for upload limit exceeded
                if "uploadLimitExceeded" in error_content:
                    logger.warning("Upload limit exceeded error detected")
                    # Try to switch to another API client
                    current_client_id = youtube_api.active_client_id
                    new_client = youtube_api.handle_upload_limit_error(current_client_id)
                    
                    if new_client:
                        logger.info(f"Switched to a new API client, retrying upload for {task.filename}")
                        # We switched to a new client, retry the upload from scratch
                        task.status = "pending"
                        task.error = None
                        task.progress = 0
                        return
                    else:
                        # No other clients available, set the limit reached flag
                        reset_hours = app_config.get("upload_limit_duration", 24)
                        logger.warning(f"No other API clients available, setting upload limit for {reset_hours} hours")
                        youtube_api.set_upload_limit_reached(reset_hours)
                        task.mark_error(f"Upload limit exceeded. Will retry in {reset_hours} hours.")
                        return
                
                # Check for SSL or network errors that can be retried
                if "SSL" in error_content or "connection" in error_content.lower() or "timeout" in error_content.lower():
                    retry_count += 1
                    logger.warning(f"Network error during upload, retry {retry_count}/{max_retries}: {error_content}")
                    if retry_count <= max_retries:
                        # Add exponential backoff before retry
                        wait_time = 2 ** retry_count
                        logger.info(f"Waiting {wait_time} seconds before retry...")
                        time.sleep(wait_time)
                        continue
                
                # For other errors, stop trying
                task.mark_error(f"Upload failed: {error_content}")
                logger.error(f"Upload failed for {task.filename}: {error_content}")
                return
                
            except Exception as e:
                # For general exceptions, also implement retry logic
                retry_count += 1
                logger.error(f"Error during upload, retry {retry_count}/{max_retries}: {str(e)}")
                if retry_count <= max_retries:
                    # Add exponential backoff before retry
                    wait_time = 2 ** retry_count
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    continue
                
                task.mark_error(f"Unknown error: {str(e)}")
                logger.error(f"Upload failed for {task.filename} after all retries: {str(e)}")
                return
        
        # If we ran out of retries
        if retry_count > max_retries and response is None:
            task.mark_error("Failed after maximum retry attempts")
            logger.error(f"Upload failed for {task.filename} after maximum retry attempts")
            return
        
        # Upload completed
        if response:
            video_id = response['id']
            task.mark_completed(video_id)
            logger.info(f"Upload completed for {task.filename}, video ID: {video_id}")
            
            # Delete file if configured
            if app_config.get("delete_after_upload"):
                logger.info(f"Attempting to delete file after upload: {task.file_path}")
                delete_video_file(task)
        else:
            task.mark_error("Upload failed - no response received")
            logger.error(f"Upload failed for {task.filename} - no response received")
            
    except Exception as e:
        task.mark_error(str(e))
        logger.error(f"Unexpected error during upload of {task.filename}: {str(e)}")

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
    logger.info(f"Starting file deletion for {task.file_path}, max attempts: {max_attempts}")
    
    for attempt in range(max_attempts):
        try:
            # Ensure file exists
            if not os.path.exists(task.file_path):
                logger.info(f"File no longer exists, marking as deleted: {task.file_path}")
                task.delete_success = True
                return
                
            # Try to delete
            logger.info(f"Deletion attempt {attempt+1}/{max_attempts} for {task.file_path}")
            os.remove(task.file_path)
            
            # If we reach here, deletion was successful
            task.delete_success = True
            logger.info(f"Successfully deleted file: {task.file_path}")
            return
            
        except Exception as e:
            # Mark the attempt
            task.delete_attempts += 1
            logger.warning(f"Failed to delete file (attempt {attempt+1}/{max_attempts}): {e}")
            
            # Wait before retrying
            time.sleep(retry_delay)
    
    # If we get here, all attempts failed
    logger.error(f"Failed to delete file after {max_attempts} attempts: {task.file_path}")
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
        logger.warning(f"Task not found for cancellation: {task_id}")
        return False
    
    if task.status == "pending":
        # Remove from queue if pending
        logger.info(f"Removing pending task from queue: {task.filename} (ID: {task_id})")
        upload_queue.remove(task)
        return True
    elif task.status == "uploading":
        # Request cancellation
        logger.info(f"Requesting cancellation of active upload: {task.filename} (ID: {task_id})")
        task.cancel_requested = True
        return True
    
    logger.warning(f"Cannot cancel task in status {task.status}: {task.filename} (ID: {task_id})")
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
    after_count = len(upload_queue)
    removed = before_count - after_count
    
    if removed > 0:
        logger.info(f"Cleared {removed} completed tasks from queue")
    
    return removed

def init_uploader():
    """Initialize the uploader - call this at application startup"""
    logger.info("Initializing uploader")
    
    try:
        # Register the upload callback with the file monitor
        import file_monitor
        file_monitor.register_callback(add_to_upload_queue)
        logger.info("Registered callback with file_monitor")
        
        # Start the upload thread
        ensure_upload_thread_running()
        logger.info("Uploader initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing uploader: {e}")