// Dynamic Kanban Board JavaScript
// Real-time project management with WebSocket synchronization

// Configuration - Auto-detect WebSocket port or use default
const CONFIG = {
    websocketPort: window.KANBAN_WEBSOCKET_PORT || 8765,
    defaultColumns: [
        {"id": "backlog", "name": "📋 Backlog", "emoji": "📋"},
        {"id": "ready", "name": "⚡ Ready", "emoji": "⚡"},
        {"id": "progress", "name": "🔧 In Progress", "emoji": "🔧"},
        {"id": "testing", "name": "🧪 Testing", "emoji": "🧪"},
        {"id": "done", "name": "✅ Done", "emoji": "✅"}
    ],
    reconnectDelay: window.KANBAN_RECONNECT_DELAY || 3000,
    maxReconnectAttempts: window.KANBAN_MAX_RECONNECTS || 10
};

// State management
let state = {
    features: [],
    boardState: {},
    connected: false,
    socket: null,
    projectTitle: "Dynamic Project",
    columns: CONFIG.defaultColumns,
    isManualMode: false,
    selectedCards: new Set(),
    reconnectAttempts: 0,
    reconnectTimer: null
};

// Initialize board
function initializeBoard() {
    createColumns();
    updateCounts();
    setupEventListeners();
    initializeWebSocket();
    console.log('✅ Real-time Kanban board initialized');
}

// WebSocket Management
function initializeWebSocket() {
    connectWebSocket();
}

function connectWebSocket() {
    try {
        // Clear any existing reconnect timer
        if (state.reconnectTimer) {
            clearTimeout(state.reconnectTimer);
            state.reconnectTimer = null;
        }
        
        state.socket = new WebSocket(`ws://127.0.0.1:${CONFIG.websocketPort}`);
        
        state.socket.onopen = function(event) {
            console.log('✅ WebSocket connected');
            state.connected = true;
            state.reconnectAttempts = 0; // Reset on successful connection
            updateConnectionStatus(true);
            
            // Force refresh board state from files when connecting
            setTimeout(() => {
                sendWebSocketMessage({type: 'refresh_board'});
            }, 500);
        };
        
        state.socket.onmessage = function(event) {
            try {
                const message = JSON.parse(event.data);
                handleWebSocketMessage(message);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };
        
        state.socket.onclose = function(event) {
            console.log('🔌 WebSocket disconnected');
            state.connected = false;
            updateConnectionStatus(false);
            
            // Attempt to reconnect with exponential backoff
            scheduleReconnect();
        };
        
        state.socket.onerror = function(error) {
            console.error('❌ WebSocket error:', error);
            state.connected = false;
            updateConnectionStatus(false);
        };
        
    } catch (e) {
        console.error('Failed to create WebSocket connection:', e);
        updateConnectionStatus(false);
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (state.reconnectAttempts >= CONFIG.maxReconnectAttempts) {
        console.log('❌ Max reconnection attempts reached');
        updateConnectionStatus(false, 'Max reconnection attempts reached');
        return;
    }
    
    state.reconnectAttempts++;
    const delay = Math.min(CONFIG.reconnectDelay * Math.pow(2, state.reconnectAttempts - 1), 30000);
    
    console.log(`🔄 Attempting to reconnect in ${delay/1000}s (attempt ${state.reconnectAttempts}/${CONFIG.maxReconnectAttempts})`);
    
    state.reconnectTimer = setTimeout(() => {
        if (!state.connected) {
            console.log(`🔄 Reconnection attempt ${state.reconnectAttempts}`);
            connectWebSocket();
        }
    }, delay);
}

function handleWebSocketMessage(message) {
    console.log('📨 WebSocket message:', message);
    
    switch (message.type) {
        case 'initial_state':
        case 'state_update':
            updateBoardFromServer(message.data);
            break;
        case 'move_card_response':
            console.log('✅ Card move confirmed by server');
            break;
        case 'refresh_response':
            console.log('✅ Board refreshed from server files');
            showNotification('Board refreshed from files', 'success');
            break;
        case 'error':
            console.error('❌ Server error:', message.message);
            break;
        
        // ===== MODE MANAGEMENT RESPONSES =====
        case 'mode_changed':
            console.log(`🔄 Mode changed to ${message.isManualMode ? 'Manual' : 'Autonomous'} by ${message.source}`);
            if (message.pendingActions > 0) {
                showNotification(`Mode switched. ${message.pendingActions} Claude actions are pending.`, 'info');
            }
            break;
            
        case 'set_mode_response':
            console.log(`✅ Mode change confirmed: ${message.isManualMode ? 'Manual' : 'Autonomous'}`);
            if (message.pendingActions > 0 && !message.isManualMode) {
                // Switched to autonomous with pending actions
                setTimeout(() => showPendingActionsDialog(message.pendingActions), 1000);
            }
            break;
            
        case 'claude_action_blocked':
            const action = message.action;
            showNotification(`🔒 Claude action blocked: ${action.description}`, 'warning');
            updatePendingActionsIndicator(message.totalPending);
            break;
            
        case 'pending_actions_response':
            if (message.actions.length > 0) {
                showPendingActionsDialog(message.actions.length, message.actions);
            }
            break;
            
        case 'pending_actions_applied':
            showNotification(`✅ Applied ${message.appliedCount} pending Claude actions`, 'success');
            updateBoardFromCurrentState();
            break;
        
        // ===== MANUAL TASK RESPONSES =====
        case 'manual_task_response':
            if (message.success) {
                showNotification(`✅ Task ${message.action} successfully`, 'success');
            } else {
                showNotification(`❌ Failed to ${message.action} task: ${message.message}`, 'error');
            }
            break;
            
        case 'bulk_move_response':
            if (message.success) {
                showNotification(`✅ Moved ${message.movedCount} tasks to ${message.newStatus}`, 'success');
            } else {
                showNotification(`❌ Bulk move failed: ${message.message}`, 'error');
            }
            break;
            
        case 'bulk_delete_response':
            if (message.success) {
                showNotification(`✅ Deleted ${message.deletedCount} tasks`, 'success');
            } else {
                showNotification(`❌ Bulk delete failed: ${message.message}`, 'error');
            }
            break;
            
        default:
            // Check if it's a clearing/removal response
            if (message.type.includes('_response')) {
                console.log('📨 Handling clearing/removal response:', message);
                handleClearingResponse(message);
            } else {
                console.log('❓ Unknown message type:', message.type, message);
            }
    }
}

function updateBoardFromServer(data) {
    // Always update state from server - this handles empty data properly
    state.features = data.features || [];
    state.boardState = data.boardState || {};
    
    // Update project title if available
    if (data.metadata && data.metadata.projectName) {
        state.projectTitle = data.metadata.projectName;
        document.querySelector('.header h1').textContent = `🚀 ${state.projectTitle} Kanban`;
    } else if (state.features.length === 0) {
        // Reset title when no features
        state.projectTitle = "Dynamic Project";
        document.querySelector('.header h1').textContent = `🚀 ${state.projectTitle} Kanban`;
    }
    
    // Always re-render the board completely
    createColumns();
    renderCards();
    updateCounts();
    
    // Show/hide startup message based on data
    if (state.features.length === 0) {
        showStartupMessage();
    } else {
        hideStartupMessage();
    }
}

function sendWebSocketMessage(message) {
    if (state.socket && state.socket.readyState === WebSocket.OPEN) {
        console.log('📤 Sending WebSocket message:', message);
        state.socket.send(JSON.stringify(message));
        return true;
    } else {
        console.warn('⚠️ WebSocket not connected, cannot send message:', {
            socket: state.socket,
            readyState: state.socket ? state.socket.readyState : 'null',
            connected: state.connected
        });
        return false;
    }
}

function updateConnectionStatus(connected, message = null) {
    const indicator = document.getElementById('connection-indicator');
    const text = document.getElementById('connection-text');
    
    if (connected) {
        indicator.classList.add('connected');
        text.textContent = message || 'Connected to Claude - Real-time sync active';
    } else {
        indicator.classList.remove('connected');
        if (message) {
            text.textContent = message;
        } else if (state.reconnectAttempts > 0) {
            text.textContent = `Reconnecting... (attempt ${state.reconnectAttempts}/${CONFIG.maxReconnectAttempts})`;
        } else {
            text.textContent = 'Disconnected - Attempting to reconnect...';
        }
    }
}

function hideStartupMessage() {
    const startupMessage = document.getElementById('startup-message');
    if (startupMessage) {
        startupMessage.style.display = 'none';
    }
}

function showStartupMessage() {
    const startupMessage = document.getElementById('startup-message');
    if (startupMessage) {
        startupMessage.style.display = 'block';
    }
}

function reconnectWebSocket() {
    if (state.socket) {
        state.socket.close();
    }
    
    // Clear reconnect timer and reset attempts for manual reconnect
    if (state.reconnectTimer) {
        clearTimeout(state.reconnectTimer);
        state.reconnectTimer = null;
    }
    state.reconnectAttempts = 0;
    
    state.connected = false;
    updateConnectionStatus(false, 'Manually reconnecting...');
    setTimeout(connectWebSocket, 1000);
}

// Create columns based on configuration
function createColumns() {
    const board = document.getElementById('kanban-board');
    board.innerHTML = '';

    state.columns.forEach(column => {
        const columnElement = document.createElement('div');
        columnElement.className = 'column';
        columnElement.dataset.status = column.id;
        columnElement.innerHTML = `
            <div class="column-header">
                ${column.name}
                <span class="column-count">0</span>
                <button class="column-clear-btn" onclick="showClearColumnModal('${column.id}')" title="Clear ${column.name}">×</button>
            </div>
            <div class="drop-zone" data-status="${column.id}">
                Drop cards here
            </div>
        `;
        
        // Add drag and drop event listeners
        const dropZone = columnElement.querySelector('.drop-zone');
        setupDropZone(dropZone, column.id);
        
        board.appendChild(columnElement);
    });
}

// Show empty message
function showEmptyMessage() {
    const board = document.getElementById('kanban-board');
    board.innerHTML = `
        <div class="empty-board-message">
            <h2>🎯 Project Ready</h2>
            <p>Your kanban board is ready for Claude to manage!</p>
            <p>Use Claude's MCP tools to create a project and add features.</p>
            <p>Real-time sync is active - changes from Claude will appear instantly!</p>
        </div>
    `;
}

// Render cards
function renderCards() {
    // Clear columns (keep headers and drop zones)
    document.querySelectorAll('.column').forEach(column => {
        const header = column.querySelector('.column-header');
        const dropZone = column.querySelector('.drop-zone');
        column.innerHTML = '';
        column.appendChild(header);
        column.appendChild(dropZone);
    });

    // Only add cards if we have features
    if (state.features && state.features.length > 0) {
        state.features.forEach(feature => {
            const card = createCard(feature);
            const column = document.querySelector(`[data-status="${feature.status || 'backlog'}"]`);
            if (column) {
                // Insert before drop zone
                const dropZone = column.querySelector('.drop-zone');
                column.insertBefore(card, dropZone);
            }
        });
    }
}

// Create card element
function createCard(feature) {
    const card = document.createElement('div');
    card.className = state.isManualMode ? 'card manual-mode' : 'card';
    card.dataset.id = feature.id;
    card.draggable = true;

    const dependencyText = feature.dependencies && feature.dependencies.length > 0 
        ? `<div class="dependencies">Depends on: ${feature.dependencies.join(', ')}</div>`
        : '';

    // Manual mode enhancements
    const checkboxHtml = state.isManualMode ? 
        `<input type="checkbox" class="card-checkbox" onchange="toggleCardSelection('${feature.id}')" ${state.selectedCards.has(feature.id) ? 'checked' : ''}>` : '';
    
    const actionsHtml = state.isManualMode ? 
        `<div class="card-actions">
            <button class="card-action-btn edit" onclick="editTask('${feature.id}')" title="Edit">✏️</button>
            <button class="card-action-btn delete" onclick="deleteTask('${feature.id}')" title="Delete">🗑️</button>
        </div>` : '';

    card.innerHTML = `
        ${checkboxHtml}
        ${actionsHtml}
        <div class="card-title">${feature.title}</div>
        <div class="card-description">${feature.description || ''}</div>
        <div class="card-meta">
            <div class="card-tags">
                ${feature.priority ? `<span class="tag priority">${feature.priority}</span>` : ''}
                ${feature.effort ? `<span class="tag effort">${feature.effort}</span>` : ''}
                ${feature.epic ? `<span class="tag epic">${feature.epic}</span>` : ''}
                ${feature.stage ? `<span class="tag stage">Stage ${feature.stage}</span>` : ''}
            </div>
        </div>
        ${dependencyText}
    `;

    // Add drag event listeners
    setupDragEvents(card, feature);
    
    // In manual mode, click to edit; in autonomous mode, click for details
    if (state.isManualMode) {
        card.addEventListener('click', (e) => {
            if (!e.target.classList.contains('card-action-btn') && !e.target.classList.contains('card-checkbox')) {
                editTask(feature.id);
            }
        });
    } else {
        card.addEventListener('click', () => showCardDetails(feature));
    }
    
    return card;
}

// Setup drag events for cards
function setupDragEvents(card, feature) {
    card.addEventListener('dragstart', function(e) {
        e.dataTransfer.setData('text/plain', feature.id);
        card.classList.add('dragging');
        console.log('🎯 Dragging card:', feature.id);
    });
    
    card.addEventListener('dragend', function(e) {
        card.classList.remove('dragging');
    });
}

// Setup drop zone events
function setupDropZone(dropZone, status) {
    dropZone.addEventListener('dragover', function(e) {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', function(e) {
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        
        const taskId = e.dataTransfer.getData('text/plain');
        const feature = state.features.find(f => f.id === taskId);
        
        if (feature && feature.status !== status) {
            // Update local state immediately for responsive UI
            const oldStatus = feature.status;
            feature.status = status;
            state.boardState[taskId] = status;
            
            // Re-render cards
            renderCards();
            updateCounts();
            
            // Send to server via WebSocket
            const success = sendWebSocketMessage({
                type: 'move_card',
                taskId: taskId,
                newStatus: status,
                notes: `Moved from ${oldStatus} to ${status} via UI`
            });
            
            if (!success) {
                // Revert if WebSocket failed
                feature.status = oldStatus;
                state.boardState[taskId] = oldStatus;
                renderCards();
                updateCounts();
                alert('Failed to sync with server. Please check connection.');
            }
            
            console.log(`✅ Moved ${taskId} from ${oldStatus} to ${status}`);
        }
    });
}

// Show card details
function showCardDetails(feature) {
    const modal = document.getElementById('cardModal');
    const modalBody = document.getElementById('modal-body');
    
    modalBody.innerHTML = `
        <h2>${feature.title}</h2>
        <p><strong>Description:</strong> ${feature.description || 'No description'}</p>
        <p><strong>Stage:</strong> ${feature.stage || 'Not specified'}</p>
        <p><strong>Priority:</strong> ${feature.priority || 'Not specified'}</p>
        <p><strong>Effort:</strong> ${feature.effort || 'Not specified'}</p>
        <p><strong>Epic:</strong> ${feature.epic || 'Not specified'}</p>
        <p><strong>Dependencies:</strong> ${feature.dependencies && feature.dependencies.length ? feature.dependencies.join(', ') : 'None'}</p>
        <p><strong>Acceptance Criteria:</strong> ${feature.acceptance || 'Not specified'}</p>
    `;
    
    modal.style.display = 'block';
}

// Update counts
function updateCounts() {
    const statusCounts = {};
    let totalFeatures = 0;

    state.features.forEach(feature => {
        const status = feature.status || 'backlog';
        statusCounts[status] = (statusCounts[status] || 0) + 1;
        totalFeatures++;
    });

    // Update column counts
    document.querySelectorAll('.column').forEach(column => {
        const status = column.dataset.status;
        const count = statusCounts[status] || 0;
        const countEl = column.querySelector('.column-count');
        if (countEl) countEl.textContent = count;
    });

    // Update progress summary
    const doneCount = statusCounts.done || 0;
    const progressCount = statusCounts.progress || 0;
    const progressPercent = totalFeatures > 0 ? Math.round((doneCount / totalFeatures) * 100) : 0;

    document.getElementById('total-count').textContent = totalFeatures;
    document.getElementById('progress-count').textContent = progressCount;
    document.getElementById('done-count').textContent = doneCount;
    document.getElementById('progress-percent').textContent = `${progressPercent}%`;

    // Always show columns, render cards if they exist
    createColumns();
    if (totalFeatures > 0) {
        renderCards();
    }
}

// Setup event listeners
function setupEventListeners() {
    // Modal close
    const closeBtn = document.querySelector('.close');
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            document.getElementById('cardModal').style.display = 'none';
        });
    }

    window.addEventListener('click', (e) => {
        const modal = document.getElementById('cardModal');
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
}

// Export board
function exportBoard() {
    const exportData = {
        project: state.projectTitle,
        features: state.features,
        boardState: state.boardState,
        timestamp: new Date().toISOString(),
        websocketConnected: state.connected
    };
    
    const dataStr = JSON.stringify(exportData, null, 2);
    const dataBlob = new Blob([dataStr], {type: 'application/json'});
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `${state.projectTitle.toLowerCase().replace(/\s+/g, '-')}-kanban-export.json`;
    link.click();
    
    URL.revokeObjectURL(url);
}

// Refresh board
function refreshBoard() {
    if (state.connected) {
        // Force refresh from files and get updated state
        sendWebSocketMessage({type: 'refresh_board'});
    } else {
        location.reload();
    }
}

// Toggle legend visibility
function toggleLegend() {
    const content = document.getElementById('legend-content');
    const toggle = document.getElementById('legend-toggle');
    
    if (content.classList.contains('expanded')) {
        content.classList.remove('expanded');
        toggle.classList.remove('expanded');
        toggle.textContent = '▼';
    } else {
        content.classList.add('expanded');
        toggle.classList.add('expanded');
        toggle.textContent = '▲';
    }
}

// ===== MANUAL MODE FUNCTIONS =====

// Toggle between Manual and Autonomous mode
function toggleMode() {
    const toggle = document.getElementById('mode-toggle');
    const indicator = document.getElementById('mode-indicator');
    const modeText = document.getElementById('mode-text');
    const modeDescription = document.getElementById('mode-description');
    const fab = document.getElementById('fab');
    const kanbanBoard = document.getElementById('kanban-board');
    
    state.isManualMode = toggle.checked;
    
    // Send mode change to server
    if (state.connected) {
        sendWebSocketMessage({
            type: 'set_mode',
            isManualMode: state.isManualMode
        });
    }
    
    if (state.isManualMode) {
        // Switch to Manual Mode
        indicator.className = 'mode-indicator manual';
        indicator.innerHTML = '<span>👤</span><span id="mode-text">Manual Mode</span>';
        modeDescription.textContent = 'You control the kanban board - Claude is blocked';
        fab.classList.remove('hidden');
        kanbanBoard.classList.add('manual-mode');
    } else {
        // Switch to Autonomous Mode
        indicator.className = 'mode-indicator autonomous';
        indicator.innerHTML = '<span>🤖</span><span id="mode-text">Autonomous Mode</span>';
        modeDescription.textContent = 'Claude manages your kanban board';
        fab.classList.add('hidden');
        kanbanBoard.classList.remove('manual-mode');
        clearSelection(); // Clear any selections when switching modes
        
        // Check for pending actions when switching back to autonomous
        if (state.connected) {
            setTimeout(() => {
                sendWebSocketMessage({type: 'get_pending_actions'});
            }, 500);
        }
    }
    
    // Re-render cards with appropriate mode styling
    renderCards();
    updateBulkSelectionBar();
    
    console.log(`Switched to ${state.isManualMode ? 'Manual' : 'Autonomous'} mode`);
}

// Manual Mode - Task Management
function openAddTaskModal() {
    document.getElementById('addTaskModal').style.display = 'block';
    document.getElementById('taskTitle').focus();
}

function closeAddTaskModal() {
    document.getElementById('addTaskModal').style.display = 'none';
    document.getElementById('addTaskForm').reset();
}

function handleAddTask(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const taskData = {
        id: `task-${crypto.randomUUID().substring(0, 8)}`,
        title: formData.get('title'),
        description: formData.get('description'),
        priority: formData.get('priority'),
        effort: formData.get('effort'),
        epic: formData.get('epic'),
        stage: parseInt(formData.get('stage')),
        status: 'backlog',
        dependencies: formData.get('dependencies') ? 
            formData.get('dependencies').split(',').map(d => d.trim()).filter(d => d) : [],
        acceptance: formData.get('acceptance') || 'Task completed successfully'
    };
    
    // Add to local state
    state.features.push(taskData);
    state.boardState[taskData.id] = 'backlog';
    
    // Sync with WebSocket if connected
    if (state.connected) {
        sendWebSocketMessage({
            type: 'manual_task_added',
            task: taskData
        });
    }
    
    // Update UI
    createColumns();
    renderCards();
    updateCounts();
    closeAddTaskModal();
    
    console.log('Added new task:', taskData);
}

function editTask(taskId) {
    const feature = state.features.find(f => f.id === taskId);
    if (!feature) return;
    
    // Populate edit form
    document.getElementById('editTaskId').value = feature.id;
    document.getElementById('editTaskTitle').value = feature.title;
    document.getElementById('editTaskDescription').value = feature.description;
    document.getElementById('editTaskPriority').value = feature.priority;
    document.getElementById('editTaskEffort').value = feature.effort;
    document.getElementById('editTaskEpic').value = feature.epic;
    document.getElementById('editTaskStage').value = feature.stage;
    document.getElementById('editTaskAcceptance').value = feature.acceptance || '';
    document.getElementById('editTaskDependencies').value = feature.dependencies.join(', ');
    
    // Show modal
    document.getElementById('editTaskModal').style.display = 'block';
}

function closeEditTaskModal() {
    document.getElementById('editTaskModal').style.display = 'none';
    document.getElementById('editTaskForm').reset();
}

function handleEditTask(event) {
    event.preventDefault();
    
    const formData = new FormData(event.target);
    const taskId = formData.get('id');
    const feature = state.features.find(f => f.id === taskId);
    
    if (!feature) return;
    
    // Update feature data
    feature.title = formData.get('title');
    feature.description = formData.get('description');
    feature.priority = formData.get('priority');
    feature.effort = formData.get('effort');
    feature.epic = formData.get('epic');
    feature.stage = parseInt(formData.get('stage'));
    feature.acceptance = formData.get('acceptance') || 'Task completed successfully';
    feature.dependencies = formData.get('dependencies') ? 
        formData.get('dependencies').split(',').map(d => d.trim()).filter(d => d) : [];
    
    // Sync with WebSocket if connected
    if (state.connected) {
        sendWebSocketMessage({
            type: 'manual_task_updated',
            task: feature
        });
    }
    
    // Update UI
    renderCards();
    updateCounts();
    closeEditTaskModal();
    
    console.log('Updated task:', feature);
}

function deleteTask(taskId) {
    if (!confirm('Are you sure you want to delete this task?')) return;
    
    // Get task info before removal for better messaging
    const feature = state.features.find(f => f.id === taskId);
    const taskTitle = feature ? feature.title : taskId;
    
    // Sync with WebSocket FIRST if connected
    if (state.connected) {
        const success = sendWebSocketMessage({
            type: 'manual_task_deleted',
            taskId: taskId
        });
        
        if (success) {
            // Remove from local state only after successful WebSocket send
            state.features = state.features.filter(f => f.id !== taskId);
            delete state.boardState[taskId];
            state.selectedCards.delete(taskId);
            
            // Update UI
            renderCards();
            updateCounts();
            updateBulkSelectionBar();
            
            console.log('Deleted task via WebSocket:', taskId);
            showNotification(`Task "${taskTitle}" deleted successfully`, 'success');
        } else {
            showNotification('Failed to delete task - WebSocket not ready', 'error');
            return;
        }
    } else {
        // Fallback: remove locally if not connected
        state.features = state.features.filter(f => f.id !== taskId);
        delete state.boardState[taskId];
        state.selectedCards.delete(taskId);
        
        renderCards();
        updateCounts();
        updateBulkSelectionBar();
        
        console.log('Deleted task locally (no connection):', taskId);
        showNotification(`Task "${taskTitle}" deleted locally (not synced)`, 'warning');
    }
}

function confirmDeleteTask() {
    const taskId = document.getElementById('editTaskId').value;
    closeEditTaskModal();
    deleteTask(taskId);
}

// Bulk Selection Management
function toggleCardSelection(taskId) {
    if (state.selectedCards.has(taskId)) {
        state.selectedCards.delete(taskId);
    } else {
        state.selectedCards.add(taskId);
    }
    updateBulkSelectionBar();
}

function clearSelection() {
    state.selectedCards.clear();
    updateBulkSelectionBar();
    // Update checkboxes
    document.querySelectorAll('.card-checkbox').forEach(cb => cb.checked = false);
}

function updateBulkSelectionBar() {
    const bulkBar = document.getElementById('bulk-selection-bar');
    const selectedCount = document.getElementById('selected-count');
    
    if (state.selectedCards.size > 0 && state.isManualMode) {
        bulkBar.classList.add('active');
        selectedCount.textContent = `${state.selectedCards.size} task${state.selectedCards.size !== 1 ? 's' : ''} selected`;
    } else {
        bulkBar.classList.remove('active');
    }
}

function bulkMoveSelected() {
    if (state.selectedCards.size === 0) return;
    
    const newStatus = prompt('Move selected tasks to status:', 'ready');
    if (!newStatus || !['backlog', 'ready', 'progress', 'testing', 'done'].includes(newStatus)) {
        alert('Invalid status. Use: backlog, ready, progress, testing, or done');
        return;
    }
    
    // Move all selected tasks
    state.selectedCards.forEach(taskId => {
        const feature = state.features.find(f => f.id === taskId);
        if (feature) {
            feature.status = newStatus;
            state.boardState[taskId] = newStatus;
        }
    });
    
    // Sync with WebSocket if connected
    if (state.connected) {
        sendWebSocketMessage({
            type: 'manual_bulk_move',
            taskIds: Array.from(state.selectedCards),
            newStatus: newStatus
        });
    }
    
    // Update UI
    renderCards();
    updateCounts();
    clearSelection();
    
    console.log(`Moved ${state.selectedCards.size} tasks to ${newStatus}`);
}

function bulkDeleteSelected() {
    if (state.selectedCards.size === 0) return;
    
    if (!confirm(`Are you sure you want to delete ${state.selectedCards.size} selected task${state.selectedCards.size !== 1 ? 's' : ''}?`)) return;
    
    const deletedIds = Array.from(state.selectedCards);
    
    // Sync with WebSocket FIRST if connected
    if (state.connected) {
        const success = sendWebSocketMessage({
            type: 'manual_bulk_delete',
            taskIds: deletedIds
        });
        
        if (success) {
            // Remove from local state only after successful WebSocket send
            state.features = state.features.filter(f => !state.selectedCards.has(f.id));
            state.selectedCards.forEach(taskId => {
                delete state.boardState[taskId];
            });
            
            clearSelection();
            renderCards();
            updateCounts();
            
            console.log('Bulk deleted tasks via WebSocket:', deletedIds);
            showNotification(`${deletedIds.length} tasks deleted successfully`, 'success');
        } else {
            showNotification('Failed to delete tasks - WebSocket not ready', 'error');
            return;
        }
    } else {
        // Fallback: remove locally if not connected
        state.features = state.features.filter(f => !state.selectedCards.has(f.id));
        state.selectedCards.forEach(taskId => {
            delete state.boardState[taskId];
        });
        
        clearSelection();
        renderCards();
        updateCounts();
        
        console.log('Bulk deleted tasks locally (no connection):', deletedIds);
        showNotification(`${deletedIds.length} tasks deleted locally (not synced)`, 'warning');
    }
}

// ===== NOTIFICATION AND UI HELPERS =====

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : type === 'warning' ? '#ff9800' : '#2196F3'};
        color: white;
        padding: 15px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 400px;
        font-size: 14px;
        opacity: 0;
        transform: translateX(100%);
        transition: all 0.3s ease;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
        notification.style.opacity = '1';
        notification.style.transform = 'translateX(0)';
    }, 100);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 5000);
}

function updatePendingActionsIndicator(count) {
    // Update mode description to show pending actions
    const modeDescription = document.getElementById('mode-description');
    if (count > 0) {
        modeDescription.textContent = `You control the kanban board - ${count} Claude action${count !== 1 ? 's' : ''} pending`;
    } else {
        modeDescription.textContent = 'You control the kanban board - Claude is blocked';
    }
}

function showPendingActionsDialog(actionCount, actions = []) {
    const message = `Claude has ${actionCount} pending action${actionCount !== 1 ? 's' : ''} to apply. What would you like to do?`;
    
    if (confirm(`${message}\n\nClick OK to apply all pending actions, or Cancel to review them first.`)) {
        // Apply all pending actions
        sendWebSocketMessage({type: 'apply_pending_actions'});
    } else {
        // Show detailed view
        showPendingActionsDetails(actions);
    }
}

function showPendingActionsDetails(actions) {
    let details = "Pending Claude Actions:\n\n";
    actions.forEach((action, index) => {
        details += `${index + 1}. ${action.description}\n`;
        details += `   Type: ${action.type}\n`;
        details += `   Time: ${new Date(action.timestamp).toLocaleTimeString()}\n\n`;
    });
    
    details += "Choose an option:";
    
    const choice = prompt(details + "\n\nType 'apply' to apply all actions, 'clear' to discard them, or 'cancel' to decide later:");
    
    if (choice && choice.toLowerCase() === 'apply') {
        sendWebSocketMessage({type: 'apply_pending_actions'});
    } else if (choice && choice.toLowerCase() === 'clear') {
        if (confirm('Are you sure you want to discard all pending Claude actions? This cannot be undone.')) {
            sendWebSocketMessage({type: 'clear_pending_actions'});
        }
    }
}

function updateBoardFromCurrentState() {
    // Refresh the board state from server
    if (state.connected) {
        sendWebSocketMessage({type: 'get_board_state'});
    }
}

// ===== CLEARING AND REMOVAL FUNCTIONS =====

// Global variable to store current column to clear
let currentColumnToClear = null;

// Clear Board Modal Functions
function showClearBoardModal() {
    document.getElementById('clearBoardModal').style.display = 'block';
}

function closeClearBoardModal() {
    document.getElementById('clearBoardModal').style.display = 'none';
}

function confirmClearBoard() {
    closeClearBoardModal();
    
    console.log('🗑️ Confirming board clear...');
    
    if (state.connected) {
        // Send WebSocket message to server with explicit confirmation
        const message = {
            type: 'clear_kanban',
            confirm: true
        };
        console.log('📤 Sending clear_kanban message:', message);
        
        const success = sendWebSocketMessage(message);
        
        if (success) {
            showNotification('Board clearing requested...', 'info');
            console.log('✅ Clear board message sent to server');
        } else {
            showNotification('Failed to send clear request - WebSocket not ready', 'error');
            console.log('❌ Failed to send clear board message');
        }
    } else {
        showNotification('Cannot clear board - not connected to server', 'error');
        console.log('❌ Clear board failed - no WebSocket connection');
    }
}

// Delete Project Modal Functions
function showDeleteProjectModal() {
    document.getElementById('deleteProjectModal').style.display = 'block';
}

function closeDeleteProjectModal() {
    document.getElementById('deleteProjectModal').style.display = 'none';
}

function confirmDeleteProject() {
    closeDeleteProjectModal();
    
    console.log('🚨 Confirming project deletion...');
    
    if (state.connected) {
        // Send WebSocket message to server with explicit confirmation
        const message = {
            type: 'delete_project',
            confirm: true
        };
        console.log('📤 Sending delete_project message:', message);
        
        const success = sendWebSocketMessage(message);
        
        if (success) {
            showNotification('Project deletion requested...', 'info');
            console.log('✅ Delete project message sent to server');
        } else {
            showNotification('Failed to send delete request - WebSocket not ready', 'error');
            console.log('❌ Failed to send delete project message');
        }
    } else {
        showNotification('Cannot delete project - not connected to server', 'error');
        console.log('❌ Delete project failed - no WebSocket connection');
    }
}

// Clear Column Modal Functions
function showClearColumnModal(columnId) {
    currentColumnToClear = columnId;
    
    // Find column name
    const column = state.columns.find(col => col.id === columnId);
    const columnName = column ? column.name : columnId;
    
    // Count tasks in this column
    const tasksInColumn = state.features.filter(f => (f.status || 'backlog') === columnId);
    const taskCount = tasksInColumn.length;
    
    if (taskCount === 0) {
        showNotification(`No tasks in ${columnName} to clear`, 'info');
        return;
    }
    
    // Update modal message
    const message = `This will permanently delete all ${taskCount} task${taskCount !== 1 ? 's' : ''} in ${columnName}.
                     <br><br><strong>This action cannot be undone!</strong>`;
    document.getElementById('clearColumnMessage').innerHTML = message;
    
    document.getElementById('clearColumnModal').style.display = 'block';
}

function closeClearColumnModal() {
    document.getElementById('clearColumnModal').style.display = 'none';
    currentColumnToClear = null;
}

function confirmClearColumn() {
    if (!currentColumnToClear) return;
    
    closeClearColumnModal();
    
    if (state.connected) {
        // Send WebSocket message to server
        sendWebSocketMessage({
            type: 'clear_column',
            status: currentColumnToClear,
            confirm: true
        });
        showNotification(`Column clearing requested...`, 'info');
    } else {
        showNotification('Cannot clear column - not connected to server', 'error');
    }
    
    currentColumnToClear = null;
}

// Enhanced delete task function with confirmation
function deleteTaskWithConfirmation(taskId) {
    const feature = state.features.find(f => f.id === taskId);
    if (!feature) return;
    
    if (confirm(`Are you sure you want to delete "${feature.title}"?\n\nThis action cannot be undone.`)) {
        deleteTask(taskId);
    }
}

// Enhanced bulk delete with better confirmation
function bulkDeleteSelectedEnhanced() {
    if (state.selectedCards.size === 0) return;
    
    const taskCount = state.selectedCards.size;
    const taskList = Array.from(state.selectedCards).map(taskId => {
        const feature = state.features.find(f => f.id === taskId);
        return feature ? feature.title : taskId;
    }).slice(0, 5); // Show first 5 tasks
    
    let confirmMessage = `Are you sure you want to delete ${taskCount} selected task${taskCount !== 1 ? 's' : ''}?\n\n`;
    confirmMessage += taskList.join('\n');
    if (taskCount > 5) {
        confirmMessage += `\n... and ${taskCount - 5} more`;
    }
    confirmMessage += '\n\nThis action cannot be undone.';
    
    if (confirm(confirmMessage)) {
        bulkDeleteSelected();
    }
}

// Handle server responses for clearing/removal operations
function handleClearingResponse(message) {
    switch (message.type) {
        case 'clear_kanban_response':
            console.log('🗑️ Clear kanban response:', message);
            if (message.success) {
                showNotification('Kanban board cleared successfully', 'success');
                // Clear local state immediately
                state.features = [];
                state.boardState = {};
                // Update UI immediately
                createColumns();
                updateCounts();
                showStartupMessage();
                console.log('✅ Board cleared successfully, UI updated');
            } else {
                showNotification(`Failed to clear board: ${message.message || 'Unknown error'}`, 'error');
                console.log('❌ Board clear failed:', message.message);
            }
            break;
            
        case 'delete_project_response':
            console.log('🚨 Delete project response:', message);
            if (message.success) {
                showNotification('Project deleted successfully', 'success');
                // Reset UI to initial state completely
                state.features = [];
                state.boardState = {};
                state.projectTitle = "Dynamic Project";
                state.selectedCards.clear();
                document.querySelector('.header h1').textContent = '🚀 Dynamic Kanban Board';
                // Clear any selection state
                updateBulkSelectionBar();
                // Reset UI completely
                createColumns();
                updateCounts();
                showStartupMessage();
                console.log('✅ Project deletion UI reset complete');
            } else {
                showNotification(`Failed to delete project: ${message.message || 'Unknown error'}`, 'error');
                console.log('❌ Project deletion failed:', message.message);
            }
            break;
            
        case 'clear_column_response':
            if (message.success) {
                const columnName = message.columnName || message.status;
                showNotification(`${columnName} column cleared successfully`, 'success');
                // Force refresh board state
                setTimeout(() => {
                    sendWebSocketMessage({type: 'get_board_state'});
                }, 500);
            } else {
                showNotification(`Failed to clear column: ${message.message || 'Unknown error'}`, 'error');
            }
            break;
            
        case 'remove_feature_response':
            if (message.success) {
                showNotification('Task removed successfully', 'success');
            } else {
                showNotification(`Failed to remove task: ${message.message || 'Unknown error'}`, 'error');
            }
            break;
            
        case 'remove_features_response':
            if (message.success) {
                showNotification(`${message.removedCount || 'Multiple'} tasks removed successfully`, 'success');
            } else {
                showNotification(`Failed to remove tasks: ${message.message || 'Unknown error'}`, 'error');
            }
            break;
    }
}

// Close modals when clicking outside
window.addEventListener('click', (e) => {
    const modals = ['clearBoardModal', 'deleteProjectModal', 'clearColumnModal'];
    modals.forEach(modalId => {
        const modal = document.getElementById(modalId);
        if (e.target === modal) {
            modal.style.display = 'none';
            if (modalId === 'clearColumnModal') {
                currentColumnToClear = null;
            }
        }
    });
});

// Keyboard shortcuts for quick actions
document.addEventListener('keydown', (e) => {
    // Only handle shortcuts if no modal is open and no input is focused
    if (document.querySelector('.modal[style*="block"]') || 
        document.activeElement.tagName === 'INPUT' || 
        document.activeElement.tagName === 'TEXTAREA') {
        return;
    }
    
    // Ctrl+Shift+C - Clear Board
    if (e.ctrlKey && e.shiftKey && e.key === 'C') {
        e.preventDefault();
        showClearBoardModal();
    }
    
    // Ctrl+Shift+D - Delete Project
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        showDeleteProjectModal();
    }
    
    // Escape key - Close any open confirmation modal
    if (e.key === 'Escape') {
        closeClearBoardModal();
        closeDeleteProjectModal();
        closeClearColumnModal();
    }
});

// Initialize when page loads
document.addEventListener('DOMContentLoaded', initializeBoard);