"""
Models for YouTube Auto Uploader
"""
import os
import time
from datetime import datetime

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
    
    def to_dict(self):
        """Convert the task to a dictionary for API responses"""
        return {
            'id': self.id,
            'filename': self.filename,
            'file_size': self.file_size,
            'status': self.status,
            'progress': self.progress,
            'video_url': self.video_url,
            'error': self.error,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'delete_success': self.delete_success
        }
    
    def mark_uploading(self):
        """Mark task as uploading"""
        self.status = "uploading"
        self.progress = 0
        self.start_time = time.time()
        
    def mark_completed(self, video_id):
        """Mark task as completed"""
        self.video_id = video_id
        self.video_url = f"https://youtu.be/{video_id}"
        self.status = "completed"
        self.progress = 100
        self.end_time = time.time()
        
    def mark_error(self, error_message):
        """Mark task as error"""
        self.status = "error"
        self.error = error_message
        
    def mark_cancelled(self):
        """Mark task as cancelled"""
        self.status = "cancelled"
