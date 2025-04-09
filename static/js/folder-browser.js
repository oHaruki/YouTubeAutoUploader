/**
 * Enhanced Folder Browser Component
 * Provides a more intuitive folder selection experience
 */

// Global state
const folderBrowser = {
    currentPath: '',
    currentView: 'grid', // 'grid' or 'list'
    isLoading: false,
    quickAccessLocations: [
        { name: 'Home', path: '~', icon: 'bi-house' },
        { name: 'Desktop', path: '~/Desktop', icon: 'bi-display' },
        { name: 'Documents', path: '~/Documents', icon: 'bi-file-earmark-text' },
        { name: 'Downloads', path: '~/Downloads', icon: 'bi-download' },
        { name: 'Pictures', path: '~/Pictures', icon: 'bi-images' },
        { name: 'Videos', path: '~/Videos', icon: 'bi-film' }
    ],
    rootLocations: [
        { name: 'System', path: '/', icon: 'bi-hdd-rack' }
    ],
    history: [],
    historyIndex: -1
};

// Initialize the folder browser
function initEnhancedFolderBrowser() {
    renderFolderBrowserUI();
    setupEventListeners();
    
    // Start with home directory or current watch folder
    const startPath = document.getElementById('watchFolderPath').value || '~';
    navigateToPath(startPath);
}

// Render the folder browser UI
function renderFolderBrowserUI() {
    const modalBody = document.querySelector('#folderBrowserModal .modal-body');
    
    // Create enhanced UI structure
    modalBody.innerHTML = `
        <div class="folder-browser-container position-relative">
            <!-- Sidebar with quick access -->
            <div class="folder-sidebar">
                <div class="sidebar-heading">Quick Access</div>
                <div id="quickAccessList">
                    ${folderBrowser.quickAccessLocations.map(loc => 
                        `<div class="quick-access-item" data-path="${loc.path}">
                            <i class="bi ${loc.icon} me-2"></i>
                            ${loc.name}
                        </div>`
                    ).join('')}
                </div>
                
                <div class="sidebar-heading mt-3">Devices</div>
                <div id="rootLocationsList">
                    ${folderBrowser.rootLocations.map(loc => 
                        `<div class="quick-access-item" data-path="${loc.path}">
                            <i class="bi ${loc.icon} me-2"></i>
                            ${loc.name}
                        </div>`
                    ).join('')}
                </div>
            </div>
            
            <!-- Main content area -->
            <div class="folder-content">
                <!-- Path input and navigation -->
                <div class="path-navigator">
                    <button class="btn btn-sm btn-outline-secondary me-2" id="folderBackBtn" disabled>
                        <i class="bi bi-arrow-left"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary me-2" id="folderForwardBtn" disabled>
                        <i class="bi bi-arrow-right"></i>
                    </button>
                    <input type="text" class="path-input" id="pathInput" placeholder="Path" readonly>
                    <button class="refresh-btn" id="refreshFolderBtn">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                </div>
                
                <!-- Breadcrumb navigation -->
                <div class="folder-breadcrumb" id="enhancedBreadcrumb">
                    <!-- Breadcrumb items will be added here -->
                </div>
                
                <!-- View toggle -->
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="folder-view-toggle">
                        <button class="view-btn active" id="gridViewBtn">
                            <i class="bi bi-grid-3x3-gap"></i>
                        </button>
                        <button class="view-btn" id="listViewBtn">
                            <i class="bi bi-list-ul"></i>
                        </button>
                    </div>
                    <div id="folderItemCount" class="small text-muted">
                        <!-- Item count will be shown here -->
                    </div>
                </div>
                
                <!-- Folders will be displayed here -->
                <div id="folderContents">
                    <div class="text-center py-4">
                        <div class="spinner-border text-primary" role="status">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                        <p class="mt-2">Loading folders...</p>
                    </div>
                </div>
            </div>
            
            <!-- Loading overlay -->
            <div class="loading-overlay d-none" id="folderLoadingOverlay">
                <div class="spinner-border text-light" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
            </div>
        </div>
        
        <!-- Selected folder display -->
        <div class="folder-browser-footer mt-3">
            <div>
                <strong>Selected:</strong>
                <span class="selected-path" id="selectedFolderPath">No folder selected</span>
            </div>
        </div>
    `;
}

// Set up event listeners for the folder browser
function setupEventListeners() {
    // Quick access items
    document.querySelectorAll('.quick-access-item').forEach(item => {
        item.addEventListener('click', () => {
            navigateToPath(item.dataset.path);
        });
    });
    
    // View toggle buttons
    document.getElementById('gridViewBtn').addEventListener('click', () => {
        setFolderView('grid');
    });
    
    document.getElementById('listViewBtn').addEventListener('click', () => {
        setFolderView('list');
    });
    
    // Refresh button
    document.getElementById('refreshFolderBtn').addEventListener('click', () => {
        refreshCurrentFolder();
    });
    
    // Navigation buttons
    document.getElementById('folderBackBtn').addEventListener('click', navigateBack);
    document.getElementById('folderForwardBtn').addEventListener('click', navigateForward);
    
    // Path input for direct navigation
    const pathInput = document.getElementById('pathInput');
    pathInput.addEventListener('click', () => {
        // Make it editable when clicked
        pathInput.readOnly = false;
    });
    
    pathInput.addEventListener('blur', () => {
        pathInput.readOnly = true;
    });
    
    pathInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            navigateToPath(pathInput.value);
            pathInput.blur();
        }
    });
    
    // Update the select folder button to use the current path
    document.getElementById('selectFolderBtn').addEventListener('click', () => {
        selectFolder(folderBrowser.currentPath);
    });
}

// Navigate to a specific path
function navigateToPath(path) {
    setLoading(true);
    
    // No need to normalize the path here - the server will handle '~'
    // The server's Python code can expand the tilde using os.path.expanduser
    
    // Add to history if it's a new navigation
    if (folderBrowser.currentPath !== path) {
        // If we navigated from history, trim the forward history
        if (folderBrowser.historyIndex < folderBrowser.history.length - 1) {
            folderBrowser.history = folderBrowser.history.slice(0, folderBrowser.historyIndex + 1);
        }
        
        folderBrowser.history.push(path);
        folderBrowser.historyIndex = folderBrowser.history.length - 1;
        
        updateNavigationButtons();
    }
    
    folderBrowser.currentPath = path;
    document.getElementById('pathInput').value = path;
    document.getElementById('selectedFolderPath').textContent = path;
    
    // Fetch folder contents
    fetch(`/api/folder/browse?path=${encodeURIComponent(path)}`)
        .then(response => response.json())
        .then(data => {
            setLoading(false);
            
            if (data.success) {
                renderFolderContents(data);
                updateBreadcrumb(data.current_path);
                updateFolderCount(data.directories.length);
            } else {
                showFolderError(data.error || 'Error loading folder');
            }
        })
        .catch(error => {
            setLoading(false);
            console.error('Error browsing folders:', error);
            showFolderError('Error connecting to server');
        });
}

// Render folder contents based on the current view mode
function renderFolderContents(data) {
    const contentsElement = document.getElementById('folderContents');
    
    if (data.directories.length === 0) {
        contentsElement.innerHTML = `
            <div class="empty-folder-message">
                <i class="bi bi-folder"></i>
                <div>This folder is empty</div>
            </div>
        `;
        return;
    }
    
    if (folderBrowser.currentView === 'grid') {
        renderGridView(contentsElement, data);
    } else {
        renderListView(contentsElement, data);
    }
}

// Render folders in grid view
function renderGridView(container, data) {
    let html = '<div class="folder-grid">';
    
    // Add parent directory if available
    if (data.parent) {
        html += `
            <div class="grid-folder-item parent-folder" data-path="${data.parent}">
                <i class="bi bi-arrow-up-circle folder-icon"></i>
                <div class="folder-name">Parent Directory</div>
            </div>
        `;
    }
    
    // Add folders
    data.directories.forEach(dir => {
        html += `
            <div class="grid-folder-item" data-path="${data.current_path}/${dir}">
                <i class="bi bi-folder-fill folder-icon"></i>
                <div class="folder-name" title="${dir}">${dir}</div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
    
    // Add click events
    container.querySelectorAll('.grid-folder-item').forEach(item => {
        item.addEventListener('click', () => {
            navigateToPath(item.dataset.path);
        });
    });
}

// Render folders in list view
function renderListView(container, data) {
    let html = '<ul class="folder-list">';
    
    // Add parent directory if available
    if (data.parent) {
        html += `
            <li class="list-folder-item parent-folder" data-path="${data.parent}">
                <i class="bi bi-arrow-up-circle folder-icon"></i>
                <span>Parent Directory</span>
            </li>
        `;
    }
    
    // Add folders
    data.directories.forEach(dir => {
        html += `
            <li class="list-folder-item" data-path="${data.current_path}/${dir}">
                <i class="bi bi-folder-fill folder-icon"></i>
                <span title="${dir}">${dir}</span>
            </li>
        `;
    });
    
    html += '</ul>';
    container.innerHTML = html;
    
    // Add click events
    container.querySelectorAll('.list-folder-item').forEach(item => {
        item.addEventListener('click', () => {
            navigateToPath(item.dataset.path);
        });
    });
}

// Update breadcrumb navigation
function updateBreadcrumb(path) {
    const breadcrumb = document.getElementById('enhancedBreadcrumb');
    breadcrumb.innerHTML = '';
    
    // Add root
    const rootItem = document.createElement('div');
    rootItem.className = 'breadcrumb-item';
    
    const rootLink = document.createElement('a');
    rootLink.href = '#';
    rootLink.className = 'breadcrumb-link';
    rootLink.innerHTML = '<i class="bi bi-hdd-rack me-1"></i>Root';
    rootLink.addEventListener('click', (e) => {
        e.preventDefault();
        navigateToPath('/');
    });
    
    rootItem.appendChild(rootLink);
    breadcrumb.appendChild(rootItem);
    
    // Split path into parts
    const parts = path.split('/').filter(p => p !== '');
    let currentPath = '';
    
    parts.forEach((part, index) => {
        currentPath += '/' + part;
        const item = document.createElement('div');
        item.className = 'breadcrumb-item';
        
        if (index === parts.length - 1) {
            // Current folder
            const current = document.createElement('span');
            current.className = 'breadcrumb-current';
            current.textContent = part;
            item.appendChild(current);
        } else {
            // Parent folder
            const link = document.createElement('a');
            link.href = '#';
            link.className = 'breadcrumb-link';
            link.textContent = part;
            
            const pathCopy = currentPath;
            link.addEventListener('click', (e) => {
                e.preventDefault();
                navigateToPath(pathCopy);
            });
            
            item.appendChild(link);
        }
        
        breadcrumb.appendChild(item);
    });
}

// Update folder count display
function updateFolderCount(count) {
    const countElement = document.getElementById('folderItemCount');
    countElement.textContent = `${count} ${count === 1 ? 'folder' : 'folders'}`;
}

// Toggle between grid and list views
function setFolderView(view) {
    folderBrowser.currentView = view;
    
    // Update button states
    document.getElementById('gridViewBtn').classList.toggle('active', view === 'grid');
    document.getElementById('listViewBtn').classList.toggle('active', view === 'list');
    
    // If we have data, refresh the view
    if (document.querySelector('.grid-folder-item, .list-folder-item')) {
        // Re-render without fetching again
        refreshCurrentFolder(false);
    }
}

// Refresh the current folder
function refreshCurrentFolder(fetchNew = true) {
    if (fetchNew) {
        navigateToPath(folderBrowser.currentPath);
    } else {
        // Just re-render with existing data
        const directories = document.querySelectorAll('.grid-folder-item, .list-folder-item');
        
        const data = {
            current_path: folderBrowser.currentPath,
            parent: document.querySelector('.parent-folder')?.dataset.path,
            directories: Array.from(directories)
                .filter(el => !el.classList.contains('parent-folder'))
                .map(el => el.querySelector('.folder-name, span').textContent)
        };
        
        renderFolderContents(data);
    }
}

// Navigation history
function navigateBack() {
    if (folderBrowser.historyIndex > 0) {
        folderBrowser.historyIndex--;
        navigateToPath(folderBrowser.history[folderBrowser.historyIndex]);
        updateNavigationButtons();
    }
}

function navigateForward() {
    if (folderBrowser.historyIndex < folderBrowser.history.length - 1) {
        folderBrowser.historyIndex++;
        navigateToPath(folderBrowser.history[folderBrowser.historyIndex]);
        updateNavigationButtons();
    }
}

function updateNavigationButtons() {
    document.getElementById('folderBackBtn').disabled = folderBrowser.historyIndex <= 0;
    document.getElementById('folderForwardBtn').disabled = folderBrowser.historyIndex >= folderBrowser.history.length - 1;
}

// Show error message
function showFolderError(message) {
    document.getElementById('folderContents').innerHTML = `
        <div class="alert alert-danger">
            <i class="bi bi-exclamation-triangle me-2"></i>
            ${message}
        </div>
    `;
}

// Set loading state
function setLoading(isLoading) {
    folderBrowser.isLoading = isLoading;
    document.getElementById('folderLoadingOverlay').classList.toggle('d-none', !isLoading);
}

// Select a folder and update the watch folder path
function selectFolder(path) {
    document.getElementById('watchFolderPath').value = path;
    
    // Save the selection
    fetch('/api/settings', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            watch_folder: path
        })
    })
    .then(response => response.json())
    .then(data => {
        if (!data.success) {
            showToast('Error', 'Failed to save folder selection: ' + (data.error || 'Unknown error'), 'danger');
        } else {
            showToast('Success', 'Folder selected successfully!', 'success');
        }
    })
    .catch(error => {
        console.error('Error saving folder selection:', error);
        showToast('Error', 'Error saving folder selection', 'danger');
    });
}

// Initialize the enhanced folder browser when the modal is shown
document.addEventListener('DOMContentLoaded', function() {
    const folderBrowserModal = document.getElementById('folderBrowserModal');
    if (folderBrowserModal) {
        folderBrowserModal.addEventListener('shown.bs.modal', initEnhancedFolderBrowser);
    }
});