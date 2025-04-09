"""
Models for YouTube Auto Uploader
"""
import os
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('models')

class UploadTask:
    """
    Represents a video upload task
    
    Attributes:
        file_path (str): Path to the video file
        filename (str): Basename of the file
        file_size (int): Size of the file in bytes
        id (str): Unique identifier for the task
        status (str): Current status (pending, uploading, completed, error, cancelled)
        progress (int): Upload progress percentage (0-100)
        video_id (str): YouTube video ID after successful upload
        video_url (str): YouTube video URL after successful upload
        start_time (float): Timestamp when upload started
        end_time (float): Timestamp when upload completed
        error (str): Error message if upload failed
        cancel_requested (bool): Flag to indicate cancellation is requested
        delete_attempts (int): Number of attempts to delete the local file
        delete_success (bool): Whether file deletion was successful
    """
    def __init__(self, file_path):
        """Initialize a new upload task"""
        try:
            # Normalize the file path
            self.file_path = os.path.abspath(os.path.expanduser(file_path))
            
            # Extract just the filename (no path)
            self.filename = os.path.basename(self.file_path)
            
            # Get the file size
            try:
                self.file_size = os.path.getsize(self.file_path)
            except Exception as e:
                logger.error(f"Error getting file size for {self.file_path}: {e}")
                self.file_size = 0
                
            # Generate a unique ID based on timestamp and filename
            timestamp = int(time.time() * 1000)
            unique_suffix = hash(self.filename) % 10000  # Add some uniqueness based on filename
            self.id = f"{timestamp}_{unique_suffix}"
            
            # Initialize other attributes
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
            
            logger.info(f"Created upload task for {self.filename} with ID {self.id}")
        except Exception as e:
            logger.error(f"Error creating upload task: {e}")
            raise
    
    def to_dict(self):
        """Convert the task to a dictionary for API responses"""
        return {
            'id': self.id,
            'filename': self.filename,
            'file_path': self.file_path,  # Include full path for debugging
            'file_size': self.file_size,
            'status': self.status,
            'progress': self.progress,
            'video_id': self.video_id,
            'video_url': self.video_url,
            'error': self.error,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'delete_success': self.delete_success,
            'delete_attempts': self.delete_attempts
        }
    
    def mark_uploading(self):
        """Mark task as uploading"""
        self.status = "uploading"
        self.progress = 0
        self.start_time = time.time()
        logger.info(f"Task {self.id} ({self.filename}) marked as uploading")
        
    def mark_completed(self, video_id):
        """Mark task as completed"""
        self.video_id = video_id
        self.video_url = f"https://youtu.be/{video_id}"
        self.status = "completed"
        self.progress = 100
        self.end_time = time.time()
        logger.info(f"Task {self.id} ({self.filename}) marked as completed, video ID: {video_id}")
        
    def mark_error(self, error_message):
        """Mark task as error"""
        self.status = "error"
        self.error = error_message
        logger.error(f"Task {self.id} ({self.filename}) marked as error: {error_message}")
        
    def mark_cancelled(self):
        """Mark task as cancelled"""
        self.status = "cancelled"
        logger.info(f"Task {self.id} ({self.filename}) marked as cancelled")