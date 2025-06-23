#!/usr/bin/env python3
"""
Proper MCP Protocol Implementation
JSON-RPC 2.0 compliant Model Context Protocol server
"""

import json
import sys
import asyncio
import logging
import functools
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

class MCPError(Exception):
    """MCP-specific error"""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

def timeout_protection(timeout_seconds: float = 30.0):
    """Decorator to add timeout protection to tool handlers"""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logging.error(f"Tool handler {func.__name__} timed out after {timeout_seconds} seconds")
                raise MCPError(-32603, f"Tool execution timed out after {timeout_seconds} seconds")
            except Exception as e:
                logging.error(f"Tool handler {func.__name__} failed: {str(e)}")
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                # For sync functions, we can't easily add timeout without threading
                return func(*args, **kwargs)
            except Exception as e:
                logging.error(f"Tool handler {func.__name__} failed: {str(e)}")
                raise
        
        # Return the appropriate wrapper based on whether the function is async
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class MCPServer:
    """Proper MCP Protocol Server Implementation"""
    
    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self.tools = {}
        self.resources = {}
        self.prompts = {}
        self.initialized = False
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"mcp.{name}")
        
    def add_tool(self, name: str, description: str, input_schema: Dict[str, Any], handler: Callable):
        """Add a tool to the server"""
        self.tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
            "handler": handler
        }
        self.logger.info(f"Added tool: {name}")
    
    def add_resource(self, uri: str, name: str, description: str, mime_type: str, handler: Callable):
        """Add a resource to the server"""
        self.resources[uri] = {
            "uri": uri,
            "name": name,
            "description": description,
            "mimeType": mime_type,
            "handler": handler
        }
        self.logger.info(f"Added resource: {uri}")
    
    def add_prompt(self, name: str, description: str, arguments: List[Dict], handler: Callable):
        """Add a prompt to the server"""
        self.prompts[name] = {
            "name": name,
            "description": description,
            "arguments": arguments,
            "handler": handler
        }
        self.logger.info(f"Added prompt: {name}")
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests"""
        try:
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")
            
            self.logger.debug(f"Handling request: {method}")
            
            # Handle different MCP methods
            if method == "initialize":
                return await self._handle_initialize(params, request_id)
            elif method == "tools/list":
                return await self._handle_tools_list(request_id)
            elif method == "tools/call":
                return await self._handle_tools_call(params, request_id)
            elif method == "resources/list":
                return await self._handle_resources_list(request_id)
            elif method == "resources/read":
                return await self._handle_resources_read(params, request_id)
            elif method == "prompts/list":
                return await self._handle_prompts_list(request_id)
            elif method == "prompts/get":
                return await self._handle_prompts_get(params, request_id)
            elif method == "notifications/initialized":
                return await self._handle_initialized(request_id)
            else:
                raise MCPError(-32601, f"Method not found: {method}")
                
        except MCPError as e:
            return self._create_error_response(request_id, e.code, e.message, e.data)
        except Exception as e:
            self.logger.error(f"Unexpected error: {str(e)}")
            return self._create_error_response(request_id, -32603, f"Internal error: {str(e)}")
    
    async def _handle_initialize(self, params: Dict, request_id: Any) -> Dict[str, Any]:
        """Handle initialize request"""
        protocol_version = params.get("protocolVersion", "2024-11-05")
        capabilities = params.get("capabilities", {})
        client_info = params.get("clientInfo", {})
        
        self.logger.info(f"Initializing with client: {client_info.get('name', 'unknown')}")
        
        # Server capabilities
        server_capabilities = {
            "tools": {} if self.tools else None,
            "resources": {} if self.resources else None,
            "prompts": {} if self.prompts else None
        }
        
        # Remove None values
        server_capabilities = {k: v for k, v in server_capabilities.items() if v is not None}
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol_version,
                "capabilities": server_capabilities,
                "serverInfo": {
                    "name": self.name,
                    "version": self.version
                }
            }
        }
    
    async def _handle_initialized(self, request_id: Any) -> Dict[str, Any]:
        """Handle initialized notification"""
        self.initialized = True
        self.logger.info("Server initialized successfully")
        
        # Notifications don't return responses
        return None
    
    async def _handle_tools_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle tools/list request"""
        tools_list = [
            {
                "name": tool["name"],
                "description": tool["description"],
                "inputSchema": tool["inputSchema"]
            }
            for tool in self.tools.values()
        ]
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": tools_list
            }
        }
    
    async def _handle_tools_call(self, params: Dict, request_id: Any) -> Dict[str, Any]:
        """Handle tools/call request"""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        self.logger.info(f"🔧 Tool call started: {tool_name}")
        self.logger.debug(f"Tool arguments: {arguments}")
        
        if tool_name not in self.tools:
            raise MCPError(-32602, f"Tool not found: {tool_name}")
        
        try:
            tool = self.tools[tool_name]
            self.logger.debug(f"Executing handler for {tool_name}")
            result = await self._call_handler(tool["handler"], arguments)
            self.logger.info(f"✅ Tool call completed: {tool_name}")
            
            # Format result for MCP
            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            elif isinstance(result, dict) and "content" in result:
                content = result["content"]
            elif isinstance(result, dict):
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            else:
                content = [{"type": "text", "text": str(result)}]
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": content,
                    "isError": False
                }
            }
            
        except Exception as e:
            self.logger.error(f"❌ Tool execution failed for {tool_name}: {str(e)}")
            self.logger.debug(f"Tool failure details", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [{"type": "text", "text": f"Tool execution failed: {str(e)}"}],
                    "isError": True
                }
            }
    
    async def _handle_resources_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle resources/list request"""
        resources_list = [
            {
                "uri": resource["uri"],
                "name": resource["name"],
                "description": resource["description"],
                "mimeType": resource["mimeType"]
            }
            for resource in self.resources.values()
        ]
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "resources": resources_list
            }
        }
    
    async def _handle_resources_read(self, params: Dict, request_id: Any) -> Dict[str, Any]:
        """Handle resources/read request"""
        uri = params.get("uri")
        
        if uri not in self.resources:
            raise MCPError(-32602, f"Resource not found: {uri}")
        
        try:
            resource = self.resources[uri]
            result = await self._call_handler(resource["handler"], {"uri": uri})
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": resource["mimeType"],
                            "text": result if isinstance(result, str) else json.dumps(result)
                        }
                    ]
                }
            }
            
        except Exception as e:
            self.logger.error(f"Resource read failed: {str(e)}")
            raise MCPError(-32603, f"Resource read failed: {str(e)}")
    
    async def _handle_prompts_list(self, request_id: Any) -> Dict[str, Any]:
        """Handle prompts/list request"""
        prompts_list = [
            {
                "name": prompt["name"],
                "description": prompt["description"],
                "arguments": prompt["arguments"]
            }
            for prompt in self.prompts.values()
        ]
        
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "prompts": prompts_list
            }
        }
    
    async def _handle_prompts_get(self, params: Dict, request_id: Any) -> Dict[str, Any]:
        """Handle prompts/get request"""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if prompt_name not in self.prompts:
            raise MCPError(-32602, f"Prompt not found: {prompt_name}")
        
        try:
            prompt = self.prompts[prompt_name]
            result = await self._call_handler(prompt["handler"], arguments)
            
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "description": prompt["description"],
                    "messages": result if isinstance(result, list) else [{"role": "user", "content": {"type": "text", "text": str(result)}}]
                }
            }
            
        except Exception as e:
            self.logger.error(f"Prompt execution failed: {str(e)}")
            raise MCPError(-32603, f"Prompt execution failed: {str(e)}")
    
    async def _call_handler(self, handler: Callable, arguments: Dict) -> Any:
        """Call a handler function, handling both sync and async with timeout protection"""
        import concurrent.futures
        
        if asyncio.iscoroutinefunction(handler):
            # For async handlers, wrap with timeout
            try:
                return await asyncio.wait_for(handler(arguments), timeout=30.0)
            except asyncio.TimeoutError:
                self.logger.error(f"Async handler timed out after 30 seconds")
                raise MCPError(-32603, "Handler execution timed out")
        else:
            # For sync handlers, run in executor with timeout to prevent blocking
            try:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = loop.run_in_executor(executor, handler, arguments)
                    return await asyncio.wait_for(future, timeout=30.0)
            except asyncio.TimeoutError:
                self.logger.error(f"Sync handler timed out after 30 seconds")
                raise MCPError(-32603, "Handler execution timed out")
            except Exception as e:
                self.logger.error(f"Sync handler execution failed: {str(e)}")
                raise
    
    def _create_error_response(self, request_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Create an error response"""
        error = {
            "code": code,
            "message": message
        }
        if data is not None:
            error["data"] = data
            
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error
        }
    
    async def run_stdio(self):
        """Run the server using stdio for MCP communication"""
        self.logger.info(f"Starting MCP server: {self.name} v{self.version}")
        self.logger.info("Server will run continuously to maintain WebSocket connections...")
        
        try:
            while True:
                try:
                    # Read line from stdin with proper async handling
                    line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                    
                    # Check if stdin was closed (EOF)
                    if not line:
                        self.logger.info("Stdin closed, but continuing to serve WebSocket connections...")
                        # Don't break - keep server running for WebSocket connections
                        await asyncio.sleep(1)
                        continue
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    self.logger.debug(f"Received request: {line}")
                    
                    # Parse JSON-RPC request
                    try:
                        request = json.loads(line)
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Invalid JSON: {e}")
                        # Send error response for malformed JSON
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": -32700,
                                "message": "Parse error"
                            }
                        }
                        print(json.dumps(error_response))
                        sys.stdout.flush()
                        continue
                    
                    # Handle request
                    response = await self.handle_request(request)
                    
                    # Send response (if not None for notifications)
                    if response is not None:
                        response_line = json.dumps(response)
                        print(response_line)
                        sys.stdout.flush()
                        self.logger.debug(f"Sent response: {response_line}")
                        
                except EOFError:
                    self.logger.info("EOF received, but continuing to serve WebSocket connections...")
                    await asyncio.sleep(1)
                    continue
                except Exception as e:
                    self.logger.error(f"Request handling error: {str(e)}")
                    continue
                    
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user (Ctrl+C)")
        except Exception as e:
            self.logger.error(f"Server error: {str(e)}")
        finally:
            self.logger.info("MCP server shutdown")

    def run_sync(self):
        """Run the server synchronously"""
        try:
            asyncio.run(self.run_stdio())
        except KeyboardInterrupt:
            pass