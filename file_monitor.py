"""
File system monitoring functionality for YouTube Auto Uploader - Debug Version
"""
import os
import time
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('file_monitor')

# Record of active monitoring state and observer instance
is_monitoring = False
observer = None
current_watch_folder = None

# Function to be called when a new file is detected
# Will be set by the uploader module
on_new_file_callback = None

# Track files we've already seen to avoid duplicate processing
processed_files = set()

class VideoEventHandler(FileSystemEventHandler):
    """
    Watchdog handler for detecting new video files
    """
    def on_created(self, event):
        logger.info(f"File system event: {event.event_type} - {event.src_path}")
        
        if not event.is_directory:
            file_path = event.src_path
            logger.info(f"File created: {file_path}")
            
            if is_video_file(file_path):
                logger.info(f"Video file detected: {file_path}")
                
                # Check if this file has already been processed
                if file_path in processed_files:
                    logger.info(f"File already processed, skipping: {file_path}")
                    return
                
                # Wait for the file to stabilize (no more writes)
                if wait_for_file_stability(file_path):
                    # Mark as processed to avoid duplicate processing
                    processed_files.add(file_path)
                    
                    # Call the callback function with the detected file
                    if on_new_file_callback:
                        logger.info(f"Processing stable video file: {file_path}")
                        try:
                            on_new_file_callback(file_path)
                        except Exception as e:
                            logger.error(f"Error in callback for file {file_path}: {e}")
                    else:
                        logger.error("No callback function registered for file processing")
                else:
                    logger.warning(f"File did not stabilize within timeout period: {file_path}")
            else:
                logger.info(f"Non-video file ignored: {file_path}")

def wait_for_file_stability(file_path, check_interval=1, max_wait_time=30, size_change_threshold=0):
    """
    Wait for a file to stop changing size, indicating it's no longer being written
    
    Args:
        file_path (str): Path to the file
        check_interval (int): Number of seconds between size checks
        max_wait_time (int): Maximum time to wait in seconds
        size_change_threshold (int): Allow this many bytes of change between checks
        
    Returns:
        bool: True if file stabilized, False if timed out or file disappeared
    """
    logger.info(f"Waiting for file to stabilize: {file_path}")
    
    try:
        # First, make sure the file exists
        if not os.path.exists(file_path):
            logger.warning(f"File does not exist: {file_path}")
            return False
        
        # Initial size check
        try:
            initial_size = os.path.getsize(file_path)
            last_size = initial_size
            logger.info(f"Initial file size: {initial_size} bytes")
        except Exception as e:
            logger.error(f"Error getting initial file size: {e}")
            return False
        
        # If file is empty, wait a moment and check again
        if initial_size == 0:
            logger.warning(f"File is empty, waiting briefly: {file_path}")
            time.sleep(3)
            
            if not os.path.exists(file_path):
                return False
                
            try:
                initial_size = os.path.getsize(file_path)
                last_size = initial_size
                
                if initial_size == 0:
                    logger.warning(f"File is still empty after waiting: {file_path}")
                    return False
                    
                logger.info(f"File now has size: {initial_size} bytes")
            except Exception as e:
                logger.error(f"Error getting file size after wait: {e}")
                return False
                
        # Start waiting for stability
        start_time = time.time()
        stable = False
        
        while (time.time() - start_time) < max_wait_time:
            # Wait for check interval
            time.sleep(check_interval)
            
            # Check if file still exists
            if not os.path.exists(file_path):
                logger.warning(f"File no longer exists: {file_path}")
                return False
            
            # Check current size
            try:
                current_size = os.path.getsize(file_path)
                logger.debug(f"Current file size: {current_size} bytes (change: {current_size - last_size} bytes)")
                
                # Check if size is stable
                if abs(current_size - last_size) <= size_change_threshold:
                    logger.info(f"File size has stabilized at {current_size} bytes")
                    stable = True
                    break
                    
                # Update last size for next check
                last_size = current_size
            except Exception as e:
                logger.error(f"Error checking file size: {e}")
                return False
        
        if not stable:
            logger.warning(f"Timed out waiting for file to stabilize: {file_path}")
            
        # If the file has at least some content, consider it stable enough
        if last_size > 0:
            logger.info(f"File has content ({last_size} bytes), considering it stable enough")
            return True
            
        return stable
        
    except Exception as e:
        logger.error(f"Error waiting for file stability: {e}")
        return False

def is_video_file(file_path):
    """
    Check if a file is a video file based on its extension
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        bool: True if the file is a video file, False otherwise
    """
    # Expanded list of video extensions
    video_extensions = [
        '.mp4', '.avi', '.mov', '.wmv', '.mkv', '.flv', 
        '.webm', '.m4v', '.mpg', '.mpeg', '.3gp', '.3g2',
        '.ts', '.mts', '.m2ts', '.vob', '.ogv', '.rm',
        '.rmvb', '.asf', '.divx', '.f4v'
    ]
    
    if not file_path:
        logger.warning("Empty file path provided to is_video_file")
        return False
        
    try:
        is_video = any(file_path.lower().endswith(ext) for ext in video_extensions)
        logger.info(f"File extension check for {file_path}: {'MATCH' if is_video else 'NO MATCH'}")
        return is_video
    except Exception as e:
        logger.error(f"Error checking if file is video: {e}")
        return False

def register_callback(callback_function):
    """
    Register a callback function to be called when a new file is detected
    
    Args:
        callback_function (function): Function to call with the file path
    """
    global on_new_file_callback
    on_new_file_callback = callback_function
    logger.info(f"Callback function registered: {callback_function.__name__ if callback_function else None}")

def start_monitoring(watch_folder, check_existing=True):
    """
    Start monitoring a folder for new video files
    
    Args:
        watch_folder (str): Path to the folder to monitor
        check_existing (bool): Whether to check for existing files
        
    Returns:
        bool: True if monitoring started successfully, False otherwise
    """
    global observer, is_monitoring, current_watch_folder, processed_files
    
    if is_monitoring:
        logger.warning(f"Already monitoring a folder: {current_watch_folder}")
        return False
        
    if not watch_folder:
        logger.error("No watch folder specified")
        return False
    
    # Normalize the path
    try:
        watch_folder = os.path.abspath(os.path.expanduser(watch_folder))
        logger.info(f"Normalized watch folder path: {watch_folder}")
    except Exception as e:
        logger.error(f"Error normalizing watch folder path: {e}")
        return False
        
    if not os.path.exists(watch_folder):
        logger.error(f"Watch folder does not exist: {watch_folder}")
        return False
    
    if not os.path.isdir(watch_folder):
        logger.error(f"Watch folder is not a directory: {watch_folder}")
        return False
    
    if not os.access(watch_folder, os.R_OK):
        logger.error(f"No read permission for watch folder: {watch_folder}")
        return False
    
    logger.info(f"Starting monitoring for folder: {watch_folder}")
    
    # Reset the processed files when starting new monitoring
    processed_files = set()
        
    try:
        # Set up watchdog observer
        event_handler = VideoEventHandler()
        observer = Observer()
        observer.schedule(event_handler, watch_folder, recursive=False)
        observer.start()
        
        is_monitoring = True
        current_watch_folder = watch_folder
        logger.info(f"Successfully started monitoring folder: {watch_folder}")
        
        # Check for existing files
        if check_existing and on_new_file_callback:
            logger.info(f"Scanning for existing video files in {watch_folder}")
            file_count = 0
            video_count = 0
            
            try:
                files = os.listdir(watch_folder)
                file_count = len(files)
                logger.info(f"Found {file_count} files in directory")
                
                for filename in files:
                    file_path = os.path.join(watch_folder, filename)
                    logger.info(f"Checking file: {file_path}")
                    
                    if os.path.isfile(file_path):
                        if is_video_file(file_path) and file_path not in processed_files:
                            if wait_for_file_stability(file_path):
                                video_count += 1
                                logger.info(f"Found existing stable video file: {file_path}")
                                processed_files.add(file_path)
                                try:
                                    on_new_file_callback(file_path)
                                except Exception as e:
                                    logger.error(f"Error processing existing file {file_path}: {e}")
                            else:
                                logger.warning(f"Skipping unstable video file: {file_path}")
                
                logger.info(f"Scanned {file_count} files, found {video_count} stable videos")
            except Exception as e:
                logger.error(f"Error scanning existing files: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error starting monitoring: {e}")
        return False

def stop_monitoring():
    """
    Stop monitoring for new video files
    
    Returns:
        bool: True if monitoring stopped successfully, False otherwise
    """
    global observer, is_monitoring, current_watch_folder
    
    if not is_monitoring:
        logger.warning("Not currently monitoring any folder")
        return True
        
    try:
        if observer:
            logger.info(f"Stopping folder monitoring for: {current_watch_folder}")
            observer.stop()
            observer.join()
            observer = None
            
        is_monitoring = False
        current_watch_folder = None
        logger.info("Successfully stopped monitoring")
        return True
    except Exception as e:
        logger.error(f"Error stopping monitoring: {e}")
        return False

def get_monitoring_status():
    """
    Get the current monitoring status
    
    Returns:
        bool: True if monitoring is active, False otherwise
    """
    return is_monitoring

def get_current_watch_folder():
    """
    Get the currently monitored folder path
    
    Returns:
        str: Path to the currently monitored folder, or None if not monitoring
    """
    return current_watch_folder