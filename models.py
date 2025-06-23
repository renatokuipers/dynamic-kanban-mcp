#!/usr/bin/env python3
"""
Pydantic Data Models for Dynamic Kanban MCP Server
Provides type-safe validation and data structures
"""

from pydantic import BaseModel, Field, validator, root_validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

class Priority(str, Enum):
    """Task priority levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Effort(str, Enum):
    """Task effort estimates"""
    XS = "xs"  # < 1 hour
    S = "s"    # 2-4 hours
    M = "m"    # Half day
    L = "l"    # Full day
    XL = "xl"  # Multiple days

class Status(str, Enum):
    """Task status in kanban board"""
    BACKLOG = "backlog"
    READY = "ready"
    PROGRESS = "progress"
    TESTING = "testing"
    DONE = "done"

class Epic(str, Enum):
    """Epic categories for organizing tasks"""
    GENERAL = "general"
    FRONTEND = "frontend"
    BACKEND = "backend"
    UI = "ui"
    API = "api"
    DATABASE = "database"
    AUTH = "auth"
    TESTING = "testing"
    DEPLOYMENT = "deployment"

class Task(BaseModel):
    """A kanban task with full validation"""
    
    id: str = Field(..., min_length=1, max_length=50, description="Unique task identifier")
    title: str = Field(..., min_length=1, max_length=100, description="Task title")
    description: str = Field(..., min_length=1, max_length=1000, description="Task description")
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority level")
    effort: Effort = Field(default=Effort.M, description="Estimated effort required")
    epic: Epic = Field(default=Epic.GENERAL, description="Epic category")
    stage: int = Field(default=1, ge=1, le=6, description="Development stage (1-6)")
    status: Status = Field(default=Status.BACKLOG, description="Current status")
    dependencies: List[str] = Field(default_factory=list, max_items=10, description="List of task IDs this task depends on")
    acceptance: str = Field(default="Feature works as described", max_length=500, description="Acceptance criteria")
    
    @validator('dependencies')
    def validate_dependencies(cls, v):
        """Ensure dependencies are valid task IDs"""
        if v:
            # Remove duplicates and empty strings
            v = list(set(dep.strip() for dep in v if dep.strip()))
        return v
    
    @validator('id')
    def validate_id_format(cls, v):
        """Ensure task ID follows proper format"""
        if not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError('Task ID must contain only alphanumeric characters, hyphens, and underscores')
        return v
    
    class Config:
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "id": "feature-1",
                "title": "User Authentication",
                "description": "Implement user login and registration system",
                "priority": "high",
                "effort": "l",
                "epic": "backend",
                "stage": 1,
                "status": "backlog",
                "dependencies": [],
                "acceptance": "Users can register, login, and logout successfully"
            }
        }

class ProjectConfig(BaseModel):
    """Project configuration data"""
    
    project_name: str = Field(..., min_length=1, max_length=100, description="Project name")
    project_type: str = Field(..., min_length=1, max_length=50, description="Type of project")
    description: Optional[str] = Field(default="", max_length=500, description="Project description")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    id: str = Field(..., min_length=1, max_length=20, description="Unique project identifier")
    
    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "My Web App",
                "project_type": "web",
                "description": "A modern web application",
                "id": "proj-123"
            }
        }

class BoardColumn(BaseModel):
    """A column in the kanban board"""
    
    id: str = Field(..., min_length=1, max_length=20, description="Column identifier")
    name: str = Field(..., min_length=1, max_length=50, description="Display name")
    emoji: str = Field(..., min_length=1, max_length=10, description="Emoji for the column")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "backlog",
                "name": "📋 Backlog",
                "emoji": "📋"
            }
        }

class BoardConfig(BaseModel):
    """Kanban board configuration"""
    
    title: str = Field(default="Dynamic Kanban Board", max_length=100, description="Board title")
    subtitle: str = Field(default="Ready for your project", max_length=200, description="Board subtitle")
    columns: List[BoardColumn] = Field(default_factory=list, min_items=1, description="Board columns")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "🚀 My Project Kanban",
                "subtitle": "Web Application Project",
                "columns": [
                    {"id": "backlog", "name": "📋 Backlog", "emoji": "📋"},
                    {"id": "ready", "name": "⚡ Ready", "emoji": "⚡"},
                    {"id": "progress", "name": "🔧 In Progress", "emoji": "🔧"},
                    {"id": "testing", "name": "🧪 Testing", "emoji": "🧪"},
                    {"id": "done", "name": "✅ Done", "emoji": "✅"}
                ]
            }
        }

class ActivityEntry(BaseModel):
    """An activity log entry"""
    
    type: str = Field(..., description="Type of activity")
    content: str = Field(..., description="Human-readable description")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the activity occurred")
    source: str = Field(default="autonomous", description="Source of the activity (autonomous, manual, ui)")
    task_id: Optional[str] = Field(default=None, description="Related task ID if applicable")
    
    # Additional fields for specific activity types
    task_title: Optional[str] = Field(default=None, description="Task title for task-related activities")
    from_status: Optional[str] = Field(default=None, alias="from", description="Previous status for move activities")
    to_status: Optional[str] = Field(default=None, alias="to", description="New status for move activities") 
    notes: Optional[str] = Field(default=None, description="Additional notes")
    session_name: Optional[str] = Field(default=None, description="Session name for session activities")
    duration: Optional[float] = Field(default=None, description="Duration in seconds for session end")
    
    class Config:
        populate_by_name = True
        schema_extra = {
            "example": {
                "type": "card_moved",
                "content": "Moved 'User Authentication' from backlog to progress",
                "source": "autonomous",
                "task_id": "feature-1",
                "task_title": "User Authentication",
                "from": "backlog",
                "to": "progress"
            }
        }

class DevelopmentNote(BaseModel):
    """A development note for a task"""
    
    notes: str = Field(..., min_length=1, max_length=1000, description="Development notes")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the note was added")
    
    class Config:
        json_schema_extra = {
            "example": {
                "notes": "Implemented JWT authentication, still working on refresh tokens",
                "timestamp": "2023-10-01T10:30:00Z"
            }
        }

class SessionData(BaseModel):
    """Development session information"""
    
    name: str = Field(..., min_length=1, max_length=100, description="Session name")
    start_time: datetime = Field(default_factory=datetime.now, alias="startTime", description="Session start time")
    tasks: List[str] = Field(default_factory=list, description="Task IDs worked on in this session")
    
    class Config:
        populate_by_name = True
        schema_extra = {
            "example": {
                "name": "Stage 1 Core Development",
                "startTime": "2023-10-01T09:00:00Z",
                "tasks": ["feature-1", "feature-2"]
            }
        }

class Metadata(BaseModel):
    """Metadata for the progress file"""
    
    last_updated: datetime = Field(default_factory=datetime.now, alias="lastUpdated", description="Last update timestamp")
    version: str = Field(default="1.0.0", description="Progress file version")
    autonomous_mode: bool = Field(default=False, alias="autonomousMode", description="Whether in autonomous mode")
    current_session: Optional[SessionData] = Field(default=None, alias="currentSession", description="Current development session")
    is_manual_mode: Optional[bool] = Field(default=None, alias="isManualMode", description="Whether in manual mode")
    mode_changed_by: Optional[str] = Field(default=None, alias="modeChangedBy", description="Who changed the mode")
    mode_changed_at: Optional[datetime] = Field(default=None, alias="modeChangedAt", description="When mode was changed")
    project_name: Optional[str] = Field(default=None, alias="projectName", description="Project name")
    
    class Config:
        populate_by_name = True
        schema_extra = {
            "example": {
                "lastUpdated": "2023-10-01T10:30:00Z",
                "version": "1.0.0",
                "autonomousMode": False,
                "currentSession": None,
                "projectName": "My Web App"
            }
        }

class ProgressData(BaseModel):
    """Complete progress file structure"""
    
    board_state: Dict[str, str] = Field(default_factory=dict, alias="boardState", description="Task ID to status mapping")
    activity: List[ActivityEntry] = Field(default_factory=list, description="Activity log")
    metadata: Metadata = Field(default_factory=Metadata, description="Progress metadata")
    development_notes: Dict[str, List[DevelopmentNote]] = Field(default_factory=dict, alias="developmentNotes", description="Development notes by task ID")
    timestamps: Dict[str, datetime] = Field(default_factory=dict, description="Timestamps for various events")
    
    class Config:
        populate_by_name = True
        schema_extra = {
            "example": {
                "boardState": {
                    "feature-1": "progress",
                    "feature-2": "backlog"
                },
                "activity": [],
                "metadata": {
                    "lastUpdated": "2023-10-01T10:30:00Z",
                    "version": "1.0.0",
                    "autonomousMode": False
                },
                "developmentNotes": {},
                "timestamps": {}
            }
        }

class DependencyValidation(BaseModel):
    """Result of dependency validation"""
    
    valid: bool = Field(..., description="Whether dependencies are valid")
    missing: List[str] = Field(default_factory=list, description="List of missing dependency task IDs")
    circular: List[List[str]] = Field(default_factory=list, description="List of circular dependency chains found")
    
    class Config:
        json_schema_extra = {
            "example": {
                "valid": False,
                "missing": ["feature-1"],
                "circular": [["feature-2", "feature-3", "feature-2"]]
            }
        }

class BoardState(BaseModel):
    """Current state of the kanban board"""
    
    features: List[Task] = Field(default_factory=list, description="All tasks on the board")
    board_state: Dict[str, str] = Field(default_factory=dict, alias="boardState", description="Task status mapping")
    activity: List[ActivityEntry] = Field(default_factory=list, description="Recent activity")
    metadata: Metadata = Field(default_factory=Metadata, description="Board metadata")
    is_manual_mode: bool = Field(default=False, alias="isManualMode", description="Whether in manual mode")
    pending_actions: int = Field(default=0, alias="pendingActions", description="Number of pending actions")
    
    class Config:
        populate_by_name = True
        schema_extra = {
            "example": {
                "features": [],
                "boardState": {},
                "activity": [],
                "metadata": {},
                "isManualMode": False,
                "pendingActions": 0
            }
        }