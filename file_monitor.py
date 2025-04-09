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
                
                # Wait a short time to ensure the file is completely written
                # This helps avoid incomplete file uploads
                time.sleep(3)
                
                # Call the callback function with the detected file
                if on_new_file_callback:
                    logger.info(f"Processing video file: {file_path}")
                    try:
                        on_new_file_callback(file_path)
                    except Exception as e:
                        logger.error(f"Error in callback for file {file_path}: {e}")
                else:
                    logger.error("No callback function registered for file processing")
            else:
                logger.info(f"Non-video file ignored: {file_path}")

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
    global observer, is_monitoring, current_watch_folder
    
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
                        if is_video_file(file_path):
                            video_count += 1
                            logger.info(f"Found existing video file: {file_path}")
                            try:
                                on_new_file_callback(file_path)
                            except Exception as e:
                                logger.error(f"Error processing existing file {file_path}: {e}")
                
                logger.info(f"Scanned {file_count} files, found {video_count} videos")
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