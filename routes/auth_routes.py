"""
Authentication routes for YouTube Auto Uploader
"""
import os
import pickle
from flask import request, redirect, url_for, render_template
import google.oauth2.credentials
import google_auth_oauthlib.flow
from google.auth.transport.requests import Request

from . import auth_bp
import youtube_api

@auth_bp.route('/auth')
def auth():
    """Initialize OAuth flow for YouTube authentication"""
    # Check if we have any projects
    projects = youtube_api.get_available_api_projects()
    
    if not projects:
        return render_template('error.html', 
                               error="No API projects found",
                               message="Please add an API project first")
    
    # Default to first project if none specified
    project = projects[0]
    
    # Create flow instance
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        project['file_path'], youtube_api.SCOPES)
    
    # Set the redirect URI to the /oauth2callback endpoint
    flow.redirect_uri = url_for('auth.oauth2callback', _external=True)
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Redirect the user to the authorization URL
    return redirect(auth_url)

@auth_bp.route('/oauth2callback')
def oauth2callback():
    """Callback endpoint for OAuth flow"""
    global youtube
    
    # Default authentication - use the first project
    projects = youtube_api.get_available_api_projects()
    if not projects:
        return render_template('error.html', 
                               error="No API projects found",
                               message="Please add an API project first")
                               
    project = projects[0]
    
    # Create flow instance
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        project['file_path'], youtube_api.SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('auth.oauth2callback', _external=True)
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    # Store credentials
    credentials = flow.credentials
    with open(project['token_path'], 'wb') as token:
        pickle.dump(credentials, token)
    
    # Build the service
    client_builder = youtube_api.get_youtube_api_with_retry()
    youtube = client_builder(youtube_api.API_SERVICE_NAME, youtube_api.API_VERSION, credentials=credentials)
    youtube_api.youtube_clients[project['id']] = youtube
    youtube_api.active_client_id = project['id']
    youtube_api.youtube = youtube
    
    return redirect('/')

@auth_bp.route('/auth/project/<project_id>')
def auth_project(project_id):
    """Authenticate a specific API project"""
    projects = youtube_api.get_available_api_projects()
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    
    if not selected_project:
        return render_template('error.html', 
                               error=f"Project '{project_id}' not found",
                               message="Please check your credentials directory")
    
    # Create flow instance for this project
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        selected_project['file_path'], youtube_api.SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('auth.oauth2callback_project', project_id=project_id, _external=True)
    
    # Generate authorization URL
    auth_url, _ = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    
    # Redirect the user to the authorization URL
    return redirect(auth_url)

@auth_bp.route('/oauth2callback/project/<project_id>')
def oauth2callback_project(project_id):
    """OAuth callback for a specific project"""
    projects = youtube_api.get_available_api_projects()
    selected_project = next((p for p in projects if p['id'] == project_id), None)
    
    if not selected_project:
        return render_template('error.html', 
                               error=f"Project '{project_id}' not found",
                               message="Authorization failed")
    
    # Create flow instance for this project
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        selected_project['file_path'], youtube_api.SCOPES)
    
    # Set the redirect URI
    flow.redirect_uri = url_for('auth.oauth2callback_project', project_id=project_id, _external=True)
    
    # Use the authorization server's response to fetch the OAuth 2.0 tokens
    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)
    
    # Store credentials
    credentials = flow.credentials
    with open(selected_project['token_path'], 'wb') as token:
        pickle.dump(credentials, token)
    
    # Build and store the service
    client_builder = youtube_api.get_youtube_api_with_retry()
    client = client_builder(youtube_api.API_SERVICE_NAME, youtube_api.API_VERSION, credentials=credentials)
    youtube_api.youtube_clients[project_id] = client
    
    # Set as active client
    youtube_api.youtube = client
    youtube_api.active_client_id = project_id
    
    return redirect('/')
