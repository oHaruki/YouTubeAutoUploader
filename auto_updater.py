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
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('auto_updater')

# GitHub repository information
GITHUB_REPO = "oHaruki/YouTubeAutoUploader"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
# Fallback URL if no asset is available
GITHUB_ZIPBALL_URL = f"https://api.github.com/repos/{GITHUB_REPO}/zipball/latest"
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

def version_is_newer(latest, current):
    """
    Compare version strings directly
    
    Args:
        latest (str): Latest version string
        current (str): Current version string
        
    Returns:
        bool: True if latest is newer than current
    """
    try:
        # Convert to list of integers for comparison
        latest_parts = [int(x) for x in latest.split('.')]
        current_parts = [int(x) for x in current.split('.')]
        
        # Pad with zeros if needed
        while len(latest_parts) < 3:
            latest_parts.append(0)
        while len(current_parts) < 3:
            current_parts.append(0)
        
        # Compare major, minor, patch
        for l, c in zip(latest_parts, current_parts):
            if l > c:
                return True
            elif l < c:
                return False
        
        # If we get here, versions are equal
        return False
    except Exception as e:
        logger.error(f"Error comparing versions: {e}")
        logger.error(traceback.format_exc())
        # Fallback to string comparison as last resort
        return latest.strip() > current.strip()

def check_for_update():
    """
    Check if a newer version is available on GitHub
    
    Returns:
        tuple: (update_available, latest_version, download_url, release_notes)
    """
    current_version = get_current_version()
    
    try:
        logger.info(f"Checking for updates (current version: {current_version})")
        
        # Make request to GitHub API
        logger.info(f"Requesting: {GITHUB_API_URL}")
        response = requests.get(GITHUB_API_URL, timeout=10)
        logger.info(f"Response status: {response.status_code}")
        response.raise_for_status()
        
        # Parse the GitHub response
        release_data = response.json()
        
        # Get the tag name (version) from the release
        tag_name = release_data.get("tag_name", "")
        logger.info(f"Release tag name: {tag_name}")
        
        # Remove 'v' prefix if present
        latest_version = tag_name.lstrip('v')
        logger.info(f"Latest GitHub version: {latest_version}")
        
        # Find the ZIP asset
        download_url = None
        assets = release_data.get("assets", [])
        logger.info(f"Found {len(assets)} assets in the release")
        
        for asset in assets:
            asset_name = asset.get("name", "")
            logger.info(f"Found asset: {asset_name}")
            if asset_name.endswith(".zip"):
                download_url = asset.get("browser_download_url")
                logger.info(f"Found ZIP asset URL: {download_url}")
                break
        
        # If no ZIP asset found, use the source code ZIP
        if not download_url:
            logger.info("No ZIP asset found, using source code ZIP fallback")
            download_url = release_data.get("zipball_url")
            logger.info(f"Using zipball URL: {download_url}")
        
        # If still no download URL, use the repository zipball as last resort
        if not download_url:
            logger.info("No zipball URL found, using repository zipball as last resort")
            download_url = GITHUB_ZIPBALL_URL
        
        # Get release notes
        release_notes = release_data.get("body", "No release notes available.")
        
        # Compare versions
        if latest_version and download_url:
            is_newer = version_is_newer(latest_version, current_version)
            logger.info(f"Version comparison result: {is_newer} (latest={latest_version}, current={current_version})")
            
            # For debugging
            print(f"DEBUG: Version comparison: {latest_version} > {current_version} = {is_newer}")
            
            if is_newer:
                logger.info(f"New version available: {latest_version}")
                return (True, latest_version, download_url, release_notes)
            else:
                logger.info("Current version is up to date")
        else:
            if not latest_version:
                logger.warning("Could not determine latest version from GitHub")
            if not download_url:
                logger.warning("No download URL found for update")
        
        # If we get here, no update is available or needed
        logger.info("No updates available")
        return (False, latest_version, None, None)
            
    except Exception as e:
        logger.error(f"Error checking for updates: {e}")
        logger.error(traceback.format_exc())
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
        logger.error(traceback.format_exc())
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
        
        # For the main script, use the current working directory
        if not current_dir:
            current_dir = os.getcwd()
        
        logger.info(f"Current directory: {current_dir}")
        logger.info(f"Temp directory: {temp_dir}")
        
        # Clear previous temp directory if it exists
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        os.makedirs(temp_dir)
        
        # Extract the update
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        # Find the root directory in the extracted files
        extracted_items = os.listdir(temp_dir)
        logger.info(f"Extracted items: {extracted_items}")
        
        # Handle GitHub's zipball format which includes a directory with the repo name
        extract_root = temp_dir
        for item in extracted_items:
            full_path = os.path.join(temp_dir, item)
            if os.path.isdir(full_path) and (GITHUB_REPO.split("/")[0] in item or "YouTubeAutoUploader" in item):
                extract_root = full_path
                logger.info(f"Found GitHub repo directory: {extract_root}")
                break
        
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
        logger.error(traceback.format_exc())
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

def force_update_to_version(version):
    """
    Force update to a specific version for testing
    
    Args:
        version (str): Version to update to
    """
    logger.info(f"Forcing update to version {version}")
    update_version_file(version)
    
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
        logger.error(traceback.format_exc())
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
    
    # Force downgrade to 1.0.0 for testing if needed
    if len(sys.argv) > 1 and sys.argv[1] == "--downgrade":
        force_update_to_version("1.0.0")
        print("Forced downgrade to version 1.0.0 for testing")
    
    update_available, latest_version, download_url, release_notes = check_for_update()
    print(f"Update available: {update_available}")
    print(f"Latest version from GitHub: {latest_version}")
    print(f"Download URL: {download_url}")
    print(f"Release notes: {release_notes}")
    
    if update_available:
        if input("Download and apply update? (y/n): ").lower() == 'y':
            zip_path = download_update(download_url)
            if zip_path:
                apply_update(zip_path, latest_version)
                print("Update applied. Restart application to use the new version.")