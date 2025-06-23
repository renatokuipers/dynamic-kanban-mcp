# Dynamic Kanban MCP Server v3.0

A production-ready Model Context Protocol (MCP) server that provides real-time kanban project management with bidirectional synchronization between Claude AI and an interactive HTML interface. Features dual-mode operation with autonomous and manual control.

## Features

### Core Functionality
- **Real-time Collaboration**: Bidirectional sync between Claude AI and HTML UI via WebSocket
- **Universal Project Support**: Works with web apps, mobile apps, APIs, desktop software, and more
- **Pre-made Interface**: No setup delays - open `kanban-board.html` and start immediately
- **Dual-Mode Operation**: Switch between Autonomous (Claude controls) and Manual (user controls) modes
- **Mode Protection**: Queuing system prevents conflicts when switching between control modes

### Advanced Capabilities
- **Drag & Drop Interface**: Move cards in browser with instant Claude synchronization
- **Bulk Operations**: Select and manage multiple tasks simultaneously in manual mode
- **Task Management**: Create, edit, delete tasks with comprehensive form validation
- **Session Tracking**: Development session management with time tracking
- **Atomic Operations**: Thread-safe state management with data integrity and backup/restore
- **Auto-reconnection**: Robust WebSocket connection with exponential backoff and fallback ports
- **Comprehensive Validation**: Pydantic models with circular dependency detection and field validation
- **Real-time Notifications**: Toast notifications for all operations and status changes

## Quick Start

### 1. Install Dependencies
```bash
pip install websockets pydantic
```

### 2. Start the Server
```bash
# Start the MCP server with WebSocket support
python3 mcp-kanban-server.py
```

### 3. Open the Interface
```bash
# Open kanban-board.html in your browser
# UI will auto-connect to WebSocket on port 8765
open kanban-board.html
```

### 4. MCP Integration
Add to your Claude MCP configuration (`mcp-config.json`):
```json
{
  "mcpServers": {
    "dynamic-kanban": {
      "command": "python3",
      "args": ["./mcp-kanban-server.py"],
      "env": {},
      "description": "Dynamic Kanban MCP Server v3.0 - Real-time project management with WebSocket sync"
    }
  }
}
```

## Architecture

### Core Components

- **`mcp-kanban-server.py`** - Main MCP server with JSON-RPC 2.0 compliance and tool handlers
- **`kanban_controller.py`** - Core logic with WebSocket support, mode management, and atomic operations
- **`mcp_protocol.py`** - Proper MCP protocol implementation with JSON-RPC 2.0 support
- **`models.py`** - Comprehensive Pydantic data models with validation and enums
- **`config.py`** - Centralized configuration management with validation helpers
- **`kanban-board.html`** - Pre-made interactive UI with dual-mode support
- **`kanban-board.js`** - Separated JavaScript with WebSocket handling and real-time updates

### Mode System

The server operates in two distinct modes:

#### Autonomous Mode (Default)
- Claude AI has full control of the kanban board
- Users can view and monitor progress in real-time
- All MCP tool calls execute immediately
- Drag & drop in UI syncs changes to Claude

#### Manual Mode
- Users have full control via the web interface
- Claude's actions are queued and blocked
- Users can create, edit, delete, and move tasks
- Bulk operations for multiple task management
- Mode switch applies or clears queued Claude actions

### Data Models

All data structures use comprehensive Pydantic validation:
- **Task** - Complete task model with priority, effort, status, dependencies, and acceptance criteria
- **ProjectConfig** - Project metadata with validation and timestamps
- **BoardConfig** - Kanban board layout and customizable columns
- **ProgressData** - Complete project state with activity logging
- **ActivityEntry** - Detailed activity tracking with multiple event types
- **DependencyValidation** - Dependency checking with circular detection
- **BoardState** - Real-time board state for WebSocket synchronization

## MCP Tools

### Project Management
- **`create_project`** - Initialize new kanban project with metadata and real-time UI setup
- **`add_feature`** - Add tasks with comprehensive validation and dependency checking
- **`configure_board`** - Customize board layout, columns, and styling
- **`import_features`** - Bulk import features from JSON with validation and error handling

### Kanban Operations
- **`kanban_status`** - Board statistics, health metrics, and connection status
- **`kanban_get_ready_tasks`** - List all tasks ready for development (dependencies met)
- **`kanban_get_next_task`** - Get highest priority task ready for development
- **`kanban_move_card`** - Change task status with dependency validation and real-time sync
- **`kanban_update_progress`** - Add progress notes with timestamp tracking

### Development Workflow
- **`kanban_start_session`** - Begin development session with activity tracking
- **`kanban_end_session`** - End session with duration summary and task completion
- **`analyze_task_requirements`** - Generate detailed implementation plans with file suggestions
- **`get_task_details`** - Retrieve comprehensive task information and development history

### Validation & Quality Assurance
- **`validate_dependencies`** - Check individual task dependencies and circular detection
- **`validate_project_dependencies`** - Project-wide dependency validation and health check

### Mode Management Features
All tools respect the current mode (Autonomous/Manual):
- **Autonomous Mode**: Tools execute immediately with real-time UI updates
- **Manual Mode**: Claude actions are queued with detailed status messages
- **Mode Switching**: Queued actions can be applied or cleared when switching modes

## Workflow Examples

### Autonomous Mode (Claude Controls)
1. **Claude**: `create_project` - Setup project structure and initialize WebSocket
2. **Claude**: `add_feature` - Add tasks with automatic validation
3. **Claude**: `kanban_move_card` - Update task status as development progresses
4. **User**: Opens `kanban-board.html` to monitor progress in real-time
5. **User**: Can drag cards in UI - changes sync instantly back to Claude
6. **Claude**: `kanban_status` - Get real-time updates on project progress

### Manual Mode (User Controls)
1. **User**: Switch to Manual Mode via UI toggle
2. **User**: Create, edit, delete tasks using web forms
3. **User**: Bulk select and move multiple tasks
4. **User**: Drag and drop cards between columns
5. **Claude**: Attempts to modify board - actions are queued with notifications
6. **User**: Switch back to Autonomous Mode - choose to apply or clear queued actions

### Development Session Workflow
1. **Claude**: `kanban_start_session` - Begin development session
2. **Claude**: `kanban_get_next_task` - Get highest priority ready task
3. **Claude**: `kanban_move_card` to "progress" - Start development
4. **Claude**: `kanban_update_progress` - Add progress notes during development
5. **Claude**: `kanban_move_card` to "testing" - Move to testing phase
6. **Claude**: `kanban_move_card` to "done" - Complete task
7. **Claude**: `kanban_end_session` - End session with summary

## Configuration

### Default Board Columns
```json
{
  "columns": [
    {"id": "backlog", "name": "📋 Backlog", "emoji": "📋"},
    {"id": "ready", "name": "⚡ Ready", "emoji": "⚡"},
    {"id": "progress", "name": "🔧 In Progress", "emoji": "🔧"},
    {"id": "testing", "name": "🧪 Testing", "emoji": "🧪"},
    {"id": "done", "name": "✅ Done", "emoji": "✅"}
  ]
}
```

### Task Properties & Validation

#### Priority Levels
- **low** - Nice to have features
- **medium** - Standard development tasks (default)
- **high** - Important features requiring attention
- **critical** - Urgent, blocking issues

#### Effort Estimates
- **xs** - Extra Small (< 1 hour)
- **s** - Small (2-4 hours)
- **m** - Medium (Half day) - default
- **l** - Large (Full day)
- **xl** - Extra Large (Multiple days)

#### Epic Categories
- **general** - Default category for uncategorized tasks
- **frontend** - UI and client-side development
- **backend** - Server-side logic and APIs
- **api** - API development and integration
- **database** - Database design and queries
- **auth** - Authentication and authorization
- **testing** - Testing, QA, and validation
- **deployment** - DevOps, CI/CD, and deployment

#### Development Stages (1-6)
- **Stage 1** - Foundation & Core Features
- **Stage 2** - Feature Development
- **Stage 3** - Integration & Enhancement
- **Stage 4** - Advanced Features
- **Stage 5** - Optimization & Polish
- **Stage 6** - Release & Maintenance

#### Other Properties
- **Dependencies**: Array of task IDs that must complete first (validates against existing tasks)
- **Acceptance Criteria**: Definition of done (default: "Feature works as described")
- **Status**: Current kanban column (backlog, ready, progress, testing, done)

### Environment Variables
- `KANBAN_WEBSOCKET_PORT` - WebSocket server port (default: 8765)
- `KANBAN_WEBSOCKET_HOST` - WebSocket server host (default: 0.0.0.0)
- `KANBAN_RECONNECT_DELAY` - Reconnection delay in milliseconds (default: 3000)
- `KANBAN_MAX_RECONNECTS` - Maximum reconnection attempts (default: 10)

### File Structure
- `kanban-progress.json` - Main data file with board state and activity
- `features.json` - Feature definitions for persistence
- `kanban-board.html` - Pre-made UI (always available)
- `kanban-board.js` - JavaScript functionality

## Error Handling & Resilience

### Data Integrity
- **Circular Dependencies**: Comprehensive detection with detailed cycle reporting
- **Dependency Validation**: Ensures all task dependencies reference existing tasks
- **Data Validation**: Pydantic models with field-specific error messages
- **Atomic Operations**: Backup/restore mechanism prevents data corruption
- **Duplicate Prevention**: UUID-based task IDs prevent conflicts

### Network Resilience
- **Connection Recovery**: Automatic WebSocket reconnection with exponential backoff
- **Port Conflicts**: Automatic fallback to available ports (8765-8864 range)
- **Connection Status**: Real-time connection indicators and notifications
- **Graceful Degradation**: UI remains functional during disconnections

### Mode Management
- **Action Queuing**: Claude actions queued safely during Manual Mode
- **State Synchronization**: Prevents conflicts between Claude and user actions
- **Transaction Safety**: Mode switches with validation and user confirmation

## User Interface Features

### Dual-Mode Interface
- **Mode Toggle**: Switch between Autonomous and Manual modes
- **Visual Indicators**: Clear mode status with color-coded indicators
- **Pending Actions**: Notification system for queued Claude actions

### Manual Mode Capabilities
- **Task Creation**: Full-featured forms with validation
- **Task Editing**: In-place editing with comprehensive field support
- **Bulk Operations**: Multi-select with bulk move and delete
- **Drag & Drop**: Intuitive card movement between columns

### Real-time Features
- **Live Updates**: Changes appear instantly across all connections
- **Connection Status**: Visual WebSocket connection indicators
- **Activity Feed**: Real-time activity log with timestamps
- **Progress Tracking**: Live progress bars and completion statistics

## Requirements

### System Requirements
- **Python**: 3.7+ (recommended: 3.9+)
- **Dependencies**: `websockets`, `pydantic`
- **Browser**: Modern web browser with WebSocket support
- **Network**: Port 8765 available (or automatic fallback)

### Installation
```bash
# Install required dependencies
pip install websockets pydantic

# No additional setup required
# UI is pre-made and ready to use
```

## Benefits

### Enterprise Features
- **Production Ready**: Comprehensive error handling and validation
- **Scalable Architecture**: Modular design with separated concerns
- **Data Integrity**: Atomic operations with backup/restore
- **Real-time Collaboration**: WebSocket synchronization with conflict resolution

### Developer Experience
- **Immediate Start**: Pre-made UI with zero configuration
- **Comprehensive Validation**: Pydantic models with clear error messages
- **Flexible Modes**: Switch between AI and manual control seamlessly
- **Rich Tooling**: 15+ MCP tools for complete project management

### User Experience
- **Intuitive Interface**: Drag & drop with visual feedback
- **Real-time Updates**: Changes appear instantly everywhere
- **Robust Connection**: Auto-reconnection with status indicators
- **Accessibility**: Responsive design for desktop and mobile

---