"""
File utility functions for YouTube Auto Uploader
"""
import os
import shutil

def format_file_size(bytes):
    """
    Format file size in human-readable format
    
    Args:
        bytes (int): Size in bytes
        
    Returns:
        str: Human-readable file size
    """
    if bytes == 0:
        return '0 B'
    
    size_names = ('B', 'KB', 'MB', 'GB', 'TB')
    i = 0
    while bytes >= 1024 and i < len(size_names) - 1:
        bytes /= 1024
        i += 1
    
    return f"{bytes:.2f} {size_names[i]}"

def ensure_directory_exists(path):
    """
    Ensure that a directory exists, creating it if necessary
    
    Args:
        path (str): Directory path
        
    Returns:
        bool: True if directory exists or was created, False otherwise
    """
    if not path:
        return False
        
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        print(f"Error creating directory {path}: {e}")
        return False

def copy_file_safe(source, destination):
    """
    Safely copy a file to a new location
    
    Args:
        source (str): Source file path
        destination (str): Destination file path
        
    Returns:
        bool: True if copy was successful, False otherwise
    """
    try:
        # Ensure destination directory exists
        dest_dir = os.path.dirname(destination)
        ensure_directory_exists(dest_dir)
        
        # Copy file
        shutil.copy2(source, destination)
        return True
    except Exception as e:
        print(f"Error copying file from {source} to {destination}: {e}")
        return False

def delete_file_safe(path):
    """
    Safely delete a file
    
    Args:
        path (str): File path
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        if os.path.exists(path):
            os.remove(path)
            return True
        return False
    except Exception as e:
        print(f"Error deleting file {path}: {e}")
        return False
