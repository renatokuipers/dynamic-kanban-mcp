#!/usr/bin/env python3
"""
Dynamic Kanban MCP Server
Proper MCP implementation with real-time WebSocket support
"""

import json
import os
import sys
import uuid
import asyncio
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from mcp_protocol import MCPServer, timeout_protection
from kanban_controller import KanbanController
from config import CONFIG

class KanbanMCPServer:
    """Dynamic Kanban MCP Server with real-time synchronization"""
    
    def __init__(self, progress_file=None):
        self.kanban = KanbanController(progress_file, mcp_server=self)
        self.server = MCPServer(CONFIG.MCP_SERVER_NAME, CONFIG.MCP_SERVER_VERSION)
        self.project_config = None
        self.board_config = {
            "title": "Dynamic Kanban Board",
            "subtitle": "Ready for your project",
            "columns": CONFIG.DEFAULT_COLUMNS.copy()
        }
        self.setup_tools()
        
        # Start WebSocket server in background
        self.kanban.start_websocket_server_thread()
        
    def setup_tools(self):
        """Setup all MCP tools with proper schemas"""
        
        # Project Management Tools
        self.server.add_tool(
            "create_project",
            "Create a new kanban project with custom configuration",
            {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Name of the project"},
                    "project_type": {"type": "string", "description": "Type of project (web, mobile, api, etc.)"},
                    "description": {"type": "string", "description": "Project description"}
                },
                "required": ["project_name", "project_type"],
                "additionalProperties": False
            },
            self.handle_create_project
        )
        
        self.server.add_tool(
            "add_feature",
            "Add a new feature/task to the kanban board",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Feature title"},
                    "description": {"type": "string", "description": "Feature description"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Priority level"},
                    "effort": {"type": "string", "enum": ["xs", "s", "m", "l", "xl"], "description": "Effort estimate"},
                    "epic": {"type": "string", "description": "Epic category"},
                    "stage": {"type": "integer", "description": "Stage number"},
                    "dependencies": {"type": "array", "items": {"type": "string"}, "description": "List of dependency task IDs"},
                    "acceptance_criteria": {"type": "string", "description": "Acceptance criteria"}
                },
                "required": ["title", "description", "priority", "effort"],
                "additionalProperties": False
            },
            self.handle_add_feature
        )
        
        # Note: UI is now pre-made and always available at kanban-board.html
        # No need to generate UI dynamically anymore
        
        self.server.add_tool(
            "configure_board",
            "Configure board layout and columns",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Board title"},
                    "subtitle": {"type": "string", "description": "Board subtitle"},
                    "columns": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                                "emoji": {"type": "string"}
                            },
                            "required": ["id", "name", "emoji"]
                        }
                    }
                },
                "additionalProperties": False
            },
            self.handle_configure_board
        )
        
        self.server.add_tool(
            "import_features",
            "Import features from JSON configuration",
            {
                "type": "object",
                "properties": {
                    "features_json": {"type": "string", "description": "JSON string containing features array"}
                },
                "required": ["features_json"],
                "additionalProperties": False
            },
            self.handle_import_features
        )
        
        # Kanban Management Tools
        self.server.add_tool(
            "kanban_status",
            "Get current kanban board status and statistics",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            self.handle_kanban_status
        )
        
        self.server.add_tool(
            "kanban_get_ready_tasks",
            "Get all tasks that are ready to work on (dependencies met)",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            self.handle_get_ready_tasks
        )
        
        self.server.add_tool(
            "kanban_get_next_task",
            "Get the highest priority task ready for development",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            self.handle_get_next_task
        )
        
        self.server.add_tool(
            "kanban_move_card",
            "Move a kanban card to a new status column",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to move"},
                    "new_status": {"type": "string", "enum": ["backlog", "ready", "progress", "testing", "done"], "description": "New status for the task"},
                    "notes": {"type": "string", "description": "Optional notes about the move"}
                },
                "required": ["task_id", "new_status"],
                "additionalProperties": False
            },
            self.handle_move_card
        )
        
        self.server.add_tool(
            "kanban_update_progress",
            "Add a progress update note to a task",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to update"},
                    "notes": {"type": "string", "description": "Progress notes"}
                },
                "required": ["task_id", "notes"],
                "additionalProperties": False
            },
            self.handle_update_progress
        )
        
        self.server.add_tool(
            "kanban_start_session",
            "Start a development session",
            {
                "type": "object",
                "properties": {
                    "session_name": {"type": "string", "description": "Name for the development session"}
                },
                "required": ["session_name"],
                "additionalProperties": False
            },
            self.handle_start_session
        )
        
        self.server.add_tool(
            "kanban_end_session",
            "End the current development session",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            self.handle_end_session
        )
        
        # Development Tools
        self.server.add_tool(
            "analyze_task_requirements",
            "Analyze a task's requirements and create implementation plan",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to analyze"}
                },
                "required": ["task_id"],
                "additionalProperties": False
            },
            self.handle_analyze_task
        )
        
        self.server.add_tool(
            "get_task_details",
            "Get detailed information about a specific task",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task"}
                },
                "required": ["task_id"],
                "additionalProperties": False
            },
            self.handle_get_task_details
        )
        
        self.server.add_tool(
            "validate_dependencies",
            "Check if a task's dependencies are properly completed and detect circular dependencies",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to validate"}
                },
                "required": ["task_id"],
                "additionalProperties": False
            },
            self.handle_validate_dependencies
        )
        
        self.server.add_tool(
            "validate_project_dependencies",
            "Check the entire project for circular dependencies and missing dependencies",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False
            },
            self.handle_validate_project_dependencies
        )
        
        # Clearing and Removal Tools
        self.server.add_tool(
            "clear_kanban",
            "Clear all tasks from the kanban board while preserving project structure",
            {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "description": "Confirmation that user wants to clear all tasks", "default": False}
                },
                "additionalProperties": False
            },
            self.handle_clear_kanban
        )
        
        self.server.add_tool(
            "delete_project",
            "Delete the entire project and all associated data",
            {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "description": "Confirmation that user wants to delete the project", "default": False}
                },
                "additionalProperties": False
            },
            self.handle_delete_project
        )
        
        self.server.add_tool(
            "remove_feature",
            "Remove a specific feature/task from the kanban board",
            {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "ID of the task to remove"},
                    "force": {"type": "boolean", "description": "Force removal even if other tasks depend on this", "default": False}
                },
                "required": ["task_id"],
                "additionalProperties": False
            },
            self.handle_remove_feature
        )
        
        self.server.add_tool(
            "remove_features",
            "Remove multiple features/tasks from the kanban board",
            {
                "type": "object",
                "properties": {
                    "task_ids": {"type": "array", "items": {"type": "string"}, "description": "List of task IDs to remove"},
                    "force": {"type": "boolean", "description": "Force removal even if dependencies exist", "default": False}
                },
                "required": ["task_ids"],
                "additionalProperties": False
            },
            self.handle_remove_features
        )
        
        self.server.add_tool(
            "clear_column",
            "Clear all tasks from a specific status column",
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["backlog", "ready", "progress", "testing", "done"], "description": "Status column to clear"},
                    "confirm": {"type": "boolean", "description": "Confirmation to clear the column", "default": False}
                },
                "required": ["status"],
                "additionalProperties": False
            },
            self.handle_clear_column
        )
        
        self.server.add_tool(
            "reset_board",
            "Reset the kanban board to initial empty state",
            {
                "type": "object",
                "properties": {
                    "confirm": {"type": "boolean", "description": "Confirmation to reset the board", "default": False}
                },
                "additionalProperties": False
            },
            self.handle_reset_board
        )

    # Project Management Tool Handlers
    def handle_create_project(self, arguments: Dict[str, Any]) -> str:
        """Create a new kanban project"""
        project_name = arguments["project_name"]
        project_type = arguments["project_type"]
        description = arguments.get("description", "")
        
        self.project_config = {
            "project_name": project_name,
            "project_type": project_type,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "id": str(uuid.uuid4())[:8]
        }
        
        # Update board title
        self.board_config["title"] = f"🚀 {project_name} Kanban"
        self.board_config["subtitle"] = f"{project_type.title()} Project - {description}" if description else f"{project_type.title()} Project"
        
        # Initialize empty features list
        self.kanban.features = []
        
        # Initialize progress file
        progress = self.kanban.load_progress()
        self.kanban.save_progress(progress)
        
        return f"""✅ Project Created: **{project_name}**

**Project Details:**
- Type: {project_type}
- Description: {description}
- ID: {self.project_config['id']}
- Created: {self.project_config['created_at']}

**Real-time Features:**
- WebSocket server running on port {self.kanban.websocket_port}
- Supports bidirectional sync between Claude and HTML UI
- Automatic state updates for all connected clients

**Next Steps:**
1. Use `add_feature` to add tasks to your kanban board
2. Use `configure_board` to customize columns if needed
3. Open `kanban-board.html` in your browser for real-time monitoring
4. Use `import_features` to bulk import from JSON

🎯 Ready to start adding features to your project!
📋 UI is pre-made and ready: Open kanban-board.html in your browser now!"""
    
    def handle_add_feature(self, arguments: Dict[str, Any]) -> str:
        """Add a new feature to the kanban board"""
        # Generate feature ID using UUID for guaranteed uniqueness
        feature_id = f"feature-{str(uuid.uuid4())[:8]}"
        
        # Create complete task data for validation
        task_data = {
            "id": feature_id,
            "title": arguments["title"],
            "description": arguments["description"],
            "priority": arguments["priority"],
            "effort": arguments["effort"],
            "epic": arguments.get("epic", "general"),
            "stage": arguments.get("stage", 1),
            "status": "backlog",
            "dependencies": arguments.get("dependencies", []),
            "acceptance": arguments.get("acceptance_criteria", "Feature works as described")
        }
        
        # Validate complete task data
        validation_errors = CONFIG.validate_task_data(task_data)
        if validation_errors:
            return f"❌ Invalid task data:\n" + "\n".join(f"  • {error}" for error in validation_errors)
        
        # Validate dependencies if provided
        dependencies = arguments.get("dependencies", [])
        if dependencies:
            dep_validation = self.kanban.validate_new_task_dependencies(feature_id, dependencies)
            if not dep_validation.valid:
                error_msg = f"❌ Dependency validation failed for task '{arguments['title']}':\n"
                if dep_validation.missing:
                    error_msg += f"  • Missing dependencies: {', '.join(dep_validation.missing)}\n"
                if dep_validation.circular:
                    error_msg += f"  • Circular dependencies detected:\n"
                    for cycle in dep_validation.circular:
                        error_msg += f"    - {' → '.join(cycle)}\n"
                return error_msg
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            # Queue the action for later
            self.kanban.queue_claude_action(
                "add_feature",
                task_data,
                f"Add feature: {arguments['title']}"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot add feature while user has control of the kanban board.

**Queued Action:** Add feature "{arguments['title']}"
- Priority: {arguments['priority']}
- Effort: {arguments['effort']}
- Epic: {arguments.get('epic', 'general')}

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This action will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can add this feature manually."""
        
        new_feature = task_data
        
        self.kanban.features.append(new_feature)
        
        # Save features to file for persistence
        self.kanban._save_features_to_file()
        
        # Update progress file (this will trigger WebSocket notification)
        progress = self.kanban.load_progress()
        progress["boardState"][feature_id] = "backlog"
        self.kanban.save_progress(progress)
        
        return f"""✅ Feature Added: **{new_feature['title']}**

**Feature Details:**
- ID: {feature_id}
- Priority: {new_feature['priority']}
- Effort: {new_feature['effort']}
- Epic: {new_feature['epic']}
- Stage: {new_feature['stage']}
- Dependencies: {', '.join(new_feature['dependencies']) if new_feature['dependencies'] else 'None'}

**Description:** {new_feature['description']}
**Acceptance Criteria:** {new_feature['acceptance']}

🎯 Feature added to backlog! All connected UIs will update automatically."""
    
    # UI is now pre-made and always available - no generation needed!
    
    def handle_configure_board(self, arguments: Dict[str, Any]) -> str:
        """Configure board layout and columns"""
        if "title" in arguments:
            self.board_config["title"] = arguments["title"]
        if "subtitle" in arguments:
            self.board_config["subtitle"] = arguments["subtitle"]
        if "columns" in arguments:
            self.board_config["columns"] = arguments["columns"]
        
        return f"""✅ Board Configuration Updated

**Current Configuration:**
- Title: {self.board_config['title']}
- Subtitle: {self.board_config['subtitle']}
- Columns: {len(self.board_config['columns'])} columns configured

**Columns:**
{chr(10).join([f"  {col['emoji']} {col['name']} (id: {col['id']})" for col in self.board_config['columns']])}

🎯 The pre-made UI at kanban-board.html will automatically use these updated settings!"""
    
    @timeout_protection(45.0)  # Longer timeout for large imports
    async def handle_import_features(self, arguments: Dict[str, Any]) -> str:
        """Import features from JSON configuration"""
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            self.kanban.queue_claude_action(
                "import_features",
                {"features_json": arguments["features_json"]},
                f"Import features from JSON data"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot import features while user has control of the kanban board.

**Queued Action:** Import features from JSON configuration

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This import will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can import features manually."""
        
        try:
            # Use async JSON parsing for large files
            loop = asyncio.get_event_loop()
            features_data = await loop.run_in_executor(None, json.loads, arguments["features_json"])
            
            if not isinstance(features_data, list):
                return "❌ Features JSON must be an array of feature objects"
            
            imported_count = 0
            for feature_data in features_data:
                # Validate required fields
                if not all(field in feature_data for field in ["id", "title", "description"]):
                    continue
                
                # Set defaults for missing fields
                feature = {
                    "id": feature_data["id"],
                    "title": feature_data["title"],
                    "description": feature_data["description"],
                    "priority": feature_data.get("priority", "medium"),
                    "effort": feature_data.get("effort", "m"),
                    "epic": feature_data.get("epic", "general"),
                    "stage": feature_data.get("stage", 1),
                    "status": feature_data.get("status", "backlog"),
                    "dependencies": feature_data.get("dependencies", []),
                    "acceptance": feature_data.get("acceptance", "Feature works as described")
                }
                
                self.kanban.features.append(feature)
                imported_count += 1
            
            # Save features to file for persistence (async)
            await loop.run_in_executor(None, self.kanban._save_features_to_file)
            
            # Update progress file (this will trigger WebSocket notification)
            progress = self.kanban.load_progress()
            for feature in self.kanban.features:
                if feature["id"] not in progress["boardState"]:
                    progress["boardState"][feature["id"]] = feature["status"]
            self.kanban.save_progress(progress)
            
            return f"""✅ Features Imported Successfully

**Import Summary:**
- Total features imported: {imported_count}
- Total features in project: {len(self.kanban.features)}

**Real-time Sync:**
- All connected UIs updated automatically
- WebSocket clients notified of new features

**Next Steps:**
1. Use `kanban_status` to see the current board state
2. Open kanban-board.html in your browser to view the real-time UI
3. Start working on features with `kanban_get_next_task`

🎯 Your project is now ready for development with real-time collaboration!"""
            
        except json.JSONDecodeError as e:
            return f"❌ Invalid JSON format: {str(e)}"

    # Kanban Management Tool Handlers
    def handle_kanban_status(self, arguments: Dict[str, Any]) -> str:
        """Get current kanban board status"""
        progress = self.kanban.load_progress()
        board_state = progress["boardState"]
        
        # Count features by status
        status_counts = {}
        for status in board_state.values():
            status_counts[status] = status_counts.get(status, 0) + 1
            
        total = len(self.kanban.features)
        done = status_counts.get("done", 0)
        progress_count = status_counts.get("progress", 0)
        
        # Get next task
        next_task = self.kanban.get_next_task()
        next_task_info = f"{next_task['title']} (Stage {next_task['stage']}, {next_task['priority']} priority)" if next_task else "No tasks ready"
        
        # Current session info
        session_info = ""
        if progress.get("metadata", {}).get("currentSession"):
            session = progress["metadata"]["currentSession"]
            session_info = f"\n🚀 Active Session: {session['name']}"
        
        project_title = self.project_config.get('project_name', 'Dynamic Project') if self.project_config else 'Dynamic Project'
        completion_percent = f"({done/total*100:.1f}%)" if total > 0 else "(0.0%)"
        
        websocket_status = f"\n🔗 WebSocket Clients: {len(self.kanban.websocket_clients)} connected"
        
        return f"""🚀 {project_title} Development Status
{'='*50}
📊 Total Features: {total}
✅ Completed: {done} {completion_percent}
🔧 In Progress: {progress_count}
📋 Backlog: {status_counts.get('backlog', 0)}
⚡ Ready: {status_counts.get('ready', 0)}
🧪 Testing: {status_counts.get('testing', 0)}

🎯 Next Task: {next_task_info}{session_info}{websocket_status}

Recent Activity: {len(progress.get('activity', []))} actions logged"""

    def handle_get_ready_tasks(self, arguments: Dict[str, Any]) -> str:
        """Get all ready tasks"""
        ready_tasks = self.kanban.get_ready_tasks()
        
        if not ready_tasks:
            return "No tasks are currently ready for development."
        
        task_list = "📋 Ready Tasks:\n\n"
        for task in ready_tasks:
            task_list += f"🎯 **{task['id']}**: {task['title']}\n"
            task_list += f"   Stage {task['stage']} | {task['priority']} priority | {task['effort']} effort\n"
            task_list += f"   Epic: {task['epic']}\n"
            task_list += f"   Description: {task['description']}\n\n"
            
        return task_list

    def handle_get_next_task(self, arguments: Dict[str, Any]) -> str:
        """Get next priority task"""
        next_task = self.kanban.get_next_task()
        
        if not next_task:
            return "No tasks are ready for development."
            
        return f"""🎯 Next Priority Task: **{next_task['id']}**

**Title**: {next_task['title']}
**Stage**: {next_task['stage']}
**Priority**: {next_task['priority']}
**Effort**: {next_task['effort']}
**Epic**: {next_task['epic']}
**Description**: {next_task['description']}
**Dependencies**: {', '.join(next_task['dependencies']) if next_task['dependencies'] else 'None'}
**Acceptance Criteria**: {next_task['acceptance']}

This task is ready to move to 'progress' and begin implementation.
All UI clients will see updates in real-time when you move this card."""

    def handle_move_card(self, arguments: Dict[str, Any]) -> str:
        """Move a kanban card"""
        task_id = arguments["task_id"]
        new_status = arguments["new_status"]
        notes = arguments.get("notes", "")
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            # Get task info for better messaging
            feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
            task_title = feature["title"] if feature else task_id
            
            # Queue the action for later
            self.kanban.queue_claude_action(
                "move_card",
                {"task_id": task_id, "new_status": new_status, "notes": notes},
                f"Move '{task_title}' to {new_status}"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot move task while user has control of the kanban board.

**Queued Action:** Move "{task_title}" to {new_status}
- Current task: {task_id}
- Target status: {new_status}
- Notes: {notes if notes else 'None'}

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This action will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can move the card manually via drag & drop."""
        
        success = self.kanban.move_card(task_id, new_status, notes)
        
        if success:
            # Get task info for confirmation
            feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
            task_title = feature["title"] if feature else task_id
            
            result = f"✅ Successfully moved '{task_title}' to {new_status}"
            if notes:
                result += f"\n📝 Notes: {notes}"
            result += f"\n🔗 All connected UIs updated automatically"
                
            return result
        else:
            return f"❌ Failed to move {task_id} to {new_status}. Check dependencies and task existence."

    def handle_update_progress(self, arguments: Dict[str, Any]) -> str:
        """Update task progress"""
        task_id = arguments["task_id"]
        notes = arguments["notes"]
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            # Get task info for better messaging
            feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
            task_title = feature["title"] if feature else task_id
            
            # Queue the action for later
            self.kanban.queue_claude_action(
                "update_progress",
                {"task_id": task_id, "notes": notes},
                f"Update progress for '{task_title}': {notes[:50]}{'...' if len(notes) > 50 else ''}"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot update task progress while user has control of the kanban board.

**Queued Action:** Update progress for "{task_title}"
- Task: {task_id}
- Progress notes: {notes}

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This progress update will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can add progress notes manually."""
        
        self.kanban.update_progress(task_id, notes)
        
        return f"📝 Progress updated for {task_id}: {notes}\n🔗 All connected UIs updated automatically"

    def handle_start_session(self, arguments: Dict[str, Any]) -> str:
        """Start development session"""
        session_name = arguments["session_name"]
        
        self.kanban.start_development_session(session_name)
        
        return f"🚀 Started development session: {session_name}\n🔗 Session info updated in all connected UIs"

    def handle_end_session(self, arguments: Dict[str, Any]) -> str:
        """End development session"""
        progress = self.kanban.load_progress()
        session_name = progress.get("metadata", {}).get("currentSession", {}).get("name", "Unknown")
        
        self.kanban.end_development_session()
        
        return f"✅ Ended development session: {session_name}\n🔗 Session status updated in all connected UIs"

    def handle_analyze_task(self, arguments: Dict[str, Any]) -> str:
        """Analyze task requirements"""
        task_id = arguments["task_id"]
        
        # Find the task
        feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
        if not feature:
            return f"❌ Task {task_id} not found"
        
        # Validate dependencies
        validation = self.kanban.validate_dependencies(task_id)
        
        return f"""🔍 Task Analysis: **{feature['title']}**

**Requirements Analysis:**
- Stage: {feature['stage']} ({self.get_stage_name(feature['stage'])})
- Effort Level: {feature['effort']} ({self.get_effort_description(feature['effort'])})
- Epic: {feature['epic']} ({self.get_epic_description(feature['epic'])})
- Priority: {feature['priority']}

**Implementation Scope:**
{feature['description']}

**Success Criteria:**
{feature['acceptance']}

**Dependencies:**
{', '.join(feature['dependencies']) if feature['dependencies'] else 'None - ready to implement'}
Dependencies Met: {'✅ Yes' if validation['valid'] else '❌ No - Missing: ' + ', '.join(validation.get('missing', []))}

**Recommended Implementation Plan:**
{self.generate_implementation_plan(feature)}

**Files Likely to be Modified:**
{self.suggest_target_files(feature)}"""

    def handle_get_task_details(self, arguments: Dict[str, Any]) -> str:
        """Get detailed task information"""
        task_id = arguments["task_id"]
        
        feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
        if not feature:
            return f"❌ Task {task_id} not found"
        
        # Get current status
        progress = self.kanban.load_progress()
        current_status = progress["boardState"].get(task_id, "backlog")
        
        # Get development notes
        dev_notes = progress.get("developmentNotes", {}).get(task_id, [])
        notes_text = ""
        if dev_notes:
            notes_text = "\n**Development Notes:**\n"
            for note in dev_notes[-3:]:  # Last 3 notes
                notes_text += f"- {note['timestamp']}: {note['notes']}\n"
        
        return f"""📋 Task Details: **{task_id}**

**Title:** {feature['title']}
**Description:** {feature['description']}
**Current Status:** {current_status}
**Stage:** {feature['stage']} ({self.get_stage_name(feature['stage'])})
**Priority:** {feature['priority']}
**Effort:** {feature['effort']} ({self.get_effort_description(feature['effort'])})
**Epic:** {feature['epic']} ({self.get_epic_description(feature['epic'])})
**Dependencies:** {', '.join(feature['dependencies']) if feature['dependencies'] else 'None'}
**Acceptance Criteria:** {feature['acceptance']}{notes_text}"""

    def handle_validate_dependencies(self, arguments: Dict[str, Any]) -> str:
        """Validate if a task's dependencies are properly completed and check for circular dependencies"""
        task_id = arguments["task_id"]
        
        validation = self.kanban.validate_dependencies(task_id)
        
        if validation["valid"]:
            return f"✅ All dependencies for task {task_id} are completed and no circular dependencies detected. Task is ready for development."
        else:
            error_msg = f"❌ Dependency validation failed for task {task_id}:\n"
            
            if validation.get("missing"):
                missing = ', '.join(validation["missing"])
                error_msg += f"  • Missing dependencies: {missing}\n"
                error_msg += f"  • Complete these tasks first before starting {task_id}\n"
            
            if validation.get("circular"):
                error_msg += f"  • Circular dependencies detected:\n"
                for cycle in validation["circular"]:
                    error_msg += f"    - {' → '.join(cycle)}\n"
                error_msg += f"  • Fix circular dependencies before proceeding\n"
            
            return error_msg.rstrip()
    
    def handle_validate_project_dependencies(self, arguments: Dict[str, Any]) -> str:
        """Check the entire project for circular dependencies and dependency issues"""
        if not self.kanban.features:
            return "✅ No features in project to validate."
        
        # Check for circular dependencies across the entire project
        circular_deps = self.kanban.detect_circular_dependencies()
        
        # Check for missing dependencies
        missing_deps_by_task = {}
        for feature in self.kanban.features:
            feature_deps = feature.get("dependencies", [])
            if feature_deps:
                existing_task_ids = {f.get("id") for f in self.kanban.features}
                missing = [dep for dep in feature_deps if dep not in existing_task_ids]
                if missing:
                    missing_deps_by_task[feature["id"]] = missing
        
        # Build report
        if not circular_deps and not missing_deps_by_task:
            return f"✅ Project dependency validation passed!\n\n📊 **Summary:**\n- Total tasks: {len(self.kanban.features)}\n- No circular dependencies detected\n- All dependencies reference valid tasks\n\n🎯 Project is ready for development!"
        
        error_msg = f"❌ Project dependency validation found issues:\n\n"
        
        if circular_deps:
            error_msg += f"🔄 **Circular Dependencies ({len(circular_deps)} found):**\n"
            for i, cycle in enumerate(circular_deps, 1):
                error_msg += f"  {i}. {' → '.join(cycle)}\n"
            error_msg += "\n"
        
        if missing_deps_by_task:
            error_msg += f"❓ **Missing Dependencies ({len(missing_deps_by_task)} tasks affected):**\n"
            for task_id, missing in missing_deps_by_task.items():
                task_title = next((f.get("title", task_id) for f in self.kanban.features if f.get("id") == task_id), task_id)
                error_msg += f"  • {task_title} ({task_id}): {', '.join(missing)}\n"
            error_msg += "\n"
        
        error_msg += f"📋 **Recommendations:**\n"
        if circular_deps:
            error_msg += f"  • Remove circular dependencies by updating task dependencies\n"
        if missing_deps_by_task:
            error_msg += f"  • Create missing dependency tasks or update dependencies to reference existing tasks\n"
        
        return error_msg.rstrip()

    # Clearing and Removal Tool Handlers
    @timeout_protection(30.0)
    async def handle_clear_kanban(self, arguments: Dict[str, Any]) -> str:
        """Clear all tasks from the kanban board"""
        confirm = arguments.get("confirm", False)
        
        if not confirm:
            task_count = len(self.kanban.features)
            project_name = self.project_config.get('project_name', 'Current Project') if self.project_config else 'Current Project'
            
            return f"""⚠️ **Confirmation Required: Clear Kanban Board**

**Project:** {project_name}
**Tasks to be removed:** {task_count}

This will permanently delete ALL tasks from the kanban board while preserving the project structure.

**What will be removed:**
- All feature/task cards ({task_count} total)
- All progress notes and development history
- All activity logs related to tasks

**What will be preserved:**
- Project configuration and metadata
- Board layout and columns
- WebSocket connections

🔴 **This action cannot be undone!**

To proceed, call this tool again with `confirm: true`."""
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            return f"""🔒 **Board is in Manual Mode - Action Blocked**

❌ Cannot clear kanban board while user has control.

📋 **Current Status:** User is managing the board manually
💡 **To proceed:** Ask the user to switch to Autonomous Mode, or they can clear the board manually via the UI."""
        
        # Perform the clearing operation (async)
        cleared_count = len(self.kanban.features)
        project_name = self.project_config.get('project_name', 'Project') if self.project_config else 'Project'
        
        # Clear all features and board state (run in executor to prevent blocking)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, self.kanban.clear_all_features)
        
        if success:
            return f"""✅ **Kanban Board Cleared Successfully**

**Project:** {project_name}
**Tasks removed:** {cleared_count}

**Actions completed:**
- All task cards removed from board
- Board state reset to empty
- Progress notes cleared
- Activity logged

**Board Status:**
- Columns preserved: {len(self.board_config['columns'])}
- Project metadata intact
- WebSocket connections maintained

🎯 **Ready for new features!** Use `add_feature` to start adding tasks to the clean board."""
        else:
            return f"""❌ **Failed to clear kanban board**

An error occurred while clearing the board. Please check the logs and try again."""

    @timeout_protection(30.0)
    async def handle_delete_project(self, arguments: Dict[str, Any]) -> str:
        """Delete the entire project"""
        confirm = arguments.get("confirm", False)
        
        if not confirm:
            project_name = self.project_config.get('project_name', 'Current Project') if self.project_config else 'Current Project'
            task_count = len(self.kanban.features)
            
            return f"""⚠️ **Confirmation Required: Delete Entire Project**

**Project:** {project_name}
**Tasks:** {task_count}
**Files:** kanban-progress.json, features.json

🔴 **DESTRUCTIVE OPERATION - COMPLETE PROJECT DELETION**

This will permanently delete:
- All project files and data
- All tasks and features ({task_count} total)
- All progress notes and history
- All activity logs
- Project configuration
- Board state and metadata

**What happens after deletion:**
- Project reset to initial empty state
- All WebSocket clients will see empty board
- You'll need to create a new project to continue

🚨 **THIS ACTION CANNOT BE UNDONE!**
🚨 **ALL PROJECT DATA WILL BE LOST!**

To proceed with complete deletion, call this tool again with `confirm: true`."""
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            return f"""🔒 **Board is in Manual Mode - Action Blocked**

❌ Cannot delete project while user has control.

📋 **Current Status:** User is managing the board manually
💡 **To proceed:** Ask the user to switch to Autonomous Mode, or they can manage the project manually."""
        
        # Perform the deletion (async)
        project_name = self.project_config.get('project_name', 'Project') if self.project_config else 'Project'
        task_count = len(self.kanban.features)
        
        # Run deletion in executor to prevent blocking
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, self.kanban.delete_project)
        
        if success:
            # Reset server state
            self.project_config = None
            self.board_config = {
                "title": "Dynamic Kanban Board",
                "subtitle": "Ready for your project", 
                "columns": CONFIG.DEFAULT_COLUMNS.copy()
            }
            
            return f"""✅ **Project Deleted Successfully**

**Former Project:** {project_name}
**Tasks removed:** {task_count}

**Deletion completed:**
- All project files removed
- Board state cleared
- Features and metadata deleted
- Activity history purged
- WebSocket clients notified

**Current Status:**
- Server reset to initial state
- Ready for new project creation
- Use `create_project` to start fresh

🎯 **Clean slate ready!** All data has been permanently removed."""
        else:
            return f"""❌ **Failed to delete project**

An error occurred during project deletion. Some files may still exist. Please check manually."""

    @timeout_protection(15.0)  # 15 second timeout for remove operations
    def handle_remove_feature(self, arguments: Dict[str, Any]) -> str:
        """Remove a specific feature from the kanban board"""
        task_id = arguments["task_id"]
        force = arguments.get("force", False)
        
        # Find the task
        feature = next((f for f in self.kanban.features if f["id"] == task_id), None)
        if not feature:
            return f"❌ Task {task_id} not found"
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            self.kanban.queue_claude_action(
                "remove_feature",
                {"task_id": task_id, "force": force},
                f"Remove task '{feature['title']}' ({task_id})"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot remove task while user has control of the kanban board.

**Queued Action:** Remove task "{feature['title']}"
- Task ID: {task_id}
- Force removal: {force}

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This action will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can delete the task manually."""
        
        # Check for dependencies if not forcing
        if not force:
            dependent_tasks = [f for f in self.kanban.features if task_id in f.get("dependencies", [])]
            if dependent_tasks:
                dependent_list = [f"{f['id']} ({f['title']})" for f in dependent_tasks]
                return f"""❌ **Cannot remove task {task_id}**

**Reason:** Other tasks depend on this task

**Dependent tasks:**
{chr(10).join([f"  • {dep}" for dep in dependent_list])}

**Options:**
1. Remove dependencies first, then delete this task
2. Use `force: true` to remove despite dependencies (may break dependent tasks)
3. Use `remove_features` to remove multiple tasks including dependencies"""
        
        # Perform the removal
        success = self.kanban.remove_feature_by_id(task_id)
        
        if success:
            return f"""✅ **Task Removed Successfully**

**Removed:** {feature['title']} ({task_id})
**Status:** {feature.get('status', 'backlog')}
**Priority:** {feature.get('priority', 'medium')}

**Actions completed:**
- Task removed from features list
- Board state updated
- Progress notes cleared
- Activity logged
- WebSocket clients notified

🔗 All connected UIs updated automatically"""
        else:
            return f"❌ Failed to remove task {task_id}. Please check logs and try again."

    @timeout_protection(30.0)  # 30 second timeout for bulk remove operations
    def handle_remove_features(self, arguments: Dict[str, Any]) -> str:
        """Remove multiple features from the kanban board"""
        task_ids = arguments["task_ids"]
        force = arguments.get("force", False)
        
        if not task_ids:
            return "❌ No task IDs provided"
        
        # Validate all task IDs exist
        existing_features = {f["id"]: f for f in self.kanban.features}
        missing_tasks = [tid for tid in task_ids if tid not in existing_features]
        valid_tasks = [tid for tid in task_ids if tid in existing_features]
        
        if missing_tasks:
            return f"""❌ **Some tasks not found**

**Missing tasks:** {', '.join(missing_tasks)}
**Valid tasks:** {', '.join(valid_tasks)}

Please check task IDs and try again with valid tasks only."""
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            task_titles = [existing_features[tid]['title'] for tid in valid_tasks]
            self.kanban.queue_claude_action(
                "remove_features",
                {"task_ids": task_ids, "force": force},
                f"Remove {len(valid_tasks)} tasks: {', '.join(task_titles[:3])}{'...' if len(task_titles) > 3 else ''}"
            )
            
            return f"""🔒 **Board is in Manual Mode - Action Queued**

❌ Cannot remove tasks while user has control of the kanban board.

**Queued Action:** Remove {len(valid_tasks)} tasks
- Tasks: {', '.join(task_ids)}
- Force removal: {force}

📋 **Current Status:** User is managing the board manually
🎯 **What happens next:** This action will be applied when the user switches back to Autonomous Mode

💡 **To apply immediately:** Ask the user to switch to Autonomous Mode, or they can delete tasks manually."""
        
        # Check for dependencies if not forcing
        if not force:
            dependency_issues = []
            for task_id in valid_tasks:
                dependent_tasks = [f for f in self.kanban.features if task_id in f.get("dependencies", []) and f["id"] not in task_ids]
                if dependent_tasks:
                    dependent_list = [f"{f['id']} ({f['title']})" for f in dependent_tasks]
                    dependency_issues.append(f"• {task_id}: {', '.join(dependent_list)}")
            
            if dependency_issues:
                return f"""❌ **Cannot remove tasks due to dependencies**

**Tasks with external dependencies:**
{chr(10).join(dependency_issues)}

**Options:**
1. Include dependent tasks in the removal list
2. Remove dependencies first
3. Use `force: true` to remove despite dependencies (may break dependent tasks)"""
        
        # Perform bulk removal
        success, removed_count = self.kanban.remove_multiple_features(valid_tasks)
        
        if success:
            removed_titles = [existing_features[tid]['title'] for tid in valid_tasks]
            return f"""✅ **Tasks Removed Successfully**

**Removed {removed_count} tasks:**
{chr(10).join([f"  • {existing_features[tid]['title']} ({tid})" for tid in valid_tasks])}

**Actions completed:**
- All tasks removed from features list
- Board state updated for all tasks
- Progress notes cleared
- Activity logged for bulk operation
- WebSocket clients notified

🔗 All connected UIs updated automatically"""
        else:
            return f"❌ Failed to remove tasks. Removed {removed_count} out of {len(valid_tasks)} tasks. Please check logs."

    @timeout_protection(20.0)  # 20 second timeout for column clear operations
    def handle_clear_column(self, arguments: Dict[str, Any]) -> str:
        """Clear all tasks from a specific status column"""
        status = arguments["status"]
        confirm = arguments.get("confirm", False)
        
        # Get tasks in this column
        tasks_in_column = [f for f in self.kanban.features if f.get("status", "backlog") == status]
        
        if not tasks_in_column:
            return f"ℹ️ No tasks found in {status} column. Nothing to clear."
        
        if not confirm:
            column_name = next((col["name"] for col in self.board_config["columns"] if col["id"] == status), status)
            task_list = [f"  • {f['title']} ({f['id']})" for f in tasks_in_column]
            
            return f"""⚠️ **Confirmation Required: Clear {column_name} Column**

**Tasks to be removed:** {len(tasks_in_column)}

{chr(10).join(task_list)}

🔴 **This will permanently delete all tasks in the {status} column!**

**What will be removed:**
- All task cards in {column_name}
- Associated progress notes
- Task history

To proceed, call this tool again with `confirm: true`."""
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            return f"""🔒 **Board is in Manual Mode - Action Blocked**

❌ Cannot clear column while user has control.

📋 **Current Status:** User is managing the board manually
💡 **To proceed:** Ask the user to switch to Autonomous Mode, or they can clear the column manually."""
        
        # Perform the clearing
        task_ids = [f["id"] for f in tasks_in_column]
        success, removed_count = self.kanban.remove_multiple_features(task_ids)
        
        if success:
            column_name = next((col["name"] for col in self.board_config["columns"] if col["id"] == status), status)
            return f"""✅ **{column_name} Column Cleared**

**Removed {removed_count} tasks from {status} column**

**Actions completed:**
- All tasks removed from {column_name}
- Board state updated
- Progress notes cleared
- Activity logged
- WebSocket clients notified

🔗 All connected UIs updated automatically"""
        else:
            return f"❌ Failed to clear {status} column. Removed {removed_count} out of {len(task_ids)} tasks."

    @timeout_protection(25.0)  # 25 second timeout for board reset operations
    def handle_reset_board(self, arguments: Dict[str, Any]) -> str:
        """Reset the kanban board to initial empty state"""
        confirm = arguments.get("confirm", False)
        
        if not confirm:
            task_count = len(self.kanban.features)
            project_name = self.project_config.get('project_name', 'Current Project') if self.project_config else 'Current Project'
            
            return f"""⚠️ **Confirmation Required: Complete Board Reset**

**Project:** {project_name}
**Current tasks:** {task_count}

🔴 **COMPLETE RESET - ALL DATA WILL BE LOST**

This will reset everything to initial state:
- Delete all tasks and features
- Clear all progress and history
- Reset project configuration
- Clear activity logs
- Reset board to default columns

**After reset:**
- Board will be completely empty
- You'll need to create a new project
- All WebSocket clients will see empty board

🚨 **THIS ACTION CANNOT BE UNDONE!**

To proceed with complete reset, call this tool again with `confirm: true`."""
        
        # Check if Claude is allowed to modify the board
        if not self.kanban.claude_action_allowed():
            return f"""🔒 **Board is in Manual Mode - Action Blocked**

❌ Cannot reset board while user has control.

📋 **Current Status:** User is managing the board manually
💡 **To proceed:** Ask the user to switch to Autonomous Mode."""
        
        # Perform complete reset
        task_count = len(self.kanban.features)
        project_name = self.project_config.get('project_name', 'Project') if self.project_config else 'Project'
        
        success = self.kanban.reset_to_initial_state()
        
        if success:
            # Reset server state
            self.project_config = None
            self.board_config = {
                "title": "Dynamic Kanban Board",
                "subtitle": "Ready for your project",
                "columns": CONFIG.DEFAULT_COLUMNS.copy()
            }
            
            return f"""✅ **Board Reset Complete**

**Former project:** {project_name}
**Tasks removed:** {task_count}

**Reset completed:**
- All tasks and features removed
- Project configuration cleared
- Board reset to default columns
- All progress and history purged
- Activity logs cleared
- WebSocket clients notified

**Current Status:**
- Board is completely empty
- Server in initial state
- Ready for new project creation

🎯 **Fresh start!** Use `create_project` to begin a new project."""
        else:
            return f"❌ Failed to reset board. Please check logs and try again."


    # Helper Methods - Now using centralized configuration
    def get_stage_name(self, stage: int) -> str:
        """Get descriptive name for a stage"""
        return CONFIG.get_stage_name(stage)

    def get_effort_description(self, effort: str) -> str:
        """Get descriptive text for effort level"""
        return CONFIG.get_effort_description(effort)

    def get_epic_description(self, epic: str) -> str:
        """Get descriptive text for epic category"""
        return CONFIG.get_epic_description(epic)

    def generate_implementation_plan(self, feature: Dict) -> str:
        """Generate implementation plan based on feature characteristics"""
        epic = feature.get("epic", "general")
        stage = feature.get("stage", 1)
        return CONFIG.get_implementation_plan(epic, stage)

    def suggest_target_files(self, feature: Dict) -> str:
        """Suggest which files might need modification"""
        epic = feature.get("epic", "general")
        return CONFIG.get_file_suggestions(epic)

    def run_server(self):
        """Run the MCP server"""
        print("🚀 Starting Dynamic Kanban MCP Server v3.0...")
        print("🔧 Real-time WebSocket synchronization enabled")
        print("📋 Dynamic kanban management for any project type")
        print("🎯 Bidirectional sync between Claude and HTML UI")
        print(f"🌐 WebSocket server on port {self.kanban.websocket_port}")
        
        # Check if running via MCP (stdin input) or standalone
        if sys.stdin.isatty():
            # Running standalone - show demo
            self._run_standalone_demo()
        else:
            # Running via MCP - use proper protocol
            self.server.run_sync()
    
    def _run_standalone_demo(self):
        """Run a standalone demo when not connected via MCP"""
        print("\n🚀 Dynamic Kanban Controller Demo Mode")
        print("=" * 40)
        
        # Show available tools
        print("\n🔧 Available Tools:")
        for tool_name, tool_data in self.server.tools.items():
            print(f"  • {tool_name} - {tool_data['description']}")
        
        # Show current status
        print(f"\n📊 Current Kanban Status:")
        self.kanban.print_status()
        
        # Show WebSocket status
        print(f"\n🔗 WebSocket Server:")
        print(f"  • Port: {self.kanban.websocket_port}")
        print(f"  • Connected clients: {len(self.kanban.websocket_clients)}")
        
        # Demo some operations
        print(f"\n🎯 Next priority task:")
        if len(self.kanban.features) > 0:
            next_task = self.kanban.get_next_task()
            if next_task:
                print(f"  {next_task['title']} (Stage {next_task['stage']}, {next_task['priority']} priority)")
            else:
                print("  No tasks ready for development")
        else:
            print("  No features defined yet. Use MCP tools to create a project and add features.")
        
        print(f"\n✅ MCP server ready for Claude integration")
        print(f"💡 Connect via MCP to enable full dynamic kanban features")
        print(f"🎯 Create projects, add features, and generate real-time UI!")
        print(f"\n🔄 Server running continuously to maintain WebSocket connections...")
        print(f"📡 WebSocket clients can connect to ws://localhost:{self.kanban.websocket_port}")
        print(f"⚠️  Press Ctrl+C to stop the server")
        
        # Keep the server running for WebSocket connections
        try:
            import time
            while True:
                time.sleep(60)  # Check every minute
                print(f"\n💓 Server heartbeat - WebSocket clients: {len(self.kanban.websocket_clients)} connected")
        except KeyboardInterrupt:
            print("\n🛑 Server stopped by user")

def main():
    """Main entry point"""
    server = KanbanMCPServer()
    server.run_server()

if __name__ == "__main__":
    main()