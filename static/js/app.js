// Initialize variables
let currentPath = '';
let uploadQueue = [];
let isMonitoring = false;
let isAuthenticated = false;
let uploadLimitReached = false;
let uploadLimitResetTime = null;
let currentTheme = "light";
let refreshInterval;
let processedTaskIds = new Set(); // Track which tasks we've already displayed

// DOM Ready
document.addEventListener('DOMContentLoaded', function() {
    console.log("App initialization started");
    
    // Get initial state from the page
    isMonitoring = document.getElementById('statusIndicator').innerText.includes('Monitoring');
    isAuthenticated = !document.getElementById('statusIndicator').innerText.includes('Not Authenticated');
    currentTheme = document.documentElement.getAttribute('data-bs-theme') || 'light';
    
    console.log(`Initial state - Monitoring: ${isMonitoring}, Authenticated: ${isAuthenticated}`);
    
    // Check for upload limit
    const limitResetTimeEl = document.getElementById('limitResetTime');
    if (limitResetTimeEl) {
        uploadLimitReached = true;
        const timeData = limitResetTimeEl.getAttribute('data-time');
        if (timeData) {
            uploadLimitResetTime = new Date(timeData);
            console.log(`Upload limit reached, reset time: ${uploadLimitResetTime}`);
        }
    }
    
    // Setup event listeners
    document.getElementById('startMonitoringBtn').addEventListener('click', startMonitoring);
    document.getElementById('stopMonitoringBtn').addEventListener('click', stopMonitoring);
    document.getElementById('clearCompletedBtn').addEventListener('click', clearCompletedUploads);
    document.getElementById('saveSettingsBtn').addEventListener('click', saveSettings);
    document.getElementById('themeToggleBtn').addEventListener('click', toggleTheme);
    
    // Set up API projects tab event listeners
    document.getElementById('api-projects-tab').addEventListener('shown.bs.tab', function (e) {
        loadApiProjects();
    });

    document.getElementById('uploadProjectForm').addEventListener('submit', function(e) {
        e.preventDefault();
        uploadApiProject();
    });
    
    // Start refresh interval for queue - more frequent updates
    refreshInterval = setInterval(refreshQueue, 1000); // Changed from 2000 to 1000ms
    refreshQueue(); // Immediate first refresh
    
    // Update upload limit timer if needed
    if (uploadLimitReached && uploadLimitResetTime) {
        updateUploadLimitTimer();
        setInterval(updateUploadLimitTimer, 1000);
    }
    
    // Load channels when the settings tab is shown
    document.getElementById('settings-tab').addEventListener('shown.bs.tab', function (e) {
        loadChannels();
    });
    
    console.log("App initialized successfully");
});

// Theme toggle functionality
function toggleTheme() {
    // Toggle theme
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    
    // Update document attribute
    document.documentElement.setAttribute('data-bs-theme', newTheme);
    
    // Update button icon
    const themeIcon = document.getElementById('themeToggleBtn').querySelector('i');
    if (newTheme === 'dark') {
        themeIcon.className = 'bi bi-sun-fill';
    } else {
        themeIcon.className = 'bi bi-moon-fill';
    }
    
    // Save preference to server
    fetch('/api/theme', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ theme: newTheme })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            currentTheme = newTheme;
            // Store in localStorage for error pages
            localStorage.setItem('theme', newTheme);
        }
    })
    .catch(error => console.error('Error setting theme:', error));
}

// Queue management
function refreshQueue() {
    fetch('/api/queue')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Check if the queue has changed
                const hasChanged = JSON.stringify(uploadQueue) !== JSON.stringify(data.queue);
                
                uploadQueue = data.queue;
                const newMonitoringState = data.is_monitoring;
                
                // Check if monitoring state changed
                if (isMonitoring !== newMonitoringState) {
                    console.log(`Monitoring state changed: ${isMonitoring} -> ${newMonitoringState}`);
                    isMonitoring = newMonitoringState;
                    updateMonitoringButtons();
                    updateStatusIndicator();
                }
                
                uploadLimitReached = data.upload_limit_reached;
                
                if (data.upload_limit_reset_time) {
                    uploadLimitResetTime = new Date(data.upload_limit_reset_time);
                }
                
                if (hasChanged) {
                    console.log("Queue updated, refreshing UI");
                    updateQueueUI();
                }
            }
        })
        .catch(error => console.error('Error refreshing queue:', error));
}

function updateQueueUI() {
    const container = document.getElementById('uploadItems');
    const emptyMessage = document.getElementById('emptyQueueMessage');
    const statsElement = document.getElementById('queueStats');
    
    // Clear existing items
    container.innerHTML = '';
    
    if (uploadQueue.length === 0) {
        emptyMessage.classList.remove('d-none');
        statsElement.classList.add('d-none');
        // Reset processed task IDs when queue is empty
        processedTaskIds.clear();
        return;
    }
    
    emptyMessage.classList.add('d-none');
    statsElement.classList.remove('d-none');
    
    // Count stats
    const completed = uploadQueue.filter(task => task.status === 'completed').length;
    const pending = uploadQueue.filter(task => task.status === 'pending').length;
    const uploading = uploadQueue.filter(task => task.status === 'uploading').length;
    const failed = uploadQueue.filter(task => task.status === 'error' || task.status === 'cancelled').length;
    
    document.getElementById('statsText').textContent = 
        `Uploads: ${completed} completed, ${pending} pending, ${uploading} uploading, ${failed} failed`;
    
    // Add upload items
    uploadQueue.forEach(task => {
        const itemEl = document.createElement('div');
        // Only apply fade-in animation to new items
        const isNewTask = !processedTaskIds.has(task.id);
        itemEl.className = `upload-item p-3 mb-3 ${isNewTask ? 'fade-in' : ''}`;
        itemEl.id = `task-${task.id}`;
        
        // Add this task ID to our processed set
        processedTaskIds.add(task.id);
        
        let statusClass = '';
        let statusIcon = '';
        let actionButton = '';
        
        switch(task.status) {
            case 'completed':
                statusClass = 'text-success';
                statusIcon = '<i class="bi bi-check-circle-fill"></i>';
                actionButton = `<a href="${task.video_url}" target="_blank" class="btn btn-sm btn-outline-primary"><i class="bi bi-youtube"></i> View</a>`;
                break;
            case 'uploading':
                statusClass = 'text-primary';
                statusIcon = '<div class="loader"></div>';
                actionButton = `<button class="btn btn-sm btn-outline-danger" onclick="cancelTask('${task.id}')"><i class="bi bi-x-circle"></i> Cancel</button>`;
                break;
            case 'pending':
                statusClass = 'text-secondary';
                statusIcon = '<i class="bi bi-hourglass"></i>';
                actionButton = `<button class="btn btn-sm btn-outline-danger" onclick="cancelTask('${task.id}')"><i class="bi bi-x-circle"></i> Cancel</button>`;
                break;
            case 'error':
                statusClass = 'text-danger';
                statusIcon = '<i class="bi bi-exclamation-circle-fill"></i>';
                
                // Create a tooltip for the error details
                const errorMessage = task.error || 'Unknown error';
                actionButton = `
                    <button class="btn btn-sm btn-outline-secondary" 
                            data-bs-toggle="tooltip" 
                            data-bs-placement="top" 
                            title="${errorMessage}">
                        <i class="bi bi-info-circle"></i> Details
                    </button>`;
                break;
            case 'cancelled':
                statusClass = 'text-muted';
                statusIcon = '<i class="bi bi-x-circle-fill"></i>';
                actionButton = '';
                break;
        }
        
        const progressBar = task.status === 'uploading' ? 
            `<div class="progress">
                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                    role="progressbar" 
                    style="width: ${task.progress}%" 
                    aria-valuenow="${task.progress}" 
                    aria-valuemin="0" 
                    aria-valuemax="100"></div>
            </div>` : '';
        
        const fileSize = formatFileSize(task.file_size);
        
        const deleteStatus = task.status === 'completed' ? 
            `<div class="small ${task.delete_success ? 'text-success' : 'text-warning'}">
                ${task.delete_success ? '<i class="bi bi-trash-fill me-1"></i> File deleted' : '<i class="bi bi-arrow-repeat me-1"></i> Attempting to delete file...'}
            </div>` : '';
        
        itemEl.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <span class="${statusClass} me-3 fs-4">${statusIcon}</span>
                    <div>
                        <div class="fw-bold">${task.filename}</div>
                        <div class="small text-muted">${fileSize}</div>
                        ${deleteStatus}
                    </div>
                </div>
                <div class="d-flex align-items-center">
                    <span class="me-3 ${statusClass} fw-semibold">${capitalizeFirstLetter(task.status)}</span>
                    ${actionButton}
                </div>
            </div>
            ${progressBar}
        `;
        
        container.appendChild(itemEl);
        
        // Initialize tooltips
        if (task.status === 'error') {
            const tooltipTriggerList = [].slice.call(itemEl.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    });
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function capitalizeFirstLetter(string) {
    return string.charAt(0).toUpperCase() + string.slice(1);
}

function cancelTask(taskId) {
    console.log(`Cancelling task: ${taskId}`);
    fetch(`/api/task/${taskId}/cancel`, {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`Task ${taskId} cancelled successfully`);
            refreshQueue();
            showToast('Success', 'Task cancelled successfully', 'success');
        } else {
            console.error(`Failed to cancel task ${taskId}: ${data.error}`);
            showToast('Error', `Failed to cancel task: ${data.error || 'Unknown error'}`, 'danger');
        }
    })
    .catch(error => {
        console.error('Error cancelling task:', error);
        showToast('Error', 'Error cancelling task', 'danger');
    });
}

function clearCompletedUploads() {
    console.log("Clearing completed uploads");
    fetch('/api/queue/clear-completed', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log("Completed uploads cleared successfully");
            refreshQueue();
            showToast('Success', 'Completed uploads cleared', 'success');
        } else {
            console.error(`Failed to clear completed uploads: ${data.error}`);
            showToast('Error', `Failed to clear completed uploads: ${data.error || 'Unknown error'}`, 'danger');
        }
    })
    .catch(error => {
        console.error('Error clearing completed uploads:', error);
        showToast('Error', 'Error clearing completed uploads', 'danger');
    });
}

// Monitoring controls
function startMonitoring() {
    console.log("Starting monitoring");
    
    // Show loading indicator on the button
    const startBtn = document.getElementById('startMonitoringBtn');
    const originalText = startBtn.innerHTML;
    startBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Starting...';
    startBtn.disabled = true;
    
    fetch('/api/monitor/start', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        startBtn.innerHTML = originalText;
        
        if (data.success) {
            console.log("Monitoring started successfully");
            isMonitoring = true;
            updateMonitoringButtons();
            updateStatusIndicator();
            
            // Force immediate queue refresh
            refreshQueue();
            
            showToast('Success', 'Started monitoring folder for videos', 'success');
        } else {
            console.error(`Failed to start monitoring: ${data.error}`);
            startBtn.disabled = false;
            showToast('Error', 'Failed to start monitoring: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        startBtn.innerHTML = originalText;
        startBtn.disabled = false;
        console.error('Error starting monitoring:', error);
        showToast('Error', 'Error starting monitoring. Check console for details.', 'danger');
    });
}

function stopMonitoring() {
    console.log("Stopping monitoring");
    
    // Show loading indicator
    const stopBtn = document.getElementById('stopMonitoringBtn');
    const originalText = stopBtn.innerHTML;
    stopBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Stopping...';
    stopBtn.disabled = true;
    
    fetch('/api/monitor/stop', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        stopBtn.innerHTML = originalText;
        stopBtn.disabled = false;
        
        if (data.success) {
            console.log("Monitoring stopped successfully");
            isMonitoring = false;
            updateMonitoringButtons();
            updateStatusIndicator();
            
            // Force immediate queue refresh
            refreshQueue();
            
            showToast('Success', 'Stopped monitoring folder', 'success');
        } else {
            console.error(`Failed to stop monitoring: ${data.error}`);
            showToast('Error', 'Failed to stop monitoring: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        stopBtn.innerHTML = originalText;
        stopBtn.disabled = false;
        console.error('Error stopping monitoring:', error);
        showToast('Error', 'Error stopping monitoring. Check console for details.', 'danger');
    });
}

function updateMonitoringButtons() {
    const startBtn = document.getElementById('startMonitoringBtn');
    const stopBtn = document.getElementById('stopMonitoringBtn');
    
    if (isMonitoring) {
        startBtn.disabled = true;
        stopBtn.disabled = false;
    } else {
        startBtn.disabled = !isAuthenticated;
        stopBtn.disabled = true;
    }
    
    updateStatusIndicator();
}

function updateStatusIndicator() {
    const statusIndicator = document.getElementById('statusIndicator');
    
    if (!isAuthenticated) {
        statusIndicator.innerHTML = `
            <span class="status-indicator status-warning"></span>
            <span class="text-light">Not Authenticated</span>
        `;
    } else if (uploadLimitReached) {
        statusIndicator.innerHTML = `
            <span class="status-indicator status-warning"></span>
            <span class="text-light">Upload Limit Reached</span>
        `;
    } else if (isMonitoring) {
        statusIndicator.innerHTML = `
            <span class="status-indicator status-active"></span>
            <span class="text-light">Monitoring</span>
        `;
    } else {
        statusIndicator.innerHTML = `
            <span class="status-indicator status-inactive"></span>
            <span class="text-light">Not Monitoring</span>
        `;
    }
}

function updateUploadLimitTimer() {
    if (!uploadLimitReached || !uploadLimitResetTime) return;
    
    const now = new Date();
    const timeLeft = uploadLimitResetTime - now;
    
    if (timeLeft <= 0) {
        document.getElementById('limitResetTime').textContent = 'Limit should be reset soon.';
        return;
    }
    
    const hours = Math.floor(timeLeft / (1000 * 60 * 60));
    const minutes = Math.floor((timeLeft % (1000 * 60 * 60)) / (1000 * 60));
    const seconds = Math.floor((timeLeft % (1000 * 60)) / 1000);
    
    document.getElementById('limitResetTime').textContent = 
        `Reset in: ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Settings management
function saveSettings() {
    console.log("Saving settings");
    
    // Show loading indicator
    const saveBtn = document.getElementById('saveSettingsBtn');
    const originalText = saveBtn.innerHTML;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Saving...';
    saveBtn.disabled = true;
    
    // Gather all settings
    const settings = {
        title_template: document.getElementById('titleTemplate').value,
        description: document.getElementById('description').value,
        tags: document.getElementById('tags').value,
        privacy: document.querySelector('input[name="privacySetting"]:checked').value,
        delete_after_upload: document.getElementById('deleteAfterUpload').checked,
        check_existing_files: document.getElementById('checkExistingFiles').checked,
        max_retries: parseInt(document.getElementById('maxRetries').value),
        upload_limit_duration: parseInt(document.getElementById('uploadLimitDuration').value),
        delete_retry_count: parseInt(document.getElementById('deleteRetryCount').value),
        delete_retry_delay: parseInt(document.getElementById('deleteRetryDelay').value)
    };
    
    // Save settings
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
    })
    .then(response => response.json())
    .then(data => {
        // Restore button
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
        
        if (data.success) {
            // Show success message
            console.log("Settings saved successfully");
            showToast('Success', 'Settings saved successfully!', 'success');
        } else {
            console.error(`Failed to save settings: ${data.error}`);
            showToast('Error', 'Failed to save settings: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        // Restore button
        saveBtn.innerHTML = originalText;
        saveBtn.disabled = false;
        
        console.error('Error saving settings:', error);
        showToast('Error', 'Error saving settings. Check console for details.', 'danger');
    });
}

// Toast notification
function showToast(title, message, type = 'info') {
    // Check if toast container exists
    let toastContainer = document.querySelector('.toast-container');
    
    // Create container if it doesn't exist
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Create toast element
    const toastEl = document.createElement('div');
    toastEl.className = `toast fade-in align-items-center text-white bg-${type} border-0`;
    toastEl.setAttribute('role', 'alert');
    toastEl.setAttribute('aria-live', 'assertive');
    toastEl.setAttribute('aria-atomic', 'true');
    
    toastEl.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <strong>${title}:</strong> ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toastEl);
    
    // Initialize and show toast
    const toast = new bootstrap.Toast(toastEl, { autohide: true, delay: 5000 });
    toast.show();
    
    // Remove from DOM after hidden
    toastEl.addEventListener('hidden.bs.toast', function () {
        toastEl.remove();
    });
}

// Channel selection functions
function loadChannels() {
    console.log("Loading YouTube channels");
    
    const loadingEl = document.getElementById('channelsLoading');
    const listEl = document.getElementById('channelsList');
    const errorEl = document.getElementById('channelsError');
    
    // Show loading, hide others
    loadingEl.classList.remove('d-none');
    listEl.classList.add('d-none');
    errorEl.classList.add('d-none');
    
    // Fetch channels
    fetch('/api/channels')
        .then(response => response.json())
        .then(data => {
            loadingEl.classList.add('d-none');
            
            if (data.success) {
                if (data.channels.length === 0) {
                    // No channels found
                    listEl.innerHTML = `
                        <div class="alert alert-warning">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            No YouTube channels found for your account. Please make sure you have created a YouTube channel.
                        </div>
                    `;
                } else {
                    console.log(`Found ${data.channels.length} YouTube channels`);
                    // Display channels
                    listEl.innerHTML = '<div class="list-group">';
                    
                    data.channels.forEach(channel => {
                        const isSelected = data.selected_channel === channel.id;
                        
                        listEl.innerHTML += `
                            <div class="list-group-item list-group-item-action ${isSelected ? 'active' : ''}" 
                                 id="channel-${channel.id}">
                                <div class="d-flex align-items-center">
                                    <img src="${channel.thumbnail}" alt="${channel.title}" class="me-3" style="width: 48px; height: 48px; border-radius: 50%;">
                                    <div>
                                        <h6 class="mb-0">${channel.title}</h6>
                                        <small class="text-muted">Channel ID: ${channel.id}</small>
                                    </div>
                                    <div class="ms-auto">
                                        ${isSelected ? 
                                            '<span class="badge bg-success">Selected</span>' : 
                                            `<button class="btn btn-sm btn-primary" onclick="selectChannel('${channel.id}')">Select</button>`
                                        }
                                    </div>
                                </div>
                            </div>
                        `;
                    });
                    
                    listEl.innerHTML += '</div>';
                }
                
                listEl.classList.remove('d-none');
            } else {
                // Show error
                console.error(`Failed to load channels: ${data.error}`);
                errorEl.textContent = data.error || 'Failed to load channels';
                errorEl.classList.remove('d-none');
            }
        })
        .catch(error => {
            console.error('Error loading channels:', error);
            loadingEl.classList.add('d-none');
            errorEl.classList.remove('d-none');
        });
}

function selectChannel(channelId) {
    console.log(`Selecting channel: ${channelId}`);
    
    fetch('/api/channels/select', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            channel_id: channelId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload channel list to show updated selection
            console.log("Channel selected successfully");
            loadChannels();
            showToast('Success', 'Channel selected successfully!', 'success');
        } else {
            console.error(`Failed to select channel: ${data.error}`);
            showToast('Error', 'Failed to select channel: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error selecting channel:', error);
        showToast('Error', 'Error selecting channel', 'danger');
    });
}

// API Projects functions
function loadApiProjects() {
    console.log("Loading API projects");
    
    const loadingEl = document.getElementById('projectsLoading');
    const listEl = document.getElementById('projectsList');
    const errorEl = document.getElementById('projectsError');
    
    // Show loading, hide others
    loadingEl.classList.remove('d-none');
    listEl.classList.add('d-none');
    errorEl.classList.add('d-none');
    
    // Fetch projects
    fetch('/api/projects')
        .then(response => response.json())
        .then(data => {
            loadingEl.classList.add('d-none');
            
            if (data.success) {
                if (data.projects.length === 0) {
                    // No projects found
                    listEl.innerHTML = `
                        <div class="alert alert-warning">
                            <i class="bi bi-exclamation-triangle me-2"></i>
                            No API projects found. Add a new API project to get started.
                        </div>
                    `;
                } else {
                    console.log(`Found ${data.projects.length} API projects`);
                    // Display projects
                    listEl.innerHTML = `
                        <div class="table-responsive">
                            <table class="table table-hover">
                                <thead>
                                    <tr>
                                        <th>Project</th>
                                        <th>Status</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                    `;
                    
                    data.projects.forEach(project => {
                        const statusBadge = project.is_authenticated
                            ? `<span class="badge bg-success">Authenticated</span>`
                            : `<span class="badge bg-warning text-dark">Not Authenticated</span>`;
                            
                        const activeBadge = project.is_active
                            ? `<span class="badge bg-primary ms-2">Active</span>`
                            : '';
                            
                        const authButton = project.is_authenticated
                            ? ``
                            : `<a href="/auth/project/${project.id}" class="btn btn-sm btn-primary me-2">
                                <i class="bi bi-key me-1"></i> Authenticate
                               </a>`;
                               
                        const selectButton = !project.is_active && project.is_authenticated
                            ? `<button class="btn btn-sm btn-outline-primary" onclick="selectApiProject('${project.id}')">
                                <i class="bi bi-check-circle me-1"></i> Use This Project
                               </button>`
                            : '';
                        
                        listEl.innerHTML += `
                            <tr>
                                <td>${project.name || project.id}</td>
                                <td>${statusBadge}${activeBadge}</td>
                                <td>
                                    ${authButton}
                                    ${selectButton}
                                </td>
                            </tr>
                        `;
                    });
                    
                    listEl.innerHTML += `
                                </tbody>
                            </table>
                        </div>
                    `;
                }
                
                listEl.classList.remove('d-none');
            } else {
                // Show error
                console.error(`Failed to load API projects: ${data.error}`);
                errorEl.textContent = data.error || 'Failed to load API projects';
                errorEl.classList.remove('d-none');
            }
        })
        .catch(error => {
            console.error('Error loading API projects:', error);
            loadingEl.classList.add('d-none');
            errorEl.classList.remove('d-none');
        });
}

function selectApiProject(projectId) {
    console.log(`Selecting API project: ${projectId}`);
    
    fetch('/api/projects/select', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            project_id: projectId
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Reload project list
            console.log("API project selected successfully");
            loadApiProjects();
            showToast('Success', 'API project selected successfully!', 'success');
        } else if (data.needs_auth) {
            // Redirect to auth page
            console.log(`API project needs authentication, redirecting to auth page for project ${data.project_id}`);
            window.location.href = `/auth/project/${data.project_id}`;
        } else {
            console.error(`Failed to select API project: ${data.error}`);
            showToast('Error', 'Failed to select project: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error selecting API project:', error);
        showToast('Error', 'Error selecting API project', 'danger');
    });
}

function uploadApiProject() {
    const fileInput = document.getElementById('projectFile');
    if (!fileInput.files || fileInput.files.length === 0) {
        showToast('Warning', 'Please select a file to upload', 'warning');
        return;
    }
    
    const file = fileInput.files[0];
    console.log(`Uploading API project file: ${file.name}`);
    
    if (!file.name.endsWith('.json')) {
        showToast('Warning', 'Please upload a .json file', 'warning');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    fetch('/api/projects/add', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            console.log(`API project added successfully with ID: ${data.project_id}`);
            showToast('Success', 'API project added successfully! You need to authenticate it now.', 'success');
            loadApiProjects();
            fileInput.value = ''; // Clear the file input
        } else {
            console.error(`Failed to add API project: ${data.error}`);
            showToast('Error', 'Failed to add API project: ' + (data.error || 'Unknown error'), 'danger');
        }
    })
    .catch(error => {
        console.error('Error uploading API project:', error);
        showToast('Error', 'Error uploading API project', 'danger');
    });
}

// Add this to the bottom of static/js/app.js

// Updates functionality
function checkForUpdates() {
    console.log("Checking for updates");
    
    const loadingEl = document.getElementById('updateStatusLoading');
    const contentEl = document.getElementById('updateStatusContent');
    const upToDateEl = document.getElementById('upToDateMessage');
    const updateAvailableEl = document.getElementById('updateAvailableMessage');
    const updateErrorEl = document.getElementById('updateErrorMessage');
    
    // Show loading, hide others
    loadingEl.classList.remove('d-none');
    contentEl.classList.add('d-none');
    upToDateEl.classList.add('d-none');
    updateAvailableEl.classList.add('d-none');
    updateErrorEl.classList.add('d-none');
    
    // Check for updates
    fetch('/api/updates/check')
        .then(response => response.json())
        .then(data => {
            loadingEl.classList.add('d-none');
            contentEl.classList.remove('d-none');
            
            if (data.success) {
                // Update version info
                document.getElementById('currentVersionText').textContent = data.current_version;
                
                // Set auto-update toggle state
                document.getElementById('autoUpdateToggle').checked = data.auto_update_enabled;
                
                if (data.update_available) {
                    // Show update available message
                    document.getElementById('latestVersionText').textContent = data.latest_version;
                    document.getElementById('releaseNotes').textContent = data.release_notes || "No release notes available.";
                    updateAvailableEl.classList.remove('d-none');
                } else {
                    // Show up to date message
                    upToDateEl.classList.remove('d-none');
                }
            } else {
                // Show error
                document.getElementById('updateErrorText').textContent = data.error || "Unable to check for updates.";
                updateErrorEl.classList.remove('d-none');
            }
        })
        .catch(error => {
            console.error('Error checking for updates:', error);
            loadingEl.classList.add('d-none');
            contentEl.classList.remove('d-none');
            document.getElementById('updateErrorText').textContent = "Connection error. Please try again.";
            updateErrorEl.classList.remove('d-none');
        });
}

function applyUpdate() {
    console.log("Applying update");
    
    // Show loading
    const updateNowBtn = document.getElementById('updateNowBtn');
    const originalBtnText = updateNowBtn.innerHTML;
    updateNowBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span> Updating...';
    updateNowBtn.disabled = true;
    
    // Apply update
    fetch('/api/updates/apply', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show restart needed message
            showToast('Success', 'Update installed successfully! Restarting application...', 'success');
            
            // Restart the application
            setTimeout(() => {
                restartApplication();
            }, 3000);
        } else {
            // Show error
            updateNowBtn.innerHTML = originalBtnText;
            updateNowBtn.disabled = false;
            showToast('Error', 'Update failed: ' + (data.error || "Unknown error"), 'danger');
        }
    })
    .catch(error => {
        console.error('Error applying update:', error);
        updateNowBtn.innerHTML = originalBtnText;
        updateNowBtn.disabled = false;
        showToast('Error', 'Connection error while updating', 'danger');
    });
}

function toggleAutoUpdate() {
    const enabled = document.getElementById('autoUpdateToggle').checked;
    console.log(`Setting auto-update to: ${enabled}`);
    
    fetch('/api/updates/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            auto_update_enabled: enabled
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', `Auto-update ${enabled ? 'enabled' : 'disabled'}`, 'success');
        } else {
            showToast('Error', 'Failed to update settings: ' + (data.error || "Unknown error"), 'danger');
            // Revert the toggle if setting failed
            document.getElementById('autoUpdateToggle').checked = !enabled;
        }
    })
    .catch(error => {
        console.error('Error updating auto-update setting:', error);
        showToast('Error', 'Error updating setting', 'danger');
        // Revert the toggle on error
        document.getElementById('autoUpdateToggle').checked = !enabled;
    });
}

function restartApplication() {
    fetch('/api/updates/restart', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show restarting message
            document.body.innerHTML = `
                <div class="container text-center" style="margin-top: 100px;">
                    <h2>Restarting Application</h2>
                    <div class="spinner-border text-primary mt-4" role="status" style="width: 4rem; height: 4rem;">
                        <span class="visually-hidden">Restarting...</span>
                    </div>
                    <p class="lead mt-4">Please wait while the application restarts...</p>
                    <p>The page will reload automatically. If it doesn't, <a href="/" class="btn btn-link">click here</a>.</p>
                </div>
            `;
            
            // Try to reload the page after a delay
            setTimeout(() => {
                window.location.reload();
            }, 5000);
        }
    })
    .catch(error => {
        console.error('Error restarting application:', error);
        showToast('Error', 'Error restarting application', 'danger');
    });
}

// Load updates when the About tab is shown
document.getElementById('about-tab').addEventListener('shown.bs.tab', function (e) {
    checkForUpdates();
});

// Set up event listeners for update functionality
document.addEventListener('DOMContentLoaded', function() {
    // Auto-update toggle
    document.getElementById('autoUpdateToggle').addEventListener('change', toggleAutoUpdate);
    
    // Update now button
    document.getElementById('updateNowBtn')?.addEventListener('click', applyUpdate);
    
    // Manual check button
    document.getElementById('manualCheckUpdateBtn')?.addEventListener('click', checkForUpdates);
    
    // Retry button
    document.getElementById('retryUpdateBtn')?.addEventListener('click', checkForUpdates);
});