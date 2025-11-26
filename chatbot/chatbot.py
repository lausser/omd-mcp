#!/usr/bin/env python3
"""
MCP Chatbot Web Application

A modern web application that enables chatting with LLMs while using MCP (Model Context Protocol)
servers as tools. Supports OpenAI-compatible APIs and dynamic MCP server management.

Features:
- Chat interface with conversation history
- OpenAI-compatible API integration
- Dynamic MCP server management
- Automatic tool calling loop
- Real-time updates
- Modern UI with Tailwind CSS
- Comprehensive logging
"""

import os
import sys
import json
import asyncio
import subprocess
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import httpx
import uvicorn

# =============================================================================
# Logging Configuration
# =============================================================================

# Configure logging to stdout only (for Docker)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("mcp_chatbot")

# Create separate loggers for different components
startup_logger = logging.getLogger("mcp_chatbot.startup")
shutdown_logger = logging.getLogger("mcp_chatbot.shutdown")
prompt_logger = logging.getLogger("mcp_chatbot.prompt")
response_logger = logging.getLogger("mcp_chatbot.response")
tool_logger = logging.getLogger("mcp_chatbot.tool")
mcp_logger = logging.getLogger("mcp_chatbot.mcp")

# =============================================================================
# Data Models
# =============================================================================

class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""
    name: str = Field(..., description="Display name for the MCP server")
    transport: str = Field(default="stdio", description="Transport type: stdio or http")
    url: Optional[str] = Field(default=None, description="URL for HTTP transport")
    command: Optional[str] = Field(default=None, description="Command to run the MCP server (for stdio)")
    args: List[str] = Field(default_factory=list, description="Command line arguments (for stdio)")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    enabled: bool = Field(default=True, description="Whether this server is enabled")

class ChatMessage(BaseModel):
    """A message in the conversation."""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class ChatRequest(BaseModel):
    """Request to send a chat message."""
    message: str = Field(..., description="User message to send")
    conversation_id: Optional[str] = Field(default="default", description="Conversation ID")

class MCPAddRequest(BaseModel):
    """Request to add an MCP server."""
    config: MCPServerConfig

class ConfigureRequest(BaseModel):
    """Request to configure OpenAI API."""
    api_key: str = Field(..., description="OpenAI API key")
    base_url: str = Field(default="https://api.openai.com/v1", description="API base URL")
    model: str = Field(default="gpt-4", description="Model to use")

# =============================================================================
# MCP Client Implementation
# =============================================================================

@dataclass
class MCPTool:
    """Represents a tool from an MCP server."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str

@dataclass
class MCPServer:
    """Represents a connected MCP server."""
    name: str
    config: MCPServerConfig
    process: Optional[subprocess.Popen] = None
    tools: List[MCPTool] = field(default_factory=list)
    connected: bool = False
    session_id: Optional[str] = None  # For HTTP transport session management
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "config": self.config.dict(),
            "connected": self.connected,
            "tools": [{"name": t.name, "description": t.description, "server": t.server_name} 
                     for t in self.tools]
        }

class MCPClient:
    """Client for managing MCP server connections."""

    def __init__(self):
        self.servers: Dict[str, MCPServer] = {}
        self.request_id = 0
        self.http_client = httpx.AsyncClient(timeout=30.0)
        mcp_logger.info("MCPClient initialized")
    
    async def add_server(self, config: MCPServerConfig) -> MCPServer:
        """Add and connect to an MCP server."""
        mcp_logger.info(f"Adding MCP server: {config.name} ({config.transport} transport)")

        if config.name in self.servers:
            mcp_logger.error(f"Server {config.name} already exists")
            raise ValueError(f"Server {config.name} already exists")

        server = MCPServer(name=config.name, config=config)

        try:
            if config.transport == "stdio":
                # Start the MCP server process for stdio transport
                env = os.environ.copy()
                env.update(config.env)

                mcp_logger.info(f"Starting MCP server process: {config.command} {' '.join(config.args)}")

                server.process = subprocess.Popen(
                    [config.command] + config.args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=False
                )

                mcp_logger.info(f"MCP server process started with PID: {server.process.pid}")
            elif config.transport == "http":
                # HTTP transport - no process to start
                mcp_logger.info(f"Using HTTP transport at: {config.url}")
            
            # Send initialize request
            init_response = await self._send_request(server, "initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {"listChanged": False},
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "mcp-chatbot",
                    "version": "1.0.0"
                }
            })
            
            mcp_logger.info(f"MCP server {config.name} initialized: {init_response.get('result', {}).get('serverInfo', {})}")

            # Send initialized notification (required by MCP protocol)
            initialized_notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            if server.config.transport == "stdio":
                notif_bytes = (json.dumps(initialized_notif) + "\n").encode('utf-8')
                server.process.stdin.write(notif_bytes)
                server.process.stdin.flush()
                mcp_logger.info("Sent initialized notification")

            # Get available tools
            tools_response = await self._send_request(server, "tools/list", {})
            mcp_logger.info(f"tools/list response: {tools_response}")

            if tools_response and "tools" in tools_response.get("result", {}):
                for tool_data in tools_response["result"]["tools"]:
                    tool = MCPTool(
                        name=tool_data["name"],
                        description=tool_data.get("description", ""),
                        input_schema=tool_data.get("inputSchema", {}),
                        server_name=config.name
                    )
                    server.tools.append(tool)
                    mcp_logger.info(f"Discovered tool: {tool.name} from {config.name}")
            
            server.connected = True
            self.servers[config.name] = server
            
            mcp_logger.info(f"✓ Connected to MCP server: {config.name} ({len(server.tools)} tools)")
            return server
            
        except Exception as e:
            mcp_logger.error(f"Failed to connect to MCP server {config.name}: {str(e)}", exc_info=True)
            if server.process:
                server.process.terminate()
            raise Exception(f"Failed to connect to MCP server {config.name}: {str(e)}")
    
    async def _send_request(self, server: MCPServer, method: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Send a JSON-RPC request to an MCP server."""
        self.request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method
        }
        # Always add params (even if empty dict)
        if params is not None:
            request["params"] = params

        mcp_logger.info(f"Sending request to {server.name}: {json.dumps(request)}")

        if server.config.transport == "stdio":
            # Stdio transport
            request_bytes = (json.dumps(request) + "\n").encode('utf-8')
            server.process.stdin.write(request_bytes)
            server.process.stdin.flush()

            # Read response
            response_line = server.process.stdout.readline()
            if not response_line:
                mcp_logger.error(f"No response from MCP server {server.name}")
                raise Exception("No response from MCP server")

            response = json.loads(response_line.decode('utf-8'))
        elif server.config.transport == "http":
            # HTTP transport (streamable HTTP with SSE response)
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }

            # Include session ID if we have one
            if server.session_id:
                headers["mcp-session-id"] = server.session_id

            http_response = await self.http_client.post(
                f"{server.config.url}/mcp",
                json=request,
                headers=headers
            )
            http_response.raise_for_status()

            # Capture session ID from response header if present
            if "mcp-session-id" in http_response.headers:
                server.session_id = http_response.headers["mcp-session-id"]
                mcp_logger.debug(f"Captured session ID for {server.name}: {server.session_id}")

            # Parse SSE response format
            response_text = http_response.text
            for line in response_text.split('\n'):
                if line.startswith('data: '):
                    response = json.loads(line[6:])  # Skip 'data: ' prefix
                    break
        else:
            raise ValueError(f"Unsupported transport: {server.config.transport}")

        mcp_logger.debug(f"Received response from {server.name}: {response.get('result', {}).get('type', 'unknown')}")

        return response
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Call an MCP tool and return the result."""
        tool_logger.info(f"Calling tool: {tool_name} with arguments: {json.dumps(arguments)}")
        
        # Find which server has this tool
        server = None
        tool = None
        
        for srv in self.servers.values():
            for t in srv.tools:
                if t.name == tool_name:
                    server = srv
                    tool = t
                    break
            if server:
                break
        
        if not server or not tool:
            tool_logger.error(f"Tool {tool_name} not found")
            return f"Error: Tool {tool_name} not found"
        
        try:
            response = await self._send_request(server, "tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            
            if "result" in response:
                result = response["result"]
                if "content" in result:
                    # Extract text from content array
                    content_texts = []
                    for content_item in result["content"]:
                        if content_item.get("type") == "text":
                            content_texts.append(content_item.get("text", ""))
                    result_text = "\n".join(content_texts)
                    tool_logger.info(f"Tool {tool_name} completed successfully (length: {len(result_text)})")
                    return result_text
                result_text = str(result)
                tool_logger.info(f"Tool {tool_name} returned: {result_text[:100]}...")
                return result_text
            elif "error" in response:
                error_msg = response['error'].get('message', 'Unknown error')
                tool_logger.error(f"Tool {tool_name} failed: {error_msg}")
                return f"Error: {error_msg}"
            else:
                tool_logger.warning(f"Tool {tool_name} returned no result")
                return "No result returned"
                
        except Exception as e:
            tool_logger.error(f"Error calling tool {tool_name}: {str(e)}", exc_info=True)
            return f"Error calling tool {tool_name}: {str(e)}"
    
    def get_all_tools(self) -> List[MCPTool]:
        """Get all tools from all connected servers."""
        tools = []
        for server in self.servers.values():
            if server.connected and server.config.enabled:
                tools.extend(server.tools)
        return tools
    
    def remove_server(self, name: str):
        """Remove and disconnect from an MCP server."""
        mcp_logger.info(f"Removing MCP server: {name}")
        if name in self.servers:
            server = self.servers[name]
            if server.process:
                server.process.terminate()
                server.process.wait()
                mcp_logger.info(f"MCP server {name} process terminated")
            del self.servers[name]
    
    def __del__(self):
        """Clean up all server processes."""
        mcp_logger.info("Cleaning up MCP client")
        for server in self.servers.values():
            if server.process:
                server.process.terminate()

# =============================================================================
# OpenAI Client
# =============================================================================

class OpenAIClient:
    """Client for OpenAI-compatible API."""
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4"):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.model = model
        logger.info(f"OpenAI client configured: base_url={base_url}, model={model}")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        max_tokens: int = 2000
    ) -> Dict[str, Any]:
        """Send a chat completion request."""
        logger.debug(f"Sending chat completion request: {len(messages)} messages, {len(tools) if tools else 0} tools")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            result = response.json()
            logger.debug(f"Chat completion response received: finish_reason={result['choices'][0].get('finish_reason')}")
            return result

# =============================================================================
# Conversation Manager
# =============================================================================

class ConversationManager:
    """Manages conversations and integrates MCP tools with LLM."""
    
    def __init__(self, mcp_client: MCPClient, openai_client: OpenAIClient):
        self.mcp_client = mcp_client
        self.openai_client = openai_client
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.max_iterations = 10  # Prevent infinite loops
        logger.info("ConversationManager initialized")
    
    def _mcp_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI tool format."""
        tools = []
        for mcp_tool in self.mcp_client.get_all_tools():
            tool = {
                "type": "function",
                "function": {
                    "name": mcp_tool.name,
                    "description": mcp_tool.description,
                    "parameters": mcp_tool.input_schema
                }
            }
            tools.append(tool)
        return tools
    
    async def send_message(self, conversation_id: str, user_message: str) -> List[ChatMessage]:
        """Send a message and handle the complete tool calling loop."""
        prompt_logger.info(f"[{conversation_id}] Received prompt: {user_message[:100]}{'...' if len(user_message) > 100 else ''}")
        
        # Initialize conversation if needed
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = []

            # Add system prompt to instruct the bot
            self.conversations[conversation_id].append({
                "role": "system",
                "content": """
# Nagios Downtime Management Prompt

You are an expert system administrator specializing in **Nagios monitoring**, with deep knowledge of hosts, services, hostgroups, and downtime management.

Your primary purpose is to assist technically skilled system administrators in managing **scheduled downtimes** in Nagios. You translate natural language requests into clear, accurate actions.

---

## **Role & Expertise**

You have extensive experience with:

* Scheduling downtimes (hosts, services, hostgroups).
* Deleting existing downtimes.
* Querying and filtering downtimes.
* Interpreting natural language requests from domain experts.
* Understanding parameters of a downtime:

  * **target** (host/service/hostgroup)
  * **start and end time**
  * **duration**
  * **fixed vs. flexible**
  * **comment/reason**

You **do not execute commands**, but you understand their semantics perfectly.

---

## **Primary Objectives**

### **1. Schedule Downtimes**

Interpret natural language to determine:

* Target (host, service, hostgroup)
* Start time / end time / duration
* Fixed or flexible downtime (if specified)
* Comment/reason for the downtime

Then respond concisely with:

> "Downtime scheduled successfully for …"

### **2. Delete Downtimes**

Support deletion using:

* Downtime ID
* or specific filters (target, time, comment, etc.)

Confirm with:

> "Downtime ID XYZ removed successfully."

### **3. Retrieve Downtime Information**

Return clear bullet-point lists containing:

* Downtime ID
* Target (host/service/hostgroup)
* Start time
* End time
* Duration
* Comment

You may filter by user request (host, service, timeframe, etc.).

### **4. Ask for Clarification**

When required details are missing or ambiguous, ask specific questions:

> "I understand you want to schedule a downtime. Could you specify the target host or service?"

---

## **Context & Constraints**

* Always operate on current host and service objects. When working with lists of hostnames/services, always refresh the list.
* Users are skilled admins; be concise and professional.
* Interpret relative time references (e.g. "tomorrow") using the current date/time.
* Focus **exclusively** on downtime management.
* Do **not** give general Nagios installation/configuration advice.
* Do **not** generate code or scripts.
* Do **not** give personal opinions.

If a user asks something outside your scope:

> "I am focused on Nagios downtime management and cannot assist with that."

---

## **Desired Output Format**

* Always polite and concise.
* Confirm successful actions.
* Use bullet points for multi-line results.
* When uncertain, restate what you understood and ask for missing details.

**Example list output:**

```
Currently active downtimes:
• ID: 1234, Host: example.com, Start: 2025-11-25 08:00, End: 2025-11-25 10:00, Comment: Emergency maintenance
• ID: 5678, Service: CPU Usage on server2.net, Start: 2025-11-26 14:00, End: 2025-11-26 16:00, Comment: Scheduled upgrade
```

---

## **Communication Style**

* Senior administrator tone: precise, direct, professional.
* Avoid unnecessary verbosity.
* Use technical terms appropriately.
* Be proactive and helpful.

---

## **Example Interactions**

**User:** “Put the database server in downtime for two hours starting now for patching.”
**AI:** “Downtime scheduled successfully for host ‘database server’ for 2 hours starting now with comment ‘patching’.”

---

**User:** “List all downtimes.”
**AI:**

```
Currently active downtimes:
• ID: 123, Host: web1, Start: …
• ID: 456, Service: CPU Load on db2, Start: …
```

---

**User:** “Remove downtime ID 9876.”
**AI:** “Downtime ID 9876 removed successfully.”

---

**User:** “Schedule downtime tomorrow.”
**AI:** “I understand you want to schedule a downtime tomorrow. Could you specify the host, service, or hostgroup, along with the duration and reason?”

---

# **End of System Prompt**
                """
            })

            logger.info(f"[{conversation_id}] New conversation started with system prompt")

        conversation = self.conversations[conversation_id]

        # Add user message
        conversation.append({
            "role": "user",
            "content": user_message
        })
        
        response_messages = []
        iteration = 0
        
        # Tool calling loop
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"[{conversation_id}] Tool calling loop iteration {iteration}/{self.max_iterations}")
            
            # Get available tools
            tools = self._mcp_tools_to_openai_format()
            logger.debug(f"[{conversation_id}] Available tools: {len(tools)}")
            
            # Call LLM
            try:
                response = await self.openai_client.chat_completion(
                    messages=conversation,
                    tools=tools if tools else None
                )
            except Exception as e:
                error_msg = f"Error calling LLM: {str(e)}"
                response_logger.error(f"[{conversation_id}] {error_msg}", exc_info=True)
                response_messages.append(ChatMessage(
                    role="assistant",
                    content=error_msg
                ))
                break
            
            # Extract assistant message
            choice = response["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason")
            
            logger.debug(f"[{conversation_id}] LLM response: finish_reason={finish_reason}, has_tool_calls={bool(message.get('tool_calls'))}")
            
            # Add assistant message to conversation
            assistant_msg = {
                "role": "assistant",
                "content": message.get("content") or ""
            }
            
            # Check for tool calls
            tool_calls = message.get("tool_calls")
            
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
                conversation.append(assistant_msg)
                
                tool_logger.info(f"[{conversation_id}] LLM requesting {len(tool_calls)} tool call(s)")
                
                # Display assistant message with tool calls
                tool_call_summary = []
                for tc in tool_calls:
                    func = tc["function"]
                    tool_call_summary.append(f"Calling {func['name']}...")
                    tool_logger.info(f"[{conversation_id}] Tool call: {func['name']} with args: {func['arguments'][:100]}...")
                
                response_messages.append(ChatMessage(
                    role="assistant",
                    content=assistant_msg.get("content") or "Calling tools...",
                    tool_calls=tool_calls
                ))
                
                # Execute each tool call
                for tool_call in tool_calls:
                    function = tool_call["function"]
                    tool_name = function["name"]
                    
                    try:
                        arguments = json.loads(function["arguments"])
                    except json.JSONDecodeError:
                        arguments = {}
                        tool_logger.warning(f"[{conversation_id}] Failed to parse arguments for {tool_name}")
                    
                    # Call the MCP tool
                    tool_result = await self.mcp_client.call_tool(tool_name, arguments)
                    
                    tool_logger.info(f"[{conversation_id}] Tool {tool_name} completed (result length: {len(tool_result)})")
                    
                    # Add tool result to conversation
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": tool_name,
                        "content": tool_result
                    }
                    conversation.append(tool_message)
                    
                    # Add to response messages
                    response_messages.append(ChatMessage(
                        role="tool",
                        content=f"**{tool_name} result:**\n{tool_result}",
                        tool_call_id=tool_call["id"],
                        name=tool_name
                    ))
                
                # Continue loop to let LLM see results and potentially call more tools
                continue
            
            else:
                # No tool calls, add final response
                conversation.append(assistant_msg)
                final_response = message.get("content") or ""
                response_logger.info(f"[{conversation_id}] Sending final response: {final_response[:100]}{'...' if len(final_response) > 100 else ''}")
                
                response_messages.append(ChatMessage(
                    role="assistant",
                    content=final_response
                ))
                
                # Check if we should stop
                if finish_reason in ["stop", "end_turn"]:
                    logger.info(f"[{conversation_id}] Conversation completed normally after {iteration} iteration(s)")
                    break
        
        if iteration >= self.max_iterations:
            logger.warning(f"[{conversation_id}] Maximum iterations reached")
            response_messages.append(ChatMessage(
                role="system",
                content="⚠️ Maximum tool calling iterations reached. Stopping to prevent infinite loop."
            ))
        
        return response_messages
    
    def get_conversation(self, conversation_id: str) -> List[ChatMessage]:
        """Get all messages in a conversation."""
        if conversation_id not in self.conversations:
            return []
        
        messages = []
        for msg in self.conversations[conversation_id]:
            messages.append(ChatMessage(
                role=msg["role"],
                content=msg.get("content", ""),
                tool_calls=msg.get("tool_calls"),
                tool_call_id=msg.get("tool_call_id"),
                name=msg.get("name")
            ))
        return messages
    
    def clear_conversation(self, conversation_id: str):
        """Clear a conversation."""
        if conversation_id in self.conversations:
            logger.info(f"[{conversation_id}] Conversation cleared")
            self.conversations[conversation_id] = []

# =============================================================================
# FastAPI Application with Lifespan
# =============================================================================

from contextlib import asynccontextmanager

# Global instances
mcp_client = MCPClient()
openai_client = None
conversation_manager = None

# WebSocket connections
active_connections: List[WebSocket] = []

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown."""
    global openai_client, conversation_manager

    # Startup
    startup_logger.info("=" * 70)
    startup_logger.info("MCP Chatbot Web Application Starting")
    startup_logger.info("=" * 70)
    startup_logger.info(f"Python version: {sys.version}")
    startup_logger.info(f"FastAPI application initialized")
    startup_logger.info(f"Log level: {logging.getLevelName(logger.level)}")

    # Load MCP servers from config file
    config_file = "chatbot.json"
    if os.path.exists(config_file):
        try:
            startup_logger.info(f"Loading MCP server configuration from {config_file}")
            with open(config_file, 'r') as f:
                config_data = json.load(f)

            mcp_servers = config_data.get("mcpServers", {})

            # Wait a bit for HTTP MCP servers to start up (in containerized environments)
            if any(s.get("transport") == "http" for s in mcp_servers.values()):
                startup_logger.info("Waiting 3 seconds for HTTP MCP servers to start...")
                await asyncio.sleep(3)
            for server_name, server_config in mcp_servers.items():
                try:
                    mcp_config = MCPServerConfig(
                        name=server_name,
                        transport=server_config.get("transport", "stdio"),
                        url=server_config.get("url"),
                        command=server_config.get("command"),
                        args=server_config.get("args", []),
                        env=server_config.get("env", {}),
                        enabled=server_config.get("enabled", True)
                    )
                    await mcp_client.add_server(mcp_config)
                    startup_logger.info(f"✓ Connected to MCP server: {server_name}")
                except Exception as e:
                    startup_logger.error(f"Failed to connect to MCP server {server_name}: {str(e)}")
        except Exception as e:
            startup_logger.error(f"Failed to load MCP config from {config_file}: {str(e)}")
    else:
        startup_logger.info(f"No MCP config file found at {config_file}")

    # Auto-configure from environment variables if available
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4")

    if api_key:
        try:
            startup_logger.info("Auto-configuring LLM API from environment variables")
            startup_logger.info(f"  Base URL: {base_url}")
            startup_logger.info(f"  Model: {model}")
            openai_client = OpenAIClient(api_key=api_key, base_url=base_url, model=model)
            conversation_manager = ConversationManager(mcp_client, openai_client)
            startup_logger.info("✓ LLM API configured successfully")
        except Exception as e:
            startup_logger.error(f"Failed to auto-configure LLM API: {str(e)}")
            startup_logger.info("Will require manual configuration via web UI")
    else:
        startup_logger.info("OPENAI_API_KEY not set - manual configuration required via web UI")

    startup_logger.info("Ready to accept connections")
    startup_logger.info("=" * 70)

    yield

    # Shutdown
    shutdown_logger.info("=" * 70)
    shutdown_logger.info("MCP Chatbot Web Application Shutting Down")
    shutdown_logger.info("=" * 70)

    # Cleanup MCP servers
    if mcp_client:
        shutdown_logger.info(f"Cleaning up {len(mcp_client.servers)} MCP server(s)")
        for server_name in list(mcp_client.servers.keys()):
            mcp_client.remove_server(server_name)

    shutdown_logger.info("Shutdown complete")
    shutdown_logger.info("=" * 70)

app = FastAPI(title="MCP Chatbot", version="1.0.0", lifespan=lifespan)

# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def get_root():
    """Serve the main HTML page."""
    logger.info("Serving main page")
    return HTML_CONTENT

@app.post("/api/configure")
async def configure_openai(request: ConfigureRequest):
    """Configure OpenAI API settings."""
    global openai_client, conversation_manager
    
    logger.info(f"Configuring OpenAI API: base_url={request.base_url}, model={request.model}")
    
    try:
        openai_client = OpenAIClient(api_key=request.api_key, base_url=request.base_url, model=request.model)
        conversation_manager = ConversationManager(mcp_client, openai_client)
        logger.info("OpenAI API configured successfully")
        return {"status": "success", "message": "OpenAI API configured"}
    except Exception as e:
        logger.error(f"Failed to configure OpenAI API: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/mcp/add")
async def add_mcp_server(request: MCPAddRequest):
    """Add a new MCP server."""
    logger.info(f"API request to add MCP server: {request.config.name}")
    try:
        server = await mcp_client.add_server(request.config)
        logger.info(f"MCP server {request.config.name} added successfully with {len(server.tools)} tools")
        return {
            "status": "success",
            "server": server.to_dict()
        }
    except Exception as e:
        logger.error(f"Failed to add MCP server: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/mcp/servers")
async def list_mcp_servers():
    """List all MCP servers."""
    servers = [server.to_dict() for server in mcp_client.servers.values()]
    logger.debug(f"Listing {len(servers)} MCP server(s)")
    return {"servers": servers}

@app.delete("/api/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """Remove an MCP server."""
    logger.info(f"API request to remove MCP server: {name}")
    try:
        mcp_client.remove_server(name)
        logger.info(f"MCP server {name} removed successfully")
        return {"status": "success", "message": f"Server {name} removed"}
    except Exception as e:
        logger.error(f"Failed to remove MCP server {name}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/chat")
async def send_chat_message(request: ChatRequest):
    """Send a chat message."""
    if not conversation_manager:
        logger.warning("Chat request received but OpenAI API not configured")
        raise HTTPException(status_code=400, detail="OpenAI API not configured")
    
    logger.info(f"Chat message received: conversation_id={request.conversation_id}")
    
    try:
        responses = await conversation_manager.send_message(
            request.conversation_id,
            request.message
        )
        logger.info(f"Chat response sent: {len(responses)} message(s)")
        return {
            "status": "success",
            "messages": [msg.dict() for msg in responses]
        }
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history."""
    if not conversation_manager:
        return {"messages": []}
    
    messages = conversation_manager.get_conversation(conversation_id)
    logger.debug(f"Retrieved {len(messages)} messages for conversation {conversation_id}")
    return {"messages": [msg.dict() for msg in messages]}

@app.delete("/api/chat/{conversation_id}")
async def clear_conversation(conversation_id: str):
    """Clear conversation history."""
    if conversation_manager:
        conversation_manager.clear_conversation(conversation_id)
        logger.info(f"Conversation {conversation_id} cleared")
    return {"status": "success"}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "mcp_servers": len(mcp_client.servers),
        "api_configured": conversation_manager is not None
    }

@app.get("/api/status")
async def api_status():
    """Get API configuration status."""
    return {
        "configured": conversation_manager is not None,
        "model": openai_client.model if openai_client else None,
        "base_url": openai_client.base_url if openai_client else None
    }

@app.get("/api/mcp/config")
async def get_mcp_config():
    """Get MCP configuration settings."""
    config_file = "chatbot.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            return {
                "uiConfigMcps": config_data.get("uiConfigMcps", False),
                "serversConfigured": list(config_data.get("mcpServers", {}).keys())
            }
        except Exception as e:
            logger.error(f"Failed to load MCP config: {str(e)}")
    return {"uiConfigMcps": True, "serversConfigured": []}

# =============================================================================
# HTML Content (same as before, not repeated for brevity)
# =============================================================================

HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Chatbot</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .message {
            animation: slideIn 0.3s ease-out;
        }
        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .tool-call {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div class="container mx-auto p-4 max-w-7xl">
        <!-- Header -->
        <div class="bg-white rounded-lg shadow-lg p-6 mb-4">
            <h1 class="text-3xl font-bold text-gray-800 mb-2">🤖 MCP Chatbot</h1>
            <p class="text-gray-600">Chat with AI using Model Context Protocol tools</p>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <!-- Main Chat Area (2/3 width) -->
            <div class="lg:col-span-2 space-y-4">
                <!-- Configuration Status (shown when configured) -->
                <div id="configStatus" class="bg-white rounded-lg shadow-lg p-6" style="display: none;">
                    <h2 class="text-xl font-semibold mb-4">⚙️ Configuration</h2>
                    <div class="bg-green-50 border border-green-200 rounded-md p-4">
                        <div class="flex items-center mb-2">
                            <span class="text-green-600 font-semibold">✓ API Configured</span>
                        </div>
                        <div class="text-sm text-gray-700 space-y-1">
                            <div><span class="font-medium">Base URL:</span> <span id="statusBaseUrl"></span></div>
                            <div><span class="font-medium">Model:</span> <span id="statusModel"></span></div>
                        </div>
                        <button onclick="showConfigPanel()"
                                class="mt-3 text-sm text-blue-600 hover:text-blue-800">
                            Reconfigure
                        </button>
                    </div>
                </div>

                <!-- Configuration Panel (shown when not configured) -->
                <div id="configPanel" class="bg-white rounded-lg shadow-lg p-6">
                    <h2 class="text-xl font-semibold mb-4">⚙️ Configuration</h2>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                            <input type="password" id="apiKey"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
                                   placeholder="sk-...">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Base URL</label>
                            <input type="text" id="baseUrl" value="https://api.openai.com/v1"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Model</label>
                            <input type="text" id="model" value="gpt-4"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500">
                        </div>
                        <button onclick="configureAPI()"
                                class="w-full bg-blue-500 text-white py-2 rounded-md hover:bg-blue-600 transition">
                            Configure API
                        </button>
                    </div>
                </div>

                <!-- Chat Area -->
                <div class="bg-white rounded-lg shadow-lg flex flex-col" style="height: 600px;">
                    <!-- Messages -->
                    <div id="messages" class="flex-1 overflow-y-auto p-6 space-y-4">
                        <div class="text-center text-gray-500 py-10">
                            <p class="text-lg">👋 Welcome! Configure the API and add MCP servers to get started.</p>
                        </div>
                    </div>

                    <!-- Input Area -->
                    <div class="border-t p-4">
                        <div class="flex space-x-2">
                            <input type="text" id="messageInput" 
                                   placeholder="Type your message..."
                                   class="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
                                   onkeypress="if(event.key === 'Enter') sendMessage()">
                            <button onclick="sendMessage()" 
                                    class="bg-green-500 text-white px-6 py-2 rounded-md hover:bg-green-600 transition">
                                Send
                            </button>
                            <button onclick="clearChat()" 
                                    class="bg-red-500 text-white px-6 py-2 rounded-md hover:bg-red-600 transition">
                                Clear
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- MCP Servers Panel (1/3 width) -->
            <div class="space-y-4">
                <!-- Add Thruk MCP Server (hidden by default, shown if uiConfigMcps is true) -->
                <div id="mcpConfigForm" class="bg-white rounded-lg shadow-lg p-6" style="display: none;">
                    <h2 class="text-xl font-semibold mb-4">🔧 Add Thruk MCP</h2>
                    <div class="space-y-3">
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Server Name</label>
                            <input type="text" id="mcpName" value="Thruk"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Command</label>
                            <input type="text" id="mcpCommand" value="python"
                                   class="w-full px-3 py-2 border border-gray-300 rounded-md">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Args (one per line)</label>
                            <textarea id="mcpArgs" rows="2"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-md">/path/to/thruk_mcp.py</textarea>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Environment Variables (JSON)</label>
                            <textarea id="mcpEnv" rows="4"
                                      class="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-sm">{
  "THRUK_API_KEY": "your-key",
  "THRUK_BASE_URL": "https://your-server/thruk"
}</textarea>
                        </div>
                        <button onclick="addMCPServer()" 
                                class="w-full bg-purple-500 text-white py-2 rounded-md hover:bg-purple-600 transition">
                            Add MCP Server
                        </button>
                    </div>
                </div>

                <!-- MCP Servers List -->
                <div class="bg-white rounded-lg shadow-lg p-6">
                    <h2 class="text-xl font-semibold mb-4">📡 MCP Servers</h2>
                    <div id="mcpServersList" class="space-y-2">
                        <p class="text-gray-500 text-sm">No servers connected</p>
                    </div>
                </div>

                <!-- Available Tools -->
                <div class="bg-white rounded-lg shadow-lg p-6">
                    <h2 class="text-xl font-semibold mb-4">🛠️ Available Tools</h2>
                    <div id="toolsList" class="space-y-1">
                        <p class="text-gray-500 text-sm">No tools available</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let conversationId = 'default';
        let isConfigured = false;

        // Check API configuration status
        async function checkAPIStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();

                if (data.configured) {
                    isConfigured = true;
                    document.getElementById('configStatus').style.display = 'block';
                    document.getElementById('configPanel').style.display = 'none';
                    document.getElementById('statusBaseUrl').textContent = data.base_url || 'N/A';
                    document.getElementById('statusModel').textContent = data.model || 'N/A';
                } else {
                    document.getElementById('configStatus').style.display = 'none';
                    document.getElementById('configPanel').style.display = 'block';
                }
            } catch (e) {
                console.error('Error checking API status:', e);
            }
        }

        // Show configuration panel for reconfiguration
        function showConfigPanel() {
            document.getElementById('configStatus').style.display = 'none';
            document.getElementById('configPanel').style.display = 'block';
        }

        // Configure API
        async function configureAPI() {
            const apiKey = document.getElementById('apiKey').value;
            const baseUrl = document.getElementById('baseUrl').value;
            const model = document.getElementById('model').value;

            if (!apiKey) {
                alert('Please enter an API key');
                return;
            }

            try {
                const response = await fetch('/api/configure', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({api_key: apiKey, base_url: baseUrl, model: model})
                });

                if (response.ok) {
                    isConfigured = true;
                    addSystemMessage('✅ API configured successfully!');
                    await checkAPIStatus(); // Update UI to show configured status
                } else {
                    const error = await response.json();
                    alert('Configuration failed: ' + error.detail);
                }
            } catch (e) {
                alert('Configuration error: ' + e.message);
            }
        }

        // Add MCP Server
        async function addMCPServer() {
            const name = document.getElementById('mcpName').value;
            const command = document.getElementById('mcpCommand').value;
            const argsText = document.getElementById('mcpArgs').value;
            const envText = document.getElementById('mcpEnv').value;

            const args = argsText.split('\n').filter(a => a.trim());
            let env = {};
            
            try {
                env = JSON.parse(envText);
            } catch (e) {
                alert('Invalid JSON in environment variables');
                return;
            }

            const config = {
                name: name,
                command: command,
                args: args,
                env: env,
                enabled: true
            };

            try {
                const response = await fetch('/api/mcp/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({config: config})
                });

                if (response.ok) {
                    addSystemMessage(`✅ Connected to MCP server: ${name}`);
                    await refreshMCPServers();
                } else {
                    const error = await response.json();
                    alert('Failed to add server: ' + error.detail);
                }
            } catch (e) {
                alert('Error adding server: ' + e.message);
            }
        }

        // Refresh MCP servers list
        async function refreshMCPServers() {
            try {
                const response = await fetch('/api/mcp/servers');
                const data = await response.json();
                
                const serversList = document.getElementById('mcpServersList');
                const toolsList = document.getElementById('toolsList');
                
                if (data.servers.length === 0) {
                    serversList.innerHTML = '<p class="text-gray-500 text-sm">No servers connected</p>';
                    toolsList.innerHTML = '<p class="text-gray-500 text-sm">No tools available</p>';
                    return;
                }

                // Update servers list
                serversList.innerHTML = data.servers.map(server => `
                    <div class="p-3 bg-gray-50 rounded border border-gray-200">
                        <div class="flex justify-between items-center">
                            <div>
                                <span class="font-semibold">${server.name}</span>
                                <span class="ml-2 text-xs ${server.connected ? 'text-green-600' : 'text-red-600'}">
                                    ${server.connected ? '● Connected' : '● Disconnected'}
                                </span>
                            </div>
                            <button onclick="removeMCPServer('${server.name}')" 
                                    class="text-red-500 hover:text-red-700 text-sm">
                                Remove
                            </button>
                        </div>
                        <div class="text-xs text-gray-600 mt-1">
                            ${server.tools.length} tools available
                        </div>
                    </div>
                `).join('');

                // Update tools list
                const allTools = data.servers.flatMap(s => s.tools);
                if (allTools.length > 0) {
                    toolsList.innerHTML = allTools.map(tool => `
                        <div class="text-sm p-2 bg-blue-50 rounded border border-blue-200">
                            <div class="font-semibold text-blue-900">${tool.name}</div>
                            <div class="text-xs text-gray-600">${tool.description}</div>
                        </div>
                    `).join('');
                } else {
                    toolsList.innerHTML = '<p class="text-gray-500 text-sm">No tools available</p>';
                }
            } catch (e) {
                console.error('Error refreshing servers:', e);
            }
        }

        // Remove MCP server
        async function removeMCPServer(name) {
            if (!confirm(`Remove server ${name}?`)) return;

            try {
                await fetch(`/api/mcp/servers/${name}`, {method: 'DELETE'});
                addSystemMessage(`🗑️ Removed MCP server: ${name}`);
                await refreshMCPServers();
            } catch (e) {
                alert('Error removing server: ' + e.message);
            }
        }

        // Send message
        async function sendMessage() {
            if (!isConfigured) {
                alert('Please configure the API first');
                return;
            }

            const input = document.getElementById('messageInput');
            const message = input.value.trim();
            
            if (!message) return;

            // Add user message to UI
            addMessage('user', message);
            input.value = '';

            // Disable input while processing
            input.disabled = true;

            try {
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        conversation_id: conversationId
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    
                    // Add all response messages
                    for (const msg of data.messages) {
                        if (msg.role === 'assistant') {
                            addMessage('assistant', msg.content, msg.tool_calls);
                        } else if (msg.role === 'tool') {
                            addMessage('tool', msg.content, null, msg.name);
                        } else if (msg.role === 'system') {
                            addSystemMessage(msg.content);
                        }
                    }
                } else {
                    const error = await response.json();
                    addSystemMessage('❌ Error: ' + error.detail);
                }
            } catch (e) {
                addSystemMessage('❌ Error: ' + e.message);
            } finally {
                input.disabled = false;
                input.focus();
            }
        }

        // Add message to chat
        function addMessage(role, content, toolCalls = null, toolName = null) {
            const messagesDiv = document.getElementById('messages');
            
            // Remove welcome message if present
            if (messagesDiv.querySelector('.text-center')) {
                messagesDiv.innerHTML = '';
            }

            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';

            if (role === 'user') {
                messageDiv.innerHTML = `
                    <div class="flex justify-end">
                        <div class="bg-blue-500 text-white rounded-lg px-4 py-2 max-w-2xl">
                            <div class="font-semibold mb-1">You</div>
                            <div class="whitespace-pre-wrap">${escapeHtml(content)}</div>
                        </div>
                    </div>
                `;
            } else if (role === 'assistant') {
                let toolCallsHtml = '';
                if (toolCalls && toolCalls.length > 0) {
                    toolCallsHtml = '<div class="mt-2 space-y-1">';
                    for (const tc of toolCalls) {
                        const func = tc.function;
                        toolCallsHtml += `
                            <div class="text-xs tool-call text-white px-2 py-1 rounded">
                                🔧 Calling: ${func.name}
                            </div>
                        `;
                    }
                    toolCallsHtml += '</div>';
                }

                messageDiv.innerHTML = `
                    <div class="flex justify-start">
                        <div class="bg-gray-200 text-gray-800 rounded-lg px-4 py-2 max-w-2xl">
                            <div class="font-semibold mb-1">🤖 Assistant</div>
                            <div class="whitespace-pre-wrap">${escapeHtml(content)}</div>
                            ${toolCallsHtml}
                        </div>
                    </div>
                `;
            } else if (role === 'tool') {
                messageDiv.innerHTML = `
                    <div class="flex justify-start">
                        <div class="bg-purple-100 text-purple-900 rounded-lg px-4 py-2 max-w-2xl text-sm">
                            <div class="font-semibold mb-1">🛠️ Tool: ${escapeHtml(toolName)}</div>
                            <div class="whitespace-pre-wrap font-mono text-xs">${escapeHtml(content)}</div>
                        </div>
                    </div>
                `;
            }

            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function addSystemMessage(content) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';
            messageDiv.innerHTML = `
                <div class="text-center">
                    <div class="inline-block bg-yellow-100 text-yellow-800 rounded-lg px-4 py-2 text-sm">
                        ${escapeHtml(content)}
                    </div>
                </div>
            `;
            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function clearChat() {
            if (!confirm('Clear conversation history?')) return;
            
            fetch(`/api/chat/${conversationId}`, {method: 'DELETE'})
                .then(() => {
                    document.getElementById('messages').innerHTML = `
                        <div class="text-center text-gray-500 py-10">
                            <p class="text-lg">💬 Conversation cleared. Start a new chat!</p>
                        </div>
                    `;
                });
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Check MCP configuration settings
        async function checkMCPConfig() {
            try {
                const response = await fetch('/api/mcp/config');
                const config = await response.json();

                // Show/hide MCP config form based on uiConfigMcps setting
                const mcpConfigForm = document.getElementById('mcpConfigForm');
                if (config.uiConfigMcps) {
                    mcpConfigForm.style.display = 'block';
                } else {
                    mcpConfigForm.style.display = 'none';
                }
            } catch (e) {
                console.error('Error checking MCP config:', e);
            }
        }

        // Initialize
        checkAPIStatus(); // Check if API is already configured
        checkMCPConfig(); // Check MCP configuration settings
        refreshMCPServers();
        setInterval(refreshMCPServers, 10000); // Refresh every 10 seconds
    </script>
</body>
</html>
"""

# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import sys
    
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    MCP Chatbot Server                         ║
║                                                              ║
║  Web Interface: http://localhost:{port}                        ║
║                                                              ║
║  Features:                                                   ║
║  • OpenAI-compatible API integration                         ║
║  • Dynamic MCP server management                             ║
║  • Automatic tool calling loop                               ║
║  • Real-time chat interface                                  ║
║  • Comprehensive logging                                     ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(app, host=host, port=port, log_level="info")
