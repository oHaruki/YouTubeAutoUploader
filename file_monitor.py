"""
File system monitoring functionality for YouTube Auto Uploader
"""
import os
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Record of active monitoring state and observer instance
is_monitoring = False
observer = None

# Function to be called when a new file is detected
# Will be set by the uploader module
on_new_file_callback = None

class VideoEventHandler(FileSystemEventHandler):
    """
    Watchdog handler for detecting new video files
    """
    def on_created(self, event):
        if not event.is_directory and is_video_file(event.src_path):
            # Wait a short time to ensure the file is completely written
            time.sleep(3)
            
            # Call the callback function with the detected file
            if on_new_file_callback:
                on_new_file_callback(event.src_path)

def is_video_file(file_path):
    """
    Check if a file is a video file based on its extension
    
    Args:
        file_path (str): Path to the file
        
    Returns:
        bool: True if the file is a video file, False otherwise
    """
    video_extensions = ['.mp4', '.avi', '.mov', '.wmv', '.mkv', '.flv']
    return any(file_path.lower().endswith(ext) for ext in video_extensions)

def register_callback(callback_function):
    """
    Register a callback function to be called when a new file is detected
    
    Args:
        callback_function (function): Function to call with the file path
    """
    global on_new_file_callback
    on_new_file_callback = callback_function

def start_monitoring(watch_folder, check_existing=True):
    """
    Start monitoring a folder for new video files
    
    Args:
        watch_folder (str): Path to the folder to monitor
        check_existing (bool): Whether to check for existing files
        
    Returns:
        bool: True if monitoring started successfully, False otherwise
    """
    global observer, is_monitoring
    
    if is_monitoring or not watch_folder:
        return False
        
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
        if check_existing and on_new_file_callback:
            for filename in os.listdir(watch_folder):
                file_path = os.path.join(watch_folder, filename)
                if is_video_file(file_path) and os.path.isfile(file_path):
                    on_new_file_callback(file_path)
        
        return True
    except Exception as e:
        print(f"Error starting monitoring: {e}")
        return False

def stop_monitoring():
    """
    Stop monitoring for new video files
    
    Returns:
        bool: True if monitoring stopped successfully, False otherwise
    """
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

def get_monitoring_status():
    """
    Get the current monitoring status
    
    Returns:
        bool: True if monitoring is active, False otherwise
    """
    return is_monitoring
