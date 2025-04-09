# YouTube Auto Uploader

A tool for automatically uploading gameplay videos to YouTube from a watched folder.

## Features

- **Automatic Uploads**: Monitors a folder and automatically uploads new video files to YouTube
- **Customizable Metadata**: Set title templates, descriptions, tags, and privacy settings
- **Multiple API Projects**: Support for multiple YouTube API projects to overcome quota limits
- **Channel Selection**: Select which YouTube channel to upload to if you have multiple channels
- **Automatic File Management**: Option to automatically delete files after successful upload
- **Retry Mechanism**: Robust retry logic for handling network issues and upload failures
- **Modern Interface**: Clean, responsive UI with dark mode support

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/youtube-auto-uploader.git
   cd youtube-auto-uploader
   ```

2. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up a YouTube API project:
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project
   - Enable the YouTube Data API v3
   - Create OAuth credentials (Web application type)
   - Add `http://localhost:5000/oauth2callback` as an authorized redirect URI
   - Download the credentials JSON file to the `credentials` directory (will be created on first run)

## Usage

1. Start the application:
   ```
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

3. Follow the steps in the web interface:
   - Authenticate with your YouTube account
   - Select a folder to monitor
   - Configure upload settings
   - Start monitoring

## Project Structure

```
youtube_auto_uploader/
├── app.py                  # Main entry point and Flask app initialization
├── config.py               # Configuration management
├── models.py               # Data models (UploadTask)
├── youtube_api.py          # YouTube API integration and authentication
├── uploader.py             # Upload queue and file processing
├── file_monitor.py         # File system monitoring
├── routes/                 # API routes
│   ├── __init__.py
│   ├── main_routes.py      # Main page and UI routes
│   ├── api_routes.py       # API endpoints
│   └── auth_routes.py      # Authentication routes
├── utils/                  # Utility functions
│   ├── __init__.py
│   └── file_utils.py       # File operations utilities
├── static/                 # CSS, JavaScript, etc.
└── templates/              # HTML templates
    ├── index.html          # Main dashboard
    └── error.html          # Error page
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- YouTube Data API v3
- Flask web framework
- Watchdog for file system monitoring