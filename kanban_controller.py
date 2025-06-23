#!/usr/bin/env python3
"""
Dynamic Kanban Controller
Autonomous development interface for any project's Kanban board
"""

import json
import os
import time
import threading
import asyncio
import websockets
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
import logging
from pydantic import ValidationError

from config import CONFIG
from models import Task, ProgressData, ActivityEntry, DependencyValidation, BoardState

class KanbanController:
    def __init__(self, progress_file=None, websocket_port=None, mcp_server=None):
        self.progress_file = progress_file or CONFIG.get_progress_file_path()
        self.websocket_port = websocket_port or CONFIG.WEBSOCKET_PORT
        self.features = self._load_features()
        self.websocket_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.websocket_server = None
        self.lock = threading.Lock()
        self.mcp_server = mcp_server  # Reference to MCP server for tool handlers
        
        # Mode management and access control
        self.is_manual_mode = False
        self.pending_claude_actions = []
        self.next_task_id = 1
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("kanban_controller")
        
    def _load_features(self) -> List[Dict]:
        """Load feature definitions from features.json file if available, 
        or attempt to reconstruct from progress file"""
        try:
            features_file = Path(__file__).parent / "features.json"
            if features_file.exists():
                with open(features_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing features.json: {e}")
        
        # Attempt to reconstruct features from existing progress file
        if os.path.exists(self.progress_file):
            try:
                reconstructed_features = self._reconstruct_features_from_progress()
                if reconstructed_features:
                    print(f"🔄 Reconstructed {len(reconstructed_features)} features from progress file")
                    return reconstructed_features
            except Exception as e:
                print(f"⚠️ Could not reconstruct features from progress file: {e}")
        
        # Return empty list - features will be managed dynamically
        return []
    
    def _reconstruct_features_from_progress(self) -> List[Dict]:
        """Reconstruct basic feature definitions from progress file task IDs"""
        try:
            with open(self.progress_file, 'r') as f:
                progress_data = json.load(f)
            
            board_state = progress_data.get("boardState", {})
            reconstructed_features = []
            
            for task_id, status in board_state.items():
                # Create basic feature structure with minimal data
                feature = {
                    "id": task_id,
                    "title": f"Task {task_id}",  # Basic title from ID
                    "description": f"Reconstructed task from progress file. Task ID: {task_id}",
                    "priority": "medium",  # Default priority
                    "effort": "m",  # Default effort
                    "epic": "general",  # Default epic
                    "stage": 1,  # Default stage
                    "status": status,
                    "dependencies": [],  # No dependencies known
                    "acceptance": "Task works as expected"  # Default acceptance criteria
                }
                reconstructed_features.append(feature)
            
            return reconstructed_features
            
        except Exception as e:
            self.logger.error(f"Failed to reconstruct features: {e}")
            return []
    
    def set_features(self, features: List[Dict]):
        """Set features list dynamically"""
        self.features = features
        self._save_features_to_file()
        
    def add_feature(self, feature: Dict):
        """Add a single feature to the board"""
        self.features.append(feature)
        self._save_features_to_file()
    
    def _save_features_to_file(self):
        """Save current features to features.json file for persistence"""
        try:
            features_file = Path(__file__).parent / "features.json"
            with open(features_file, 'w', encoding='utf-8') as f:
                json.dump(self.features, f, indent=2)
            self.logger.info(f"Saved {len(self.features)} features to {features_file}")
        except Exception as e:
            self.logger.error(f"Failed to save features to file: {e}")
    
    def load_progress(self) -> Dict:
        """Load current board state from progress file and sync with features"""
        try:
            if os.path.exists(self.progress_file):
                with open(self.progress_file, 'r') as f:
                    progress_data = json.load(f)
                    
                # Sync feature statuses from progress file
                board_state = progress_data.get("boardState", {})
                for feature in self.features:
                    if feature["id"] in board_state:
                        feature["status"] = board_state[feature["id"]]
                    else:
                        feature["status"] = "backlog"
                        board_state[feature["id"]] = "backlog"
                
                # Ensure metadata exists with proper defaults
                if "metadata" not in progress_data:
                    progress_data["metadata"] = {}
                
                metadata = progress_data["metadata"]
                if "autonomousMode" not in metadata:
                    metadata["autonomousMode"] = False
                if "version" not in metadata:
                    metadata["version"] = "1.0.0"
                if "currentSession" not in metadata:
                    metadata["currentSession"] = None
                
                # Ensure other required fields exist
                if "activity" not in progress_data:
                    progress_data["activity"] = []
                if "developmentNotes" not in progress_data:
                    progress_data["developmentNotes"] = {}
                if "timestamps" not in progress_data:
                    progress_data["timestamps"] = {}
                    
                return progress_data
            else:
                return self._create_initial_progress()
        except Exception as e:
            print(f"Error loading progress: {e}")
            return self._create_initial_progress()
    
    def _create_initial_progress(self) -> Dict:
        """Create initial progress structure with proper metadata"""
        board_state = {}
        for feature in self.features:
            board_state[feature["id"]] = "backlog"
        
        return {
            "boardState": board_state,
            "activity": [],
            "metadata": {
                "lastUpdated": datetime.now().isoformat(),
                "version": "1.0.0",
                "autonomousMode": False,
                "currentSession": None
            },
            "developmentNotes": {},
            "timestamps": {}
        }
    
    def save_progress(self, progress_data: Dict):
        """Save progress data to file with proper timestamp handling and WebSocket notification"""
        self.logger.debug("📄 Starting progress save operation")
        
        # Prepare data outside of lock
        progress_data["metadata"]["lastUpdated"] = datetime.now().isoformat()
        
        # Validate progress data structure before saving
        if not self._validate_progress_structure(progress_data):
            self.logger.error("Invalid progress data structure, aborting save")
            return False
        
        temp_file = self.progress_file + ".tmp"
        
        try:
            # Perform all file I/O operations without holding the main lock
            # Use atomic write to prevent corruption during file operations
            with open(temp_file, 'w') as f:
                json.dump(progress_data, f, indent=2)
            
            # Verify the written file is valid JSON
            with open(temp_file, 'r') as f:
                json.load(f)  # This will raise an exception if invalid
            
            # Atomic move to final location (minimal lock for file operations)
            with self.lock:
                if os.path.exists(self.progress_file):
                    os.remove(self.progress_file)
                os.rename(temp_file, self.progress_file)
                
                # Update file modification time for HTML change detection
                os.utime(self.progress_file)
            
            self.logger.info(f"Progress saved to {self.progress_file}")
            
            # Notify WebSocket clients asynchronously (outside of lock)
            self.logger.debug("📡 Triggering WebSocket notifications")
            self._notify_websocket_clients_async(progress_data)
            self.logger.debug("✅ Progress save operation completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error saving progress: {e}")
            
            # Clean up temp file if it exists
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
                        
            return False
    
    def _validate_progress_structure(self, progress_data: Dict) -> bool:
        """Validate that progress data has the required structure"""
        required_keys = ["boardState", "activity", "metadata", "developmentNotes", "timestamps"]
        
        for key in required_keys:
            if key not in progress_data:
                self.logger.error(f"Missing required key in progress data: {key}")
                return False
        
        # Validate boardState structure
        if not isinstance(progress_data["boardState"], dict):
            self.logger.error("boardState must be a dictionary")
            return False
        
        # Validate activity structure
        if not isinstance(progress_data["activity"], list):
            self.logger.error("activity must be a list")
            return False
        
        # Validate metadata structure
        metadata = progress_data["metadata"]
        if not isinstance(metadata, dict):
            self.logger.error("metadata must be a dictionary")
            return False
        
        required_metadata = ["lastUpdated", "version"]
        for key in required_metadata:
            if key not in metadata:
                self.logger.error(f"Missing required metadata key: {key}")
                return False
        
        return True
    
    def get_next_task(self) -> Optional[Dict]:
        """Get the next highest priority task that's ready to work on"""
        progress = self.load_progress()
        board_state = progress["boardState"]
        
        # Find tasks that are ready (all dependencies completed)
        ready_tasks = []
        for feature in self.features:
            current_status = feature.get("status", board_state.get(feature["id"], "backlog"))
            if current_status == "backlog":
                # Check if all dependencies are done
                deps_ready = all(
                    board_state.get(dep_id, "backlog") == "done" 
                    for dep_id in feature["dependencies"]
                )
                if deps_ready:
                    ready_tasks.append(feature)
        
        if not ready_tasks:
            return None
        
        # Sort by priority (critical > high > medium > low) then by stage (earlier stages first)
        priority_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        ready_tasks.sort(
            key=lambda x: (priority_order[x["priority"]], -x["stage"]),
            reverse=True
        )
        
        return ready_tasks[0]
    
    def get_ready_tasks(self) -> List[Dict]:
        """Get all tasks that are ready to work on"""
        progress = self.load_progress()
        board_state = progress["boardState"]
        
        ready_tasks = []
        for feature in self.features:
            current_status = feature.get("status", board_state.get(feature["id"], "backlog"))
            if current_status == "backlog":
                deps_ready = all(
                    board_state.get(dep_id, "backlog") == "done" 
                    for dep_id in feature["dependencies"]
                )
                if deps_ready:
                    ready_tasks.append(feature)
        
        return ready_tasks
    
    def validate_dependencies(self, task_id: str) -> Dict[str, any]:
        """Validate if a task's dependencies are properly completed and check for circular dependencies"""
        progress = self.load_progress()
        board_state = progress.get("boardState", {})
        
        # Find the task
        feature = next((f for f in self.features if f["id"] == task_id), None)
        if not feature:
            return {"valid": False, "missing": [f"Task {task_id} not found"], "circular": []}
        
        # Check for missing dependencies (dependencies not completed)
        missing_deps = []
        for dep_id in feature.get("dependencies", []):
            dep_status = board_state.get(dep_id, "backlog")
            if dep_status != "done":
                missing_deps.append(dep_id)
        
        # Check for circular dependencies
        circular_deps = self.detect_circular_dependencies()
        
        return {
            "valid": len(missing_deps) == 0 and len(circular_deps) == 0,
            "missing": missing_deps,
            "circular": circular_deps
        }
    
    def detect_circular_dependencies(self) -> List[List[str]]:
        """Detect circular dependencies in the current feature set"""
        # Convert features to the format expected by CONFIG.detect_circular_dependencies
        tasks_data = []
        for feature in self.features:
            task_dict = {
                'id': feature.get('id'),
                'dependencies': feature.get('dependencies', [])
            }
            tasks_data.append(task_dict)
        
        return CONFIG.detect_circular_dependencies(tasks_data)
    
    def validate_new_task_dependencies(self, task_id: str, dependencies: List[str]) -> DependencyValidation:
        """Validate dependencies for a new task before adding it"""
        # Convert current features to dict format for validation
        existing_tasks = []
        for feature in self.features:
            existing_tasks.append({
                'id': feature.get('id'),
                'dependencies': feature.get('dependencies', [])
            })
        
        validation_result = CONFIG.validate_dependencies_against_tasks(task_id, dependencies, existing_tasks)
        
        return DependencyValidation(
            valid=validation_result['valid'],
            missing=validation_result['missing'],
            circular=validation_result['circular']
        )
    
    def move_card(self, task_id: str, new_status: str, notes: str = "") -> bool:
        """Move a card to a new status"""
        progress = self.load_progress()
        
        # Find the feature
        feature = next((f for f in self.features if f["id"] == task_id), None)
        if not feature:
            print(f"❌ Task {task_id} not found")
            return False
        
        # Validate dependencies if moving to ready or progress
        if new_status in ["ready", "progress"]:
            missing_deps = [
                dep for dep in feature["dependencies"]
                if progress["boardState"].get(dep, "backlog") != "done"
            ]
            if missing_deps:
                print(f"❌ Cannot move {task_id}. Missing dependencies: {missing_deps}")
                return False
        
        # Update both board state and feature status
        old_status = progress["boardState"].get(task_id, "backlog")
        progress["boardState"][task_id] = new_status
        feature["status"] = new_status
        
        # Add activity with proper content formatting
        activity_content = f"Moved '{feature['title']}' from {old_status} to {new_status}"
        if notes:
            activity_content += f" - {notes}"
        
        activity = {
            "type": "card_moved",
            "taskId": task_id,
            "taskTitle": feature["title"],
            "from": old_status,
            "to": new_status,
            "source": "autonomous",
            "notes": notes,
            "content": activity_content,
            "timestamp": datetime.now().isoformat()
        }
        progress["activity"].append(activity)
        
        # Save progress
        self.save_progress(progress)
        
        print(f"🔄 Moved '{feature['title']}' from {old_status} to {new_status}")
        if notes:
            print(f"   📝 {notes}")
        
        return True
    
    def update_progress(self, task_id: str, notes: str):
        """Add a progress update for a task"""
        progress = self.load_progress()
        
        activity_content = f"Progress update for {task_id}: {notes}"
        
        activity = {
            "type": "progress_update",
            "taskId": task_id,
            "notes": notes,
            "content": activity_content,
            "source": "autonomous",
            "timestamp": datetime.now().isoformat()
        }
        progress["activity"].append(activity)
        
        # Store in development notes
        if task_id not in progress["developmentNotes"]:
            progress["developmentNotes"][task_id] = []
        progress["developmentNotes"][task_id].append({
            "notes": notes,
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_progress(progress)
        print(f"📝 Progress update for {task_id}: {notes}")
    
    def start_development_session(self, session_name: str):
        """Start a development session"""
        progress = self.load_progress()
        
        session = {
            "name": session_name,
            "startTime": datetime.now().isoformat(),
            "tasks": []
        }
        progress["metadata"]["currentSession"] = session
        
        activity_content = f"Started development session: {session_name}"
        
        activity = {
            "type": "session_start",
            "sessionName": session_name,
            "content": activity_content,
            "source": "autonomous",
            "timestamp": datetime.now().isoformat()
        }
        progress["activity"].append(activity)
        
        self.save_progress(progress)
        print(f"🚀 Started development session: {session_name}")
    
    def end_development_session(self):
        """End the current development session"""
        progress = self.load_progress()
        
        if progress["metadata"]["currentSession"]:
            session_name = progress["metadata"]["currentSession"]["name"]
            start_time = datetime.fromisoformat(progress["metadata"]["currentSession"]["startTime"])
            duration = (datetime.now() - start_time).total_seconds()
            
            activity_content = f"Ended session: {session_name} (Duration: {duration/60:.1f} minutes)"
            
            activity = {
                "type": "session_end",
                "sessionName": session_name,
                "duration": duration,
                "content": activity_content,
                "source": "autonomous",
                "timestamp": datetime.now().isoformat()
            }
            progress["activity"].append(activity)
            progress["metadata"]["currentSession"] = None
            
            self.save_progress(progress)
            print(f"✅ Ended session: {session_name} (Duration: {duration/60:.1f} minutes)")
        else:
            print("⚠️  No active session to end")
    
    def get_board_state(self) -> Dict:
        """Get current board state - always reload features to ensure sync"""
        # Reload features from file to ensure we have current state
        self.features = self._load_features()
        
        progress = self.load_progress()
        return {
            "features": self.features,
            "boardState": progress["boardState"],
            "activity": progress["activity"],
            "metadata": progress["metadata"],
            "isManualMode": self.is_manual_mode,
            "pendingActions": len(self.pending_claude_actions)
        }
    
    def refresh_and_notify_clients(self):
        """Refresh board state from files and notify all WebSocket clients"""
        # Force reload features from file
        self.features = self._load_features()
        
        # Get current progress and ensure board state is in sync
        progress = self.load_progress()
        
        # Remove any board state entries for features that no longer exist
        if self.features:
            existing_feature_ids = {f["id"] for f in self.features}
            progress["boardState"] = {
                task_id: status for task_id, status in progress["boardState"].items()
                if task_id in existing_feature_ids
            }
        else:
            # If no features, clear the board state completely
            progress["boardState"] = {}
        
        # Save the cleaned progress
        self.save_progress(progress)
        
        # Notify all WebSocket clients with force refresh
        self._notify_websocket_clients(progress)
        
        self.logger.info(f"Refreshed board state: {len(self.features)} features, {len(self.websocket_clients)} clients notified")
    
    # ===== MODE MANAGEMENT AND ACCESS CONTROL =====
    
    def set_manual_mode(self, enabled: bool, user_source: str = "UI") -> bool:
        """Set manual mode state with proper synchronization"""
        with self.lock:
            old_mode = self.is_manual_mode
            self.is_manual_mode = enabled
            
            # Update progress file metadata
            progress = self.load_progress()
            progress["metadata"]["isManualMode"] = enabled
            progress["metadata"]["modeChangedBy"] = user_source
            progress["metadata"]["modeChangedAt"] = datetime.now().isoformat()
            
            if enabled and not old_mode:
                # Switching to manual mode
                self.logger.info(f"🔒 Switched to Manual Mode by {user_source}")
                progress["activity"].append({
                    "type": "mode_change",
                    "mode": "manual",
                    "source": user_source,
                    "content": f"Switched to Manual Mode - User has control",
                    "timestamp": datetime.now().isoformat()
                })
            elif not enabled and old_mode:
                # Switching to autonomous mode
                self.logger.info(f"🤖 Switched to Autonomous Mode by {user_source}")
                progress["activity"].append({
                    "type": "mode_change",
                    "mode": "autonomous", 
                    "source": user_source,
                    "content": f"Switched to Autonomous Mode - Claude can manage board",
                    "timestamp": datetime.now().isoformat()
                })
                
                # Process any pending Claude actions
                if self.pending_claude_actions:
                    progress["activity"].append({
                        "type": "pending_actions_info",
                        "count": len(self.pending_claude_actions),
                        "content": f"Claude has {len(self.pending_claude_actions)} pending actions ready to apply",
                        "timestamp": datetime.now().isoformat()
                    })
            
            self.save_progress(progress)
            
            # Notify all WebSocket clients of mode change
            self._notify_mode_change(enabled, user_source)
            
            return True
    
    def claude_action_allowed(self) -> bool:
        """Check if Claude is allowed to modify the board"""
        return not self.is_manual_mode
    
    def queue_claude_action(self, action_type: str, action_data: Dict, description: str):
        """Queue Claude action when in manual mode"""
        queued_action = {
            "type": action_type,
            "data": action_data,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "id": f"pending-{len(self.pending_claude_actions) + 1}"
        }
        self.pending_claude_actions.append(queued_action)
        self.logger.info(f"📋 Queued Claude action: {description}")
        
        # Notify WebSocket clients about pending action
        self._notify_pending_action(queued_action)
    
    def apply_pending_actions(self) -> List[Dict]:
        """Apply all pending Claude actions when switching back to autonomous mode"""
        applied_actions = []
        
        for action in self.pending_claude_actions:
            try:
                success = self._execute_pending_action(action)
                if success:
                    applied_actions.append(action)
                    self.logger.info(f"✅ Applied pending action: {action['description']}")
                else:
                    self.logger.error(f"❌ Failed to apply pending action: {action['description']}")
            except Exception as e:
                self.logger.error(f"❌ Error applying pending action: {e}")
        
        # Clear pending actions
        self.pending_claude_actions.clear()
        
        return applied_actions
    
    def _execute_pending_action(self, action: Dict) -> bool:
        """Execute a single pending action"""
        try:
            if action["type"] == "add_feature":
                feature_data = action["data"]
                self.features.append(feature_data)
                progress = self.load_progress()
                progress["boardState"][feature_data["id"]] = feature_data.get("status", "backlog")
                self.save_progress(progress)
                return True
            elif action["type"] == "move_card":
                data = action["data"]
                return self.move_card(data["task_id"], data["new_status"], data.get("notes", ""))
            elif action["type"] == "update_progress":
                data = action["data"]
                self.update_progress(data["task_id"], data["notes"])
                return True
            elif action["type"] == "import_features":
                import json
                data = action["data"]
                features_data = json.loads(data["features_json"])
                
                if not isinstance(features_data, list):
                    self.logger.error("Features JSON must be an array")
                    return False
                
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
                    
                    self.features.append(feature)
                    imported_count += 1
                
                # Update progress file
                progress = self.load_progress()
                for feature in self.features:
                    if feature["id"] not in progress["boardState"]:
                        progress["boardState"][feature["id"]] = feature["status"]
                self.save_progress(progress)
                
                self.logger.info(f"Successfully imported {imported_count} features from pending action")
                return True
            # Add more action types as needed
            return False
        except Exception as e:
            self.logger.error(f"Error executing pending action: {e}")
            return False
    
    def get_pending_actions_summary(self) -> str:
        """Get human-readable summary of pending Claude actions"""
        if not self.pending_claude_actions:
            return "No pending actions"
        
        summary = f"Claude has {len(self.pending_claude_actions)} pending actions:\n"
        for i, action in enumerate(self.pending_claude_actions, 1):
            summary += f"{i}. {action['description']}\n"
        
        return summary
    
    def clear_pending_actions(self):
        """Clear all pending Claude actions"""
        count = len(self.pending_claude_actions)
        self.pending_claude_actions.clear()
        self.logger.info(f"🗑️ Cleared {count} pending Claude actions")
    
    # ===== CLEARING AND REMOVAL METHODS =====
    
    def clear_all_features(self) -> bool:
        """Clear all features from the board while preserving project structure"""
        self.logger.info("🧹 Starting clear all features operation")
        with self.lock:
            try:
                cleared_count = len(self.features)
                self.logger.debug(f"Clearing {cleared_count} features")
                
                # Clear features
                self.logger.debug("Loading progress data")
                progress = self.load_progress()
                self.features = []
                
                # Clear board state but preserve structure
                progress["boardState"] = {}
                progress["developmentNotes"] = {}
                
                # Add activity log
                progress["activity"].append({
                    "type": "board_cleared",
                    "content": f"Cleared all {cleared_count} tasks from kanban board",
                    "source": "autonomous",
                    "timestamp": datetime.now().isoformat(),
                    "cleared_count": cleared_count
                })
                
                # Save updated progress
                self.logger.debug("Saving cleared progress data")
                success = self.save_progress(progress)
                
                if success:
                    # Save empty features file
                    self.logger.debug("Saving empty features file")
                    self._save_features_to_file()
                    self.logger.info(f"Successfully cleared {cleared_count} features from board")
                    
                    # Force refresh and notify clients
                    try:
                        self.logger.debug("Refreshing and notifying clients")
                        self.refresh_and_notify_clients()
                    except Exception as e:
                        self.logger.error(f"Error refreshing clients after clear: {e}")
                    
                    return True
                else:
                    self.logger.error("Failed to save progress after clearing")
                    return False
                    
            except Exception as e:
                self.logger.error(f"Error clearing all features: {e}")
                return False
    
    def delete_project(self) -> bool:
        """Delete the entire project and all associated data"""
        with self.lock:
            try:
                # Clear all in-memory data
                cleared_features = len(self.features)
                self.features = []
                self.pending_claude_actions = []
                
                # Delete progress file
                if os.path.exists(self.progress_file):
                    os.remove(self.progress_file)
                    self.logger.info(f"Deleted progress file: {self.progress_file}")
                
                # Delete features file
                features_file = Path(__file__).parent / "features.json"
                if features_file.exists():
                    os.remove(str(features_file))
                    self.logger.info(f"Deleted features file: {features_file}")
                
                # Notify WebSocket clients of complete reset
                try:
                    self._notify_websocket_clients({
                        "boardState": {},
                        "activity": [],
                        "metadata": {
                            "lastUpdated": datetime.now().isoformat(),
                            "version": "1.0.0",
                            "autonomousMode": False,
                            "currentSession": None
                        }
                    })
                except Exception as e:
                    self.logger.error(f"Error notifying clients after project deletion: {e}")
                
                self.logger.info(f"Successfully deleted project with {cleared_features} features")
                return True
                
            except Exception as e:
                self.logger.error(f"Error deleting project: {e}")
                return False
    
    def remove_feature_by_id(self, task_id: str) -> bool:
        """Remove a specific feature by ID"""
        # Prepare data changes outside of lock first
        feature_to_remove = None
        updated_features = None
        
        # Quick lock to get data and prepare changes
        with self.lock:
            try:
                # Find the feature
                feature_to_remove = next((f for f in self.features if f["id"] == task_id), None)
                if not feature_to_remove:
                    self.logger.warning(f"Feature {task_id} not found for removal")
                    return False
                
                # Prepare updated features list
                updated_features = [f for f in self.features if f["id"] != task_id]
                
            except Exception as e:
                self.logger.error(f"Error preparing feature removal {task_id}: {e}")
                return False
        
        # Perform I/O operations outside of lock
        try:
            # Load progress outside of main lock
            progress = self.load_progress()
            
            # Prepare all changes
            if task_id in progress["boardState"]:
                del progress["boardState"][task_id]
            
            if task_id in progress["developmentNotes"]:
                del progress["developmentNotes"][task_id]
            
            # Add activity log
            progress["activity"].append({
                "type": "feature_removed",
                "taskId": task_id,
                "taskTitle": feature_to_remove["title"],
                "content": f"Removed task '{feature_to_remove['title']}' ({task_id})",
                "source": "autonomous",
                "timestamp": datetime.now().isoformat()
            })
            
            # Save progress (this has its own minimal locking)
            success = self.save_progress(progress)
            
            if success:
                # Apply the feature list change with minimal lock time
                with self.lock:
                    self.features = updated_features
                
                # Save features file outside of main lock
                self._save_features_to_file()
                self.logger.info(f"Successfully removed feature: {feature_to_remove['title']} ({task_id})")
                return True
            else:
                self.logger.error(f"Failed to save progress after removing {task_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error removing feature {task_id}: {e}")
            return False
    
    def remove_multiple_features(self, task_ids: List[str]) -> Tuple[bool, int]:
        """Remove multiple features by IDs"""
        # Prepare data changes outside of lock first
        removed_features = []
        updated_features = None
        
        # Quick lock to get data and prepare changes
        with self.lock:
            try:
                # Find all features to remove
                for task_id in task_ids:
                    feature = next((f for f in self.features if f["id"] == task_id), None)
                    if feature:
                        removed_features.append(feature)
                
                if not removed_features:
                    self.logger.warning("No valid features found for bulk removal")
                    return False, 0
                
                # Prepare updated features list
                original_count = len(self.features)
                updated_features = [f for f in self.features if f["id"] not in task_ids]
                removed_count = original_count - len(updated_features)
                
            except Exception as e:
                self.logger.error(f"Error preparing bulk feature removal: {e}")
                return False, 0
        
        # Perform I/O operations outside of lock
        try:
            # Load progress outside of main lock
            progress = self.load_progress()
            
            # Update progress file
            for task_id in task_ids:
                # Remove from board state
                if task_id in progress["boardState"]:
                    del progress["boardState"][task_id]
                
                # Remove development notes
                if task_id in progress["developmentNotes"]:
                    del progress["developmentNotes"][task_id]
            
            # Add activity log for bulk operation
            removed_titles = [f["title"] for f in removed_features]
            removed_count = len(removed_features)
            progress["activity"].append({
                "type": "bulk_features_removed",
                "content": f"Bulk removed {removed_count} tasks: {', '.join(removed_titles[:3])}{'...' if len(removed_titles) > 3 else ''}",
                "source": "autonomous",
                "timestamp": datetime.now().isoformat(),
                "removed_count": removed_count,
                "task_ids": task_ids
            })
            
            # Save changes (this has its own minimal locking)
            success = self.save_progress(progress)
            
            if success:
                # Apply the feature list change with minimal lock time
                with self.lock:
                    self.features = updated_features
                
                # Save features file outside of main lock
                self._save_features_to_file()
                self.logger.info(f"Successfully removed {removed_count} features in bulk operation")
                return True, removed_count
            else:
                self.logger.error("Failed to save progress after bulk removal")
                return False, removed_count
            
        except Exception as e:
            self.logger.error(f"Error in bulk feature removal: {e}")
            return False, 0
    
    def reset_to_initial_state(self) -> bool:
        """Reset the entire board to initial empty state"""
        with self.lock:
            try:
                # Clear all data
                cleared_features = len(self.features)
                self.features = []
                self.pending_claude_actions = []
                self.is_manual_mode = False
                
                # Create fresh initial progress
                initial_progress = self._create_initial_progress()
                
                # Add activity log for reset
                initial_progress["activity"].append({
                    "type": "board_reset",
                    "content": f"Board reset to initial state - {cleared_features} tasks removed",
                    "source": "autonomous",
                    "timestamp": datetime.now().isoformat(),
                    "cleared_count": cleared_features
                })
                
                # Save fresh state
                success = self.save_progress(initial_progress)
                
                if success:
                    # Save empty features file
                    self._save_features_to_file()
                    self.logger.info(f"Successfully reset board to initial state - removed {cleared_features} features")
                    return True
                else:
                    self.logger.error("Failed to save progress after reset")
                    return False
                
            except Exception as e:
                self.logger.error(f"Error resetting board to initial state: {e}")
                return False
    
    # ===== MANUAL MODE TASK MANAGEMENT =====
    
    def add_manual_task(self, task_data: Dict) -> str:
        """Add task created manually by user"""
        if not self.is_manual_mode:
            return "Cannot add manual task - not in manual mode"
        
        # Ensure unique ID
        if not task_data.get("id"):
            task_data["id"] = f"manual-{self.next_task_id}"
            self.next_task_id += 1
        
        # Add to features list
        self.features.append(task_data)
        
        # Save features to file immediately
        self._save_features_to_file()
        
        # Update progress
        progress = self.load_progress()
        progress["boardState"][task_data["id"]] = task_data.get("status", "backlog")
        
        # Add activity
        progress["activity"].append({
            "type": "manual_task_added",
            "taskId": task_data["id"],
            "taskTitle": task_data["title"],
            "source": "manual",
            "content": f"User added task: {task_data['title']}",
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_progress(progress)
        self.logger.info(f"📝 User added task: {task_data['title']}")
        
        return f"✅ Task '{task_data['title']}' added successfully"
    
    def update_manual_task(self, task_id: str, updated_data: Dict) -> str:
        """Update task modified manually by user"""
        if not self.is_manual_mode:
            return "Cannot update manual task - not in manual mode"
        
        # Find and update feature
        feature = next((f for f in self.features if f["id"] == task_id), None)
        if not feature:
            return f"Task {task_id} not found"
        
        old_title = feature["title"]
        
        # Update feature data
        for key, value in updated_data.items():
            if key != "id":  # Don't allow ID changes
                feature[key] = value
        
        # Save updated features to file immediately
        self._save_features_to_file()
        
        # Update progress
        progress = self.load_progress()
        progress["activity"].append({
            "type": "manual_task_updated",
            "taskId": task_id,
            "taskTitle": feature["title"],
            "source": "manual",
            "content": f"User updated task: {feature['title']}",
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_progress(progress)
        self.logger.info(f"✏️ User updated task: {old_title} -> {feature['title']}")
        
        return f"✅ Task '{feature['title']}' updated successfully"
    
    def delete_manual_task(self, task_id: str) -> str:
        """Delete task manually by user"""
        if not self.is_manual_mode:
            return "Cannot delete manual task - not in manual mode"
        
        # Find and remove feature
        feature = next((f for f in self.features if f["id"] == task_id), None)
        if not feature:
            return f"Task {task_id} not found"
        
        task_title = feature["title"]
        self.features = [f for f in self.features if f["id"] != task_id]
        
        # Save updated features to file immediately
        self._save_features_to_file()
        
        # Update progress
        progress = self.load_progress()
        if task_id in progress["boardState"]:
            del progress["boardState"][task_id]
        
        # Remove development notes if they exist
        if task_id in progress.get("developmentNotes", {}):
            del progress["developmentNotes"][task_id]
        
        progress["activity"].append({
            "type": "manual_task_deleted",
            "taskId": task_id,
            "taskTitle": task_title,
            "source": "manual",
            "content": f"User deleted task: {task_title}",
            "timestamp": datetime.now().isoformat()
        })
        
        self.save_progress(progress)
        self.logger.info(f"🗑️ User deleted task: {task_title}")
        
        return f"✅ Task '{task_title}' deleted successfully"
    
    def _notify_mode_change(self, is_manual: bool, source: str):
        """Notify WebSocket clients of mode change"""
        notification = {
            "type": "mode_changed",
            "isManualMode": is_manual,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "pendingActions": len(self.pending_claude_actions)
        }
        
        self._broadcast_to_websockets(notification)
    
    def _notify_pending_action(self, action: Dict):
        """Notify WebSocket clients of new pending action"""
        notification = {
            "type": "claude_action_blocked",
            "action": action,
            "totalPending": len(self.pending_claude_actions)
        }
        
        self._broadcast_to_websockets(notification)
    
    def _broadcast_to_websockets(self, message: Dict):
        """Broadcast message to all WebSocket clients"""
        if not self.websocket_clients:
            return
        
        disconnected_clients = set()
        for client in self.websocket_clients:
            try:
                asyncio.create_task(client.send(json.dumps(message)))
            except Exception as e:
                self.logger.error(f"Failed to send notification to client: {e}")
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        self.websocket_clients -= disconnected_clients
    
    def print_status(self):
        """Print current kanban status"""
        progress = self.load_progress()
        board_state = progress["boardState"]
        
        print("\n🚀 Project Development Status")
        print("=" * 50)
        
        # Count by status
        status_counts = {}
        for status in board_state.values():
            status_counts[status] = status_counts.get(status, 0) + 1
        
        total = len(self.features)
        done = status_counts.get("done", 0)
        progress_count = status_counts.get("progress", 0)
        
        print(f"📊 Total Features: {total}")
        completion_pct = f"({done/total*100:.1f}%)" if total > 0 else "(0.0%)"
        print(f"✅ Completed: {done} {completion_pct}")
        print(f"🔧 In Progress: {progress_count}")
        print(f"📋 Backlog: {status_counts.get('backlog', 0)}")
        print(f"⚡ Ready: {status_counts.get('ready', 0)}")
        print(f"🧪 Testing: {status_counts.get('testing', 0)}")
        
        # Show next task
        next_task = self.get_next_task()
        if next_task:
            print(f"\n🎯 Next Task: {next_task['title']} (Stage {next_task['stage']}, {next_task['priority']} priority)")
        else:
            print("\n🏁 No tasks ready for development")
        
        # Show current session
        if progress["metadata"]["currentSession"]:
            session = progress["metadata"]["currentSession"]
            print(f"\n🚀 Active Session: {session['name']}")
        
        print()
    
    async def start_websocket_server(self):
        """Start WebSocket server for real-time updates with fallback port selection"""
        original_port = self.websocket_port
        
        for attempt in range(5):  # Try up to 5 different ports
            try:
                self.websocket_server = await websockets.serve(
                    self._handle_websocket_connection,
                    CONFIG.WEBSOCKET_HOST,
                    self.websocket_port
                )
                self.logger.info(f"WebSocket server started on {CONFIG.WEBSOCKET_HOST}:{self.websocket_port}")
                return
            except OSError as e:
                if "Address already in use" in str(e):
                    self.logger.warning(f"Port {self.websocket_port} is in use, trying {self.websocket_port + 1}")
                    self.websocket_port += 1
                else:
                    self.logger.error(f"Failed to start WebSocket server on port {self.websocket_port}: {e}")
                    break
            except Exception as e:
                self.logger.error(f"Unexpected error starting WebSocket server: {e}")
                break
        
        # If we get here, all attempts failed
        self.logger.error(f"Failed to start WebSocket server after trying ports {original_port}-{self.websocket_port}")
        self.websocket_port = original_port  # Reset to original port
    
    async def stop_websocket_server(self):
        """Stop WebSocket server"""
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            self.logger.info("WebSocket server stopped")
    
    async def _handle_websocket_connection(self, websocket):
        """Handle new WebSocket connections"""
        self.websocket_clients.add(websocket)
        self.logger.info(f"WebSocket client connected. Total clients: {len(self.websocket_clients)}")
        
        try:
            # Send current state to new client
            current_state = self.get_board_state()
            await websocket.send(json.dumps({
                "type": "initial_state",
                "data": current_state
            }))
            
            # Listen for messages from client
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self._handle_websocket_message(websocket, data)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
                except Exception as e:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": str(e)
                    }))
                    
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.error(f"WebSocket error: {e}")
        finally:
            self.websocket_clients.discard(websocket)
            self.logger.info(f"WebSocket client disconnected. Total clients: {len(self.websocket_clients)}")
    
    async def _handle_websocket_message(self, websocket, data: Dict):
        """Handle messages from WebSocket clients"""
        message_type = data.get("type")
        self.logger.info(f"🔔 Handling WebSocket message: {message_type} from client")
        
        if message_type == "move_card":
            task_id = data.get("taskId")
            new_status = data.get("newStatus")
            notes = data.get("notes", "Moved via UI")
            
            success = self.move_card(task_id, new_status, notes)
            
            await websocket.send(json.dumps({
                "type": "move_card_response",
                "success": success,
                "taskId": task_id,
                "newStatus": new_status
            }))
            
        elif message_type == "update_progress":
            task_id = data.get("taskId")
            notes = data.get("notes")
            
            self.update_progress(task_id, notes)
            
            await websocket.send(json.dumps({
                "type": "update_progress_response",
                "success": True,
                "taskId": task_id
            }))
            
        elif message_type == "get_board_state":
            board_state = self.get_board_state()
            await websocket.send(json.dumps({
                "type": "board_state",
                "data": board_state
            }))
        
        elif message_type == "refresh_board":
            # Force refresh from files and notify all clients
            self.refresh_and_notify_clients()
            await websocket.send(json.dumps({
                "type": "refresh_response",
                "success": True
            }))
        
        # ===== MODE MANAGEMENT MESSAGES =====
        elif message_type == "set_mode":
            is_manual = data.get("isManualMode", False)
            success = self.set_manual_mode(is_manual, "UI")
            
            await websocket.send(json.dumps({
                "type": "set_mode_response",
                "success": success,
                "isManualMode": is_manual,
                "pendingActions": len(self.pending_claude_actions)
            }))
        
        elif message_type == "get_pending_actions":
            summary = self.get_pending_actions_summary()
            await websocket.send(json.dumps({
                "type": "pending_actions_response",
                "summary": summary,
                "actions": self.pending_claude_actions
            }))
        
        elif message_type == "apply_pending_actions":
            applied = self.apply_pending_actions()
            await websocket.send(json.dumps({
                "type": "pending_actions_applied",
                "appliedCount": len(applied),
                "actions": applied
            }))
        
        elif message_type == "clear_pending_actions":
            self.clear_pending_actions()
            await websocket.send(json.dumps({
                "type": "pending_actions_cleared",
                "success": True
            }))
        
        # ===== MANUAL TASK MANAGEMENT MESSAGES =====
        elif message_type == "manual_task_added":
            task_data = data.get("task", {})
            result = self.add_manual_task(task_data)
            
            await websocket.send(json.dumps({
                "type": "manual_task_response",
                "action": "added",
                "success": "✅" in result,
                "message": result,
                "taskId": task_data.get("id")
            }))
        
        elif message_type == "manual_task_updated":
            task_data = data.get("task", {})
            task_id = task_data.get("id")
            result = self.update_manual_task(task_id, task_data)
            
            await websocket.send(json.dumps({
                "type": "manual_task_response", 
                "action": "updated",
                "success": "✅" in result,
                "message": result,
                "taskId": task_id
            }))
        
        elif message_type == "manual_task_deleted":
            task_id = data.get("taskId")
            result = self.delete_manual_task(task_id)
            
            await websocket.send(json.dumps({
                "type": "manual_task_response",
                "action": "deleted", 
                "success": "✅" in result,
                "message": result,
                "taskId": task_id
            }))
        
        elif message_type == "manual_bulk_move":
            task_ids = data.get("taskIds", [])
            new_status = data.get("newStatus")
            
            if self.is_manual_mode:
                moved_count = 0
                for task_id in task_ids:
                    success = self.move_card(task_id, new_status, f"Bulk moved to {new_status} via UI")
                    if success:
                        moved_count += 1
                
                await websocket.send(json.dumps({
                    "type": "bulk_move_response",
                    "success": moved_count > 0,
                    "movedCount": moved_count,
                    "totalRequested": len(task_ids),
                    "newStatus": new_status
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "bulk_move_response",
                    "success": False,
                    "message": "Not in manual mode"
                }))
        
        elif message_type == "manual_bulk_delete":
            task_ids = data.get("taskIds", [])
            
            if self.is_manual_mode:
                deleted_count = 0
                for task_id in task_ids:
                    result = self.delete_manual_task(task_id)
                    if "✅" in result:
                        deleted_count += 1
                
                await websocket.send(json.dumps({
                    "type": "bulk_delete_response",
                    "success": deleted_count > 0,
                    "deletedCount": deleted_count,
                    "totalRequested": len(task_ids)
                }))
            else:
                await websocket.send(json.dumps({
                    "type": "bulk_delete_response",
                    "success": False,
                    "message": "Not in manual mode"
                }))
        
        # ===== CLEARING AND REMOVAL MESSAGES =====
        elif message_type == "clear_kanban":
            confirm = data.get("confirm", False)
            
            if not confirm:
                await websocket.send(json.dumps({
                    "type": "clear_kanban_response",
                    "success": False,
                    "message": "Confirmation required"
                }))
            else:
                try:
                    # Use the controller's clear method directly
                    success = self.clear_all_features()
                    message = "Board cleared successfully" if success else "Failed to clear board"
                    
                    await websocket.send(json.dumps({
                        "type": "clear_kanban_response",
                        "success": success,
                        "message": message
                    }))
                    
                    # Force refresh board state for all clients if successful
                    if success:
                        self.refresh_and_notify_clients()
                    
                    self.logger.info(f"Clear kanban via WebSocket: {'success' if success else 'failed'}")
                except Exception as e:
                    self.logger.error(f"Error clearing kanban via WebSocket: {e}")
                    await websocket.send(json.dumps({
                        "type": "clear_kanban_response",
                        "success": False,
                        "message": f"Error clearing board: {str(e)}"
                    }))
        
        elif message_type == "delete_project":
            confirm = data.get("confirm", False)
            
            if not confirm:
                await websocket.send(json.dumps({
                    "type": "delete_project_response",
                    "success": False,
                    "message": "Confirmation required"
                }))
            else:
                try:
                    # Use the controller's delete method directly
                    success = self.delete_project()
                    message = "Project deleted successfully" if success else "Failed to delete project"
                    
                    await websocket.send(json.dumps({
                        "type": "delete_project_response",
                        "success": success,
                        "message": message
                    }))
                    
                    # Force refresh board state for all clients if successful
                    if success:
                        self.refresh_and_notify_clients()
                    
                    self.logger.info(f"Delete project via WebSocket: {'success' if success else 'failed'}")
                except Exception as e:
                    self.logger.error(f"Error deleting project via WebSocket: {e}")
                    await websocket.send(json.dumps({
                        "type": "delete_project_response",
                        "success": False,
                        "message": f"Error deleting project: {str(e)}"
                    }))
        
        elif message_type == "clear_column":
            status = data.get("status")
            confirm = data.get("confirm", False)
            
            if not status:
                await websocket.send(json.dumps({
                    "type": "clear_column_response",
                    "success": False,
                    "message": "Status parameter required"
                }))
            elif not confirm:
                await websocket.send(json.dumps({
                    "type": "clear_column_response",
                    "success": False,
                    "message": "Confirmation required"
                }))
            else:
                # Get tasks in this column
                tasks_in_column = [f["id"] for f in self.features if f.get("status", "backlog") == status]
                
                if not tasks_in_column:
                    await websocket.send(json.dumps({
                        "type": "clear_column_response",
                        "success": True,
                        "message": f"No tasks in {status} column",
                        "status": status,
                        "removedCount": 0
                    }))
                else:
                    success, removed_count = self.remove_multiple_features(tasks_in_column)
                    await websocket.send(json.dumps({
                        "type": "clear_column_response",
                        "success": success,
                        "message": f"Cleared {removed_count} tasks from {status} column" if success else "Failed to clear column",
                        "status": status,
                        "removedCount": removed_count
                    }))
        
        elif message_type == "remove_feature":
            task_id = data.get("taskId")
            
            if not task_id:
                await websocket.send(json.dumps({
                    "type": "remove_feature_response",
                    "success": False,
                    "message": "Task ID required"
                }))
            else:
                success = self.remove_feature_by_id(task_id)
                await websocket.send(json.dumps({
                    "type": "remove_feature_response",
                    "success": success,
                    "message": "Task removed successfully" if success else "Failed to remove task",
                    "taskId": task_id
                }))
        
        elif message_type == "remove_features":
            task_ids = data.get("taskIds", [])
            
            if not task_ids:
                await websocket.send(json.dumps({
                    "type": "remove_features_response",
                    "success": False,
                    "message": "Task IDs required"
                }))
            else:
                success, removed_count = self.remove_multiple_features(task_ids)
                await websocket.send(json.dumps({
                    "type": "remove_features_response",
                    "success": success,
                    "message": f"Removed {removed_count} tasks successfully" if success else "Failed to remove tasks",
                    "removedCount": removed_count,
                    "totalRequested": len(task_ids)
                }))
            
        else:
            await websocket.send(json.dumps({
                "type": "error",
                "message": f"Unknown message type: {message_type}"
            }))
    
    def _notify_websocket_clients(self, progress_data: Dict):
        """Notify all WebSocket clients of state changes (synchronous version for compatibility)"""
        if not self.websocket_clients:
            return
        
        # Prepare notification data
        notification = {
            "type": "state_update",
            "data": {
                "features": self.features,
                "boardState": progress_data["boardState"],
                "activity": progress_data["activity"],
                "metadata": progress_data["metadata"]
            }
        }
        
        self.logger.info(f"📡 Notifying {len(self.websocket_clients)} WebSocket clients of state update")
        
        # Send to all connected clients using proper async scheduling
        self._schedule_websocket_notifications(notification)
    
    def _notify_websocket_clients_async(self, progress_data: Dict):
        """Notify all WebSocket clients of state changes (non-blocking async version)"""
        if not self.websocket_clients:
            return
        
        # Prepare notification data
        notification = {
            "type": "state_update",
            "data": {
                "features": self.features,
                "boardState": progress_data["boardState"],
                "activity": progress_data["activity"],
                "metadata": progress_data["metadata"]
            }
        }
        
        self.logger.info(f"📡 Notifying {len(self.websocket_clients)} WebSocket clients of state update (async)")
        
        # Use a separate thread to avoid blocking the main thread
        def async_notify():
            try:
                self._schedule_websocket_notifications(notification)
            except Exception as e:
                self.logger.error(f"Error in async WebSocket notification: {e}")
        
        # Run in background thread to prevent blocking
        notification_thread = threading.Thread(target=async_notify, daemon=True)
        notification_thread.start()
    
    def _schedule_websocket_notifications(self, notification):
        """Schedule WebSocket notifications in a thread-safe way with timeout protection"""
        self.logger.debug(f"🔄 Scheduling WebSocket notifications for {len(self.websocket_clients)} clients")
        
        # Quick check - if no clients, skip processing
        if not self.websocket_clients:
            self.logger.debug("No WebSocket clients to notify")
            return
        
        try:
            # Try to get the current event loop with timeout protection
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self.logger.debug("✅ Event loop is running, scheduling notifications")
                    # Use asyncio.create_task with timeout protection
                    def safe_schedule():
                        try:
                            task = asyncio.create_task(self._send_notifications_async(notification))
                            # Add done callback for error handling
                            task.add_done_callback(self._notification_task_done)
                        except Exception as e:
                            self.logger.error(f"Error creating notification task: {e}")
                    
                    loop.call_soon_threadsafe(safe_schedule)
                else:
                    self.logger.debug("⚠️ Event loop exists but not running, running in background thread")
                    self._run_notifications_in_background_thread(notification)
            except RuntimeError:
                # No event loop in current thread, create one in a background thread
                self.logger.debug("🔧 No event loop, creating background thread for notifications")
                self._run_notifications_in_background_thread(notification)
                
        except Exception as e:
            self.logger.error(f"Error scheduling WebSocket notifications: {e}")
            # Fallback: try simple synchronous notification to at least some clients
            self._fallback_sync_notification(notification)
    
    def _notification_task_done(self, task):
        """Callback for when notification task completes"""
        try:
            if task.exception():
                self.logger.error(f"WebSocket notification task failed: {task.exception()}")
        except Exception as e:
            self.logger.error(f"Error in notification task callback: {e}")
    
    def _fallback_sync_notification(self, notification):
        """Fallback synchronous notification method"""
        self.logger.debug("Using fallback sync notification")
        try:
            disconnected_clients = set()
            for client in list(self.websocket_clients):  # Create a copy
                try:
                    # Only try if the client connection is still open
                    if client.open:
                        client.send(json.dumps(notification))
                except Exception as e:
                    self.logger.debug(f"Client notification failed (will remove): {e}")
                    disconnected_clients.add(client)
            
            # Clean up disconnected clients
            if disconnected_clients:
                self.websocket_clients -= disconnected_clients
                self.logger.info(f"Removed {len(disconnected_clients)} disconnected clients")
                
        except Exception as e:
            self.logger.error(f"Error in fallback sync notification: {e}")
    
    def _run_notifications_in_background_thread(self, notification):
        """Run WebSocket notifications in a background thread with its own event loop"""
        def background_notification_runner():
            try:
                # Create a new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                # Run the notification coroutine
                loop.run_until_complete(self._send_notifications_async(notification))
                self.logger.debug("✅ Background WebSocket notifications completed")
                
            except Exception as e:
                self.logger.error(f"❌ Error in background WebSocket notifications: {e}")
            finally:
                # Clean up the event loop
                try:
                    loop.close()
                except:
                    pass
        
        # Start the background thread
        notification_thread = threading.Thread(target=background_notification_runner, daemon=True)
        notification_thread.start()
        self.logger.debug("🚀 Started background thread for WebSocket notifications")
    
    async def _send_notifications_async(self, notification):
        """Send notifications to all clients asynchronously with timeout protection"""
        self.logger.debug("📤 Starting async notification send")
        disconnected_clients = set()
        
        # Quick check for clients
        if not self.websocket_clients:
            self.logger.debug("No clients to notify")
            return
        
        # Create tasks for all notifications with individual timeouts
        tasks = []
        client_count = len(self.websocket_clients)
        
        # Use a copy to avoid modification during iteration
        clients_copy = list(self.websocket_clients)
        
        for i, client in enumerate(clients_copy):
            self.logger.debug(f"Creating notification task {i+1}/{client_count}")
            try:
                # Create task with individual timeout wrapper
                task = asyncio.create_task(
                    asyncio.wait_for(
                        self._send_notification_to_client(client, notification, disconnected_clients),
                        timeout=2.0  # 2 second timeout per client
                    )
                )
                tasks.append(task)
            except Exception as e:
                self.logger.error(f"Error creating task for client {i+1}: {e}")
                disconnected_clients.add(client)
        
        # Wait for all notifications to complete with overall timeout
        if tasks:
            self.logger.debug(f"Executing {len(tasks)} notification tasks")
            try:
                # Use asyncio.gather with return_exceptions=True to handle individual failures
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True), 
                    timeout=10.0  # Overall timeout of 10 seconds
                )
                
                # Check results for timeouts or errors
                error_count = sum(1 for r in results if isinstance(r, Exception))
                if error_count > 0:
                    self.logger.warning(f"⚠️ {error_count} WebSocket notifications failed")
                else:
                    self.logger.debug("✅ All WebSocket notifications completed successfully")
                    
            except asyncio.TimeoutError:
                self.logger.warning("⏰ WebSocket notifications timed out (overall timeout)")
                # Cancel remaining tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
            except Exception as e:
                self.logger.error(f"❌ Error in WebSocket notifications: {e}")
        else:
            self.logger.debug("No WebSocket notification tasks to execute")
        
        # Remove disconnected clients (thread-safe)
        if disconnected_clients:
            try:
                self.websocket_clients -= disconnected_clients
                self.logger.info(f"🧹 Removed {len(disconnected_clients)} disconnected clients")
            except Exception as e:
                self.logger.error(f"Error removing disconnected clients: {e}")
        
        self.logger.debug("📤 Async notification send completed")
    
    async def _send_notification_to_client(self, client, notification, disconnected_clients):
        """Send notification to a single client"""
        try:
            await client.send(json.dumps(notification))
        except Exception as e:
            self.logger.error(f"Failed to send notification to client: {e}")
            disconnected_clients.add(client)
    
    def start_websocket_server_thread(self):
        """Start WebSocket server in a separate thread"""
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start_websocket_server())
                self.logger.info(f"WebSocket server running continuously on port {self.websocket_port}")
                # Keep the event loop running to serve WebSocket connections
                loop.run_forever()
            except Exception as e:
                self.logger.error(f"WebSocket server error: {e}")
            finally:
                self.logger.info("WebSocket server thread ending")
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        self.logger.info("WebSocket server thread started")

# Example usage functions
def demo_autonomous_development():
    """Demonstrate autonomous development workflow"""
    kanban = KanbanController()
    
    print("🤖 Starting autonomous development demo...")
    
    # Start a session
    kanban.start_development_session("Stage 1 Core Development")
    
    # Get and work on tasks
    for i in range(3):  # Work on 3 tasks
        next_task = kanban.get_next_task()
        if not next_task:
            print("No more tasks ready!")
            break
        
        print(f"\n🎯 Working on: {next_task['title']}")
        
        # Move to progress
        kanban.move_card(next_task["id"], "progress", "Starting development")
        
        # Simulate development time
        time.sleep(1)
        
        # Add progress update
        kanban.update_progress(next_task["id"], "Implementation in progress...")
        
        # Simulate more development
        time.sleep(1)
        
        # Move to testing
        kanban.move_card(next_task["id"], "testing", "Development complete, starting tests")
        
        time.sleep(0.5)
        
        # Move to done
        kanban.move_card(next_task["id"], "done", "Tests passed, feature complete")
    
    # End session
    kanban.end_development_session()
    
    # Show final status
    kanban.print_status()

if __name__ == "__main__":
    kanban = KanbanController()
    kanban.print_status()
    
    # Uncomment to run demo:
    # demo_autonomous_development()