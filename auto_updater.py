"""
Auto-updater for YouTube Auto Uploader
Checks for updates on GitHub and applies them automatically.
"""
import os
import sys
import json
import logging
import time
import tempfile
import shutil
import zipfile
import subprocess
import requests
from packaging import version

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('auto_updater')

# GitHub repository information
GITHUB_REPO = "oHaruki/YouTubeAutoUploader"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
VERSION_FILE = "version.json"

# Files and directories to exclude during update
UPDATE_EXCLUDE = [
    "config.json",
    "version.json",
    "credentials",
    "tokens",
    "logs",
    "__pycache__",
    ".git",
    ".gitignore",
    "temp",
    "venv",
    "env",
    ".venv"
]

def get_current_version():
    """
    Get the current installed version
    
    Returns:
        str: Current version string or "0.0.0" if not found
    """
    if not os.path.exists(VERSION_FILE):
        # Create initial version file if it doesn't exist
        initial_version = {
            "version": "1.0.0",
            "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "auto_update": True
        }
        
        with open(VERSION_FILE, 'w') as f:
            json.dump(initial_version, f, indent=4)
            
        return "1.0.0"
    
    try:
        with open(VERSION_FILE, 'r') as f:
            version_data = json.load(f)
            return version_data.get("version", "0.0.0")
    except Exception as e:
        logger.error(f"Error reading version file: {e}")
        return "0.0.0"

def is_auto_update_enabled():
    """
    Check if auto-update is enabled in settings
    
    Returns:
        bool: True if auto-update is enabled, False otherwise
    """
    if not os.path.exists(VERSION_FILE):
        return True
        
    try:
        with open(VERSION_FILE, 'r') as f:
            version_data = json.load(f)
            return version_data.get("auto_update", True)
    except Exception as e:
        logger.error(f"Error reading version file auto-update setting: {e}")
        return True

def set_auto_update_enabled(enabled=True):
    """
    Set the auto-update enabled setting
    
    Args:
        enabled (bool): Whether auto-update should be enabled
    """
    if not os.path.exists(VERSION_FILE):
        # Create version file with the setting
        version_data = {
            "version": "1.0.0",
            "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "auto_update": enabled
        }
    else:
        # Update existing version file
        try:
            with open(VERSION_FILE, 'r') as f:
                version_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading version file: {e}")
            version_data = {
                "version": "1.0.0",
                "build_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
    
    # Update the auto-update setting
    version_data["auto_update"] = enabled
    
    # Save the updated version file
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_data, f, indent=4)
    except Exception as e:
        logger.error(f"Error updating version file: {e}")

def check_for_update():
    """
    Check if a newer version is available on GitHub
    
    Returns:
        tuple: (update_available, latest_version, download_url, release_notes)
    """
    current_version = get_current_version()
    
    try:
        logger.info(f"Checking for updates (current version: {current_version})")
        response = requests.get(GITHUB_API_URL, timeout=10)
        response.raise_for_status()
        
        release_data = response.json()
        latest_version = release_data.get("tag_name", "").lstrip('v')
        download_url = None
        
        # Find the ZIP asset
        for asset in release_data.get("assets", []):
            if asset.get("name", "").endswith(".zip"):
                download_url = asset.get("browser_download_url")
                break
        
        release_notes = release_data.get("body", "No release notes available.")
        
        # Compare versions
        if latest_version and download_url and version.parse(latest_version) > version.parse(current_version):
            logger.info(f"New version available: {latest_version}")
            return (True, latest_version, download_url, release_notes)
        else:
            logger.info("No updates available")
            return (False, latest_version, None, None)
            
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        return (False, None, None, None)

def download_update(download_url):
    """
    Download the update package
    
    Args:
        download_url (str): URL to download the update from
        
    Returns:
        str: Path to the downloaded update file, or None if download failed
    """
    try:
        logger.info(f"Downloading update from {download_url}")
        
        temp_dir = tempfile.gettempdir()
        zip_path = os.path.join(temp_dir, "youtube_auto_uploader_update.zip")
        
        # Download the file
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Update downloaded to {zip_path}")
        return zip_path
    except Exception as e:
        logger.error(f"Error downloading update: {e}")
        return None

def apply_update(zip_path, latest_version):
    """
    Apply the downloaded update
    
    Args:
        zip_path (str): Path to the downloaded update ZIP file
        latest_version (str): Version string of the update
        
    Returns:
        bool: True if update was successful, False otherwise
    """
    try:
        logger.info(f"Applying update to version {latest_version}")
        
        temp_dir = os.path.join(tempfile.gettempdir(), "youtube_auto_uploader_update")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Clear previous temp directory if it exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        os.makedirs(temp_dir)
        
        # Extract the update
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the root directory in the extracted files
        extracted_dirs = [d for d in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, d))]
        if extracted_dirs:
            extract_root = os.path.join(temp_dir, extracted_dirs[0])
        else:
            extract_root = temp_dir
        
        # Copy the update files to the current directory
        for item in os.listdir(extract_root):
            source = os.path.join(extract_root, item)
            destination = os.path.join(current_dir, item)
            
            # Skip excluded items
            if item in UPDATE_EXCLUDE:
                logger.info(f"Skipping excluded item: {item}")
                continue
                
            # Copy files and directories
            if os.path.isdir(source):
                if os.path.exists(destination):
                    # Update existing directory
                    for root, dirs, files in os.walk(source):
                        # Get the relative path from source root
                        rel_path = os.path.relpath(root, source)
                        
                        for file in files:
                            # Skip updating files in excluded directories
                            if any(excluded in os.path.join(rel_path, file) for excluded in UPDATE_EXCLUDE):
                                continue
                                
                            src_file = os.path.join(root, file)
                            dst_file = os.path.join(destination, rel_path, file)
                            
                            # Ensure destination directory exists
                            dst_dir = os.path.dirname(dst_file)
                            if not os.path.exists(dst_dir):
                                os.makedirs(dst_dir)
                                
                            # Copy the file
                            shutil.copy2(src_file, dst_file)
                else:
                    # Copy new directory
                    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*UPDATE_EXCLUDE))
            else:
                # Copy file
                shutil.copy2(source, destination)
        
        # Update version file
        update_version_file(latest_version)
        
        # Clean up
        try:
            os.remove(zip_path)
            shutil.rmtree(temp_dir)
            logger.info("Update cleanup completed")
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")
        
        logger.info("Update applied successfully")
        return True
    except Exception as e:
        logger.error(f"Error applying update: {e}")
        return False

def update_version_file(new_version):
    """
    Update the version file with the new version
    
    Args:
        new_version (str): New version string
    """
    version_data = {
        "version": new_version,
        "build_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "auto_update": is_auto_update_enabled()
    }
    
    try:
        with open(VERSION_FILE, 'w') as f:
            json.dump(version_data, f, indent=4)
        logger.info(f"Version file updated to {new_version}")
    except Exception as e:
        logger.error(f"Error updating version file: {e}")

def run_update():
    """
    Run the update process
    
    Returns:
        tuple: (updated, new_version, error_message)
    """
    if not is_auto_update_enabled():
        logger.info("Auto-update is disabled")
        return (False, None, "Auto-update is disabled")
    
    try:
        update_available, latest_version, download_url, release_notes = check_for_update()
        
        if not update_available:
            return (False, None, "No updates available")
        
        zip_path = download_update(download_url)
        if not zip_path:
            return (False, None, "Failed to download update")
        
        success = apply_update(zip_path, latest_version)
        if not success:
            return (False, None, "Failed to apply update")
        
        return (True, latest_version, None)
    except Exception as e:
        logger.error(f"Update process error: {e}")
        return (False, None, str(e))

def restart_application():
    """
    Restart the application after update
    """
    logger.info("Restarting application...")
    
    try:
        if getattr(sys, 'frozen', False):
            # Running as bundled executable
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            # Running as script
            args = [sys.executable] + sys.argv
            subprocess.Popen(args)
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error restarting application: {e}")

if __name__ == "__main__":
    # Manual test
    print(f"Current version: {get_current_version()}")
    print(f"Auto-update enabled: {is_auto_update_enabled()}")
    
    update_available, latest_version, download_url, release_notes = check_for_update()
    print(f"Update available: {update_available}")
    if update_available:
        print(f"Latest version: {latest_version}")
        print(f"Download URL: {download_url}")
        print(f"Release notes: {release_notes}")
        
        if input("Download and apply update? (y/n): ").lower() == 'y':
            zip_path = download_update(download_url)
            if zip_path:
                apply_update(zip_path, latest_version)
                print("Update applied. Restart application to use the new version.")