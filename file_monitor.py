"""
File system monitoring functionality for YouTube Auto Uploader - Single Scan Version
"""
import os
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('file_monitor')

# Record of active monitoring state
is_monitoring = False
current_watch_folder = None

# Function to be called when a video file is found
# Will be set by the uploader module
on_new_file_callback = None

# Track files we've already seen to avoid duplicate processing
processed_files = set()

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
    Register a callback function to be called when a video file is found
    
    Args:
        callback_function (function): Function to call with the file path
    """
    global on_new_file_callback
    on_new_file_callback = callback_function
    logger.info(f"Callback function registered: {callback_function.__name__ if callback_function else None}")

def scan_folder_for_videos(folder_path):
    """
    Scan a folder for video files and process them
    
    Args:
        folder_path (str): Path to scan for videos
        
    Returns:
        int: Number of video files found and processed
    """
    global processed_files
    
    if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        logger.error(f"Invalid folder path for scanning: {folder_path}")
        return 0
    
    logger.info(f"Scanning for video files in {folder_path}")
    
    file_count = 0
    video_count = 0
    
    try:
        files = os.listdir(folder_path)
        file_count = len(files)
        logger.info(f"Found {file_count} files in directory")
        
        for filename in files:
            file_path = os.path.join(folder_path, filename)
            logger.info(f"Checking file: {file_path}")
            
            if os.path.isfile(file_path):
                if is_video_file(file_path) and file_path not in processed_files:
                    if wait_for_file_stability(file_path, max_wait_time=60):
                        # Only add to processed files if it's stable
                        video_count += 1
                        logger.info(f"Found stable video file: {file_path}")
                        processed_files.add(file_path)
                        
                        if on_new_file_callback:
                            try:
                                on_new_file_callback(file_path)
                            except Exception as e:
                                logger.error(f"Error processing file {file_path}: {e}")
                        else:
                            logger.error("No callback function registered for file processing")
                    else:
                        logger.warning(f"Skipping unstable video file: {file_path}")
        
        logger.info(f"Scanned {file_count} files, found {video_count} stable videos")
        return video_count
        
    except Exception as e:
        logger.error(f"Error scanning folder: {e}")
        return 0

def start_monitoring(watch_folder, check_existing=True):
    """
    Start monitoring a folder for video files
    
    Args:
        watch_folder (str): Path to the folder to monitor
        check_existing (bool): Whether to check for existing files
        
    Returns:
        bool: True if monitoring started successfully, False otherwise
    """
    global is_monitoring, current_watch_folder, processed_files
    
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
    
    # Mark as monitoring and set the current watch folder
    is_monitoring = True
    current_watch_folder = watch_folder
    
    # Scan for existing files if requested
    if check_existing and on_new_file_callback:
        scan_count = scan_folder_for_videos(watch_folder)
        logger.info(f"Initial scan complete: {scan_count} videos processed")
    
    logger.info(f"Successfully started monitoring folder: {watch_folder}")
    return True

def stop_monitoring():
    """
    Stop monitoring for video files
    
    Returns:
        bool: True if monitoring stopped successfully, False otherwise
    """
    global is_monitoring, current_watch_folder
    
    if not is_monitoring:
        logger.warning("Not currently monitoring any folder")
        return True
    
    # Reset state
    is_monitoring = False
    current_watch_folder = None
    logger.info("Successfully stopped monitoring")
    return True

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

def manual_scan():
    """
    Manually trigger a scan of the current watch folder
    
    Returns:
        int: Number of new videos found and processed, or -1 if not monitoring
    """
    if not is_monitoring or not current_watch_folder:
        logger.warning("Not currently monitoring any folder")
        return -1
    
    return scan_folder_for_videos(current_watch_folder)