#!/usr/bin/env python3
"""
Centralized Configuration for Dynamic Kanban MCP Server
Ensures consistent settings across all components
"""

import os
from typing import Dict, List, Any

class KanbanConfig:
    """Centralized configuration management for the Kanban MCP system"""
    
    # WebSocket Configuration
    WEBSOCKET_PORT = int(os.getenv("KANBAN_WEBSOCKET_PORT", "8765"))
    WEBSOCKET_HOST = os.getenv("KANBAN_WEBSOCKET_HOST", "0.0.0.0")
    
    # File Paths - Use absolute paths relative to script directory
    @classmethod
    def get_progress_file_path(cls):
        from pathlib import Path
        return str(Path(__file__).parent / "kanban-progress.json")
    
    @classmethod 
    def get_ui_file_path_static(cls):
        from pathlib import Path
        return str(Path(__file__).parent / "kanban-board.html")
    
    DEFAULT_PROGRESS_FILE = "./kanban-progress.json"  # Fallback for backward compatibility
    DEFAULT_UI_FILE = "kanban-board.html"
    
    # Server Configuration
    MCP_SERVER_NAME = "dynamic-kanban"
    MCP_SERVER_VERSION = "3.0.0"
    
    # Default Board Configuration
    DEFAULT_COLUMNS = [
        {"id": "backlog", "name": "📋 Backlog", "emoji": "📋"},
        {"id": "ready", "name": "⚡ Ready", "emoji": "⚡"},
        {"id": "progress", "name": "🔧 In Progress", "emoji": "🔧"},
        {"id": "testing", "name": "🧪 Testing", "emoji": "🧪"},
        {"id": "done", "name": "✅ Done", "emoji": "✅"}
    ]
    
    # Priority and effort configurations
    PRIORITY_LEVELS = ["low", "medium", "high", "critical"]
    EFFORT_LEVELS = ["xs", "s", "m", "l", "xl"]
    
    # Epic categories
    DEFAULT_EPICS = [
        "general", "frontend", "backend", "ui", "api", 
        "database", "auth", "testing", "deployment"
    ]
    
    # Centralized descriptive text configurations
    STAGE_DESCRIPTIONS = {
        1: "Foundation & Core Features",
        2: "Feature Development",
        3: "Integration & Enhancement", 
        4: "Advanced Features",
        5: "Optimization & Polish",
        6: "Release & Maintenance"
    }
    
    EFFORT_DESCRIPTIONS = {
        "xs": "Extra Small - Quick task",
        "s": "Small - Few hours",
        "m": "Medium - Half day",
        "l": "Large - Full day",
        "xl": "Extra Large - Multiple days"
    }
    
    EPIC_DESCRIPTIONS = {
        "frontend": "Frontend Development",
        "backend": "Backend Development", 
        "ui": "User Interface",
        "api": "API Development",
        "database": "Database Design",
        "auth": "Authentication",
        "testing": "Testing & QA",
        "deployment": "DevOps & Deployment",
        "general": "General Development"
    }
    
    # Implementation plan templates by epic and stage
    IMPLEMENTATION_PLANS = {
        ("frontend", 1): "Implement basic UI components with responsive design",
        ("backend", 1): "Create core API endpoints and data models",
        ("ui", 1): "Build clean, responsive interface with modern frameworks",
        ("api", 1): "Develop RESTful API with proper error handling",
        ("database", 1): "Design and implement data schema",
        ("auth", 1): "Implement authentication and authorization",
        ("testing", 1): "Create comprehensive test suite",
        ("deployment", 1): "Set up CI/CD pipeline and deployment"
    }
    
    # File suggestions by epic
    FILE_SUGGESTIONS = {
        "frontend": "src/components/ (React/Vue components), src/styles/ (CSS files)",
        "backend": "src/api/ (API routes), src/models/ (data models)",
        "ui": "src/components/ (UI components), public/index.html (HTML structure)",
        "api": "src/routes/ (API endpoints), src/controllers/ (business logic)",
        "database": "migrations/ (database schema), src/models/ (ORM models)",
        "auth": "src/auth/ (authentication logic), middleware/ (auth middleware)",
        "testing": "tests/ (test files), jest.config.js (test configuration)",
        "deployment": ".github/workflows/ (CI/CD), docker/ (containerization)"
    }
    
    # Validation settings
    MAX_TASK_TITLE_LENGTH = 100
    MAX_TASK_DESCRIPTION_LENGTH = 1000
    MAX_DEPENDENCIES = 10
    
    # WebSocket settings
    WEBSOCKET_RECONNECT_DELAY = 3  # seconds
    WEBSOCKET_PING_INTERVAL = 30   # seconds
    WEBSOCKET_TIMEOUT = 120        # seconds
    
    @classmethod
    def get_websocket_url(cls) -> str:
        """Get the complete WebSocket URL"""
        return f"ws://{cls.WEBSOCKET_HOST}:{cls.WEBSOCKET_PORT}"
    
    @classmethod
    def validate_task_data(cls, task_data: Dict[str, Any]) -> List[str]:
        """Validate task data using Pydantic model and return list of errors"""
        try:
            from models import Task
            # Try to create a Task instance with the data
            Task.parse_obj(task_data)
            return []  # No errors if validation passes
        except Exception as e:
            # Extract error messages from Pydantic validation
            if hasattr(e, 'errors'):
                errors = []
                for error in e.errors():
                    field = ' -> '.join(str(x) for x in error['loc'])
                    message = error['msg']
                    errors.append(f"{field}: {message}")
                return errors
            else:
                return [str(e)]
    
    @classmethod
    def detect_circular_dependencies(cls, tasks: List[Dict[str, Any]]) -> List[List[str]]:
        """Detect circular dependencies in task list and return cycles found"""
        # Build dependency graph
        graph = {}
        for task in tasks:
            task_id = task.get('id')
            if task_id:
                graph[task_id] = task.get('dependencies', [])
        
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: List[str]) -> bool:
            """Depth-first search to detect cycles"""
            if node in rec_stack:
                # Found a cycle - extract the cycle from the path
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
                return True
            
            if node in visited:
                return False
            
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            # Check all dependencies
            for dependency in graph.get(node, []):
                if dependency in graph:  # Only check dependencies that exist as tasks
                    if dfs(dependency, path):
                        # Continue searching for more cycles
                        pass
            
            rec_stack.remove(node)
            path.pop()
            return False
        
        # Check all nodes for cycles
        for task_id in graph:
            if task_id not in visited:
                dfs(task_id, [])
        
        return cycles
    
    @classmethod
    def validate_dependencies_against_tasks(cls, task_id: str, dependencies: List[str], existing_tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate that dependencies exist and don't create circular dependencies"""
        existing_task_ids = {task.get('id') for task in existing_tasks if task.get('id')}
        
        # Check for non-existent dependencies
        missing_deps = [dep for dep in dependencies if dep not in existing_task_ids and dep != task_id]
        
        # Create a test task list including the new task to check for cycles
        test_tasks = existing_tasks.copy()
        test_tasks.append({
            'id': task_id,
            'dependencies': dependencies
        })
        
        # Check for circular dependencies
        circular_deps = cls.detect_circular_dependencies(test_tasks)
        
        return {
            'valid': len(missing_deps) == 0 and len(circular_deps) == 0,
            'missing': missing_deps,
            'circular': circular_deps
        }
    
    @classmethod
    def get_default_task_data(cls) -> Dict[str, Any]:
        """Get default task data structure"""
        return {
            "id": "",
            "title": "",
            "description": "",
            "priority": "medium",
            "effort": "m",
            "epic": "general",
            "stage": 1,
            "status": "backlog",
            "dependencies": [],
            "acceptance": "Feature works as described"
        }
    
    @classmethod
    def ensure_websocket_port_available(cls) -> bool:
        """Check if WebSocket port is available"""
        import socket
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((cls.WEBSOCKET_HOST, cls.WEBSOCKET_PORT))
                return True
        except OSError:
            return False
    
    @classmethod
    def find_available_port(cls, start_port: int = None) -> int:
        """Find an available port starting from start_port"""
        import socket
        
        if start_port is None:
            start_port = cls.WEBSOCKET_PORT
        
        for port in range(start_port, start_port + 100):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((cls.WEBSOCKET_HOST, port))
                    return port
            except OSError:
                continue
        
        raise RuntimeError("No available ports found")
    
    @classmethod
    def get_ui_file_path(cls) -> str:
        """Get the path to the UI file"""
        import os
        from pathlib import Path
        
        # Check current directory first
        current_dir = Path.cwd()
        ui_file = current_dir / cls.DEFAULT_UI_FILE
        
        if ui_file.exists():
            return str(ui_file)
        
        # Check script directory
        script_dir = Path(__file__).parent
        ui_file = script_dir / cls.DEFAULT_UI_FILE
        
        if ui_file.exists():
            return str(ui_file)
        
        # Return default path even if doesn't exist
        return str(script_dir / cls.DEFAULT_UI_FILE)
    
    @classmethod
    def validate_ui_file_exists(cls) -> bool:
        """Check if the UI file exists"""
        import os
        return os.path.exists(cls.get_ui_file_path())
    
    @classmethod
    def get_stage_name(cls, stage: int) -> str:
        """Get descriptive name for a stage"""
        return cls.STAGE_DESCRIPTIONS.get(stage, f"Stage {stage}")
    
    @classmethod
    def get_effort_description(cls, effort: str) -> str:
        """Get descriptive text for effort level"""
        return cls.EFFORT_DESCRIPTIONS.get(effort, effort)
    
    @classmethod
    def get_epic_description(cls, epic: str) -> str:
        """Get descriptive text for epic category"""
        return cls.EPIC_DESCRIPTIONS.get(epic, epic.title())
    
    @classmethod
    def get_implementation_plan(cls, epic: str, stage: int) -> str:
        """Get implementation plan template for epic and stage"""
        return cls.IMPLEMENTATION_PLANS.get((epic, stage), f"Implement according to requirements and acceptance criteria")
    
    @classmethod
    def get_file_suggestions(cls, epic: str) -> str:
        """Get file suggestions for an epic"""
        return cls.FILE_SUGGESTIONS.get(epic, "Implementation-specific files based on requirements")

# Global configuration instance
CONFIG = KanbanConfig()