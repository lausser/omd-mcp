"""
Chatbot Service - Main Application

FastAPI application providing:
- User authentication via X-WEBAUTH-USER header or default username
- Session management with 15-minute timeout
- Web UI with username display
- LLM integration with Thruk MCP tool access
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, AsyncIterator, List, Tuple, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from chatbot.session_manager import SessionStore, Message

# Load environment variables (before logging configuration)
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import OpenAI client (optional dependency)
try:
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI library not installed. OpenAI LLM features will be disabled.")

# Try to import Gemini client (optional dependency)
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("Google GenAI library not installed. Gemini features will be disabled.")

# Try to import MCP client (optional dependency)
try:
    from fastmcp.client import Client
    from fastmcp.client.transports import PythonStdioTransport
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("FastMCP library not installed. MCP tool features will be disabled.")

# Session configuration from environment
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "15"))
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "chatuser")
SESSION_CLEANUP_INTERVAL = int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS", "60"))

# LLM Provider selection
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

# OpenAI configuration from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")

# Gemini configuration from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_BASE_URL = os.getenv("GEMINI_BASE_URL", "")  # Empty = cloud
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_VERTEXAI = os.getenv("GEMINI_VERTEXAI", "false").lower() == "true"

# Initialize LLM clients based on provider
openai_client = None
gemini_client = None

if LLM_PROVIDER == "openai":
    if OPENAI_AVAILABLE and OPENAI_API_KEY:
        openai_client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL
        )
        logger.info(f"OpenAI client initialized: {OPENAI_BASE_URL} / {OPENAI_MODEL}")
    elif OPENAI_AVAILABLE and not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set. LLM features will be disabled.")
    elif not OPENAI_AVAILABLE:
        logger.warning("OpenAI library not available. Please install: pip install openai>=1.10.0")
elif LLM_PROVIDER == "gemini":
    if GEMINI_AVAILABLE and GEMINI_API_KEY:
        # Build client configuration
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            vertexai=GEMINI_VERTEXAI,
            http_options={"base_url": GEMINI_BASE_URL} if GEMINI_BASE_URL else None
        )
        logger.info(f"Gemini client initialized: {GEMINI_BASE_URL or 'cloud'} / {GEMINI_MODEL} (vertexai={GEMINI_VERTEXAI})")
    elif GEMINI_AVAILABLE and not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set. LLM features will be disabled.")
    elif not GEMINI_AVAILABLE:
        logger.warning("Google GenAI library not available. Please install: pip install google-genai>=0.3.0")
else:
    logger.error(f"Unknown LLM_PROVIDER: {LLM_PROVIDER}. Must be 'openai' or 'gemini'.")

# Thruk MCP configuration - spawned as subprocess, auto-configures itself
# The thruk_mcp.py script handles its own OMD environment detection and
# auto-loads secret.key and THRUK_BASE_URL from the OMD site

# MCP client globals
mcp_client_available = False  # Whether MCP client can be created
mcp_tools_cache = []  # Cached list of available MCP tools


async def get_mcp_tools() -> List[Dict[str, Any]]:
    """
    Get list of available MCP tools from Thruk MCP server.

    Returns:
        List of tool dictionaries in OpenAI function calling format
    """
    global mcp_tools_cache

    if not MCP_AVAILABLE:
        return []

    # Return cached tools if available
    if mcp_tools_cache:
        return mcp_tools_cache

    try:
        # Find thruk_mcp.py - it should be in lib/python/thruk_mcp/
        # In OMD, use site's lib/python, not version's lib/python (permission issue)
        if os.getenv("OMD_ROOT"):
            # OMD environment: use site's lib/python directory
            thruk_mcp_path = os.path.join(os.getenv("OMD_ROOT"), "lib", "python", "thruk_mcp", "thruk_mcp.py")
        else:
            # Containerized or local: use relative path from chatbot.py
            thruk_mcp_path = os.path.join(os.path.dirname(__file__), "..", "thruk_mcp", "thruk_mcp.py")
            thruk_mcp_path = os.path.abspath(thruk_mcp_path)

        if not os.path.exists(thruk_mcp_path):
            logger.error(f"Thruk MCP server not found at {thruk_mcp_path}")
            return []

        logger.debug(f"Using Thruk MCP server at: {thruk_mcp_path}")

        # Spawn thruk_mcp.py as subprocess with stdio transport
        transport = PythonStdioTransport(thruk_mcp_path, env=os.environ.copy())

        async with Client(transport) as client:
            # List available tools
            tools_response = await client.list_tools()

            # Handle different response formats from FastMCP
            if isinstance(tools_response, list):
                # Sometimes returns a list directly
                mcp_tools = tools_response
            elif hasattr(tools_response, 'result'):
                # Usually returns JSONRPCResponse with .result['tools']
                mcp_tools = tools_response.result['tools']
            elif hasattr(tools_response, 'tools'):
                # Or might have .tools attribute
                mcp_tools = tools_response.tools
            else:
                logger.error(f"Unexpected tools_response type: {type(tools_response)}")
                mcp_tools = []

            # Convert MCP tools to OpenAI function format
            openai_tools = []
            for tool in mcp_tools:
                # Handle both dict and object formats
                if isinstance(tool, dict):
                    name = tool.get('name', '')
                    description = tool.get('description', '')
                    parameters = tool.get('inputSchema', {"type": "object", "properties": {}})
                else:
                    # Tool object with attributes
                    name = getattr(tool, 'name', '')
                    description = getattr(tool, 'description', '')
                    parameters = getattr(tool, 'inputSchema', {"type": "object", "properties": {}})

                openai_tool = {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters
                    }
                }
                openai_tools.append(openai_tool)

            # Cache the tools
            mcp_tools_cache = openai_tools
            logger.info(f"Cached {len(openai_tools)} MCP tools for LLM function calling")

            return openai_tools

    except Exception as e:
        logger.error(f"Failed to get MCP tools: {e}")
        return []


async def call_mcp_tool(tool_name: str, arguments: Dict[str, Any], username: str) -> Any:
    """
    Call an MCP tool with the given arguments.

    Args:
        tool_name: Name of the MCP tool to call
        arguments: Tool arguments as a dictionary
        username: Username to pass to the tool for authorization

    Returns:
        Tool result
    """
    if not MCP_AVAILABLE:
        return {"error": "MCP not available"}

    try:
        # Add username to arguments if not present
        if "username" not in arguments:
            arguments["username"] = username

        # Find thruk_mcp.py - it should be in lib/python/thruk_mcp/
        # In OMD, use site's lib/python, not version's lib/python (permission issue)
        if os.getenv("OMD_ROOT"):
            # OMD environment: use site's lib/python directory
            thruk_mcp_path = os.path.join(os.getenv("OMD_ROOT"), "lib", "python", "thruk_mcp", "thruk_mcp.py")
        else:
            # Containerized or local: use relative path from chatbot.py
            thruk_mcp_path = os.path.join(os.path.dirname(__file__), "..", "thruk_mcp", "thruk_mcp.py")
            thruk_mcp_path = os.path.abspath(thruk_mcp_path)

        if not os.path.exists(thruk_mcp_path):
            logger.error(f"Thruk MCP server not found at {thruk_mcp_path}")
            return {"error": "Thruk MCP server not found"}

        logger.debug(f"Using Thruk MCP server at: {thruk_mcp_path}")

        # Spawn thruk_mcp.py as subprocess with stdio transport
        transport = PythonStdioTransport(thruk_mcp_path, env=os.environ.copy())

        async with Client(transport) as client:
            # Call the tool
            result = await client.call_tool(tool_name, arguments)

            logger.info(f"MCP tool called: {tool_name} by {username}")
            logger.debug(f"Tool arguments: {arguments}")
            logger.debug(f"Tool result: {result}")

            return result

    except Exception as e:
        logger.error(f"Failed to call MCP tool {tool_name}: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# Initialize session store
session_store = SessionStore(
    timeout_minutes=SESSION_TIMEOUT_MINUTES,
    cleanup_interval_seconds=SESSION_CLEANUP_INTERVAL
)

# Templates - support OMD, containerized, and local development environments
import pathlib

# Determine template directory based on environment
if os.getenv("OMD_ROOT"):
    # OMD environment: templates are in $OMD_ROOT/share/chatbot/templates/
    _templates_dir = pathlib.Path(os.getenv("OMD_ROOT")) / "share" / "chatbot" / "templates"
else:
    # Containerized or local development: templates are relative to this file
    _current_dir = pathlib.Path(__file__).parent
    _templates_dir = _current_dir / "templates"

logger.debug(f"Using templates directory: {_templates_dir}")
templates = Jinja2Templates(directory=str(_templates_dir))


async def cleanup_sessions_background() -> None:
    """
    Background task to clean up expired sessions.

    Runs every SESSION_CLEANUP_INTERVAL seconds.
    """
    while True:
        try:
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
            cleaned = session_store.cleanup_expired_sessions()
            if cleaned > 0:
                logger.info(f"Background cleanup removed {cleaned} expired sessions")
        except Exception as e:
            logger.error(f"Error in background cleanup task: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Lifespan context manager for FastAPI application.

    Starts background cleanup task on startup.

    Args:
        app: FastAPI application instance

    Yields:
        None during application runtime
    """
    # Startup
    logger.info("Starting chatbot service")
    logger.info(f"Session timeout: {SESSION_TIMEOUT_MINUTES} minutes")
    logger.info(f"Default username: {DEFAULT_USERNAME}")

    # Log LLM status
    if LLM_PROVIDER == "openai" and openai_client:
        logger.info(f"LLM enabled: OpenAI - {OPENAI_MODEL} via {OPENAI_BASE_URL}")
    elif LLM_PROVIDER == "gemini" and gemini_client:
        logger.info(f"LLM enabled: Gemini - {GEMINI_MODEL} (cloud={not GEMINI_BASE_URL}, vertexai={GEMINI_VERTEXAI})")
    else:
        logger.warning(f"LLM disabled: Provider '{LLM_PROVIDER}' not configured")

    # Initialize MCP tools if available (spawns thruk_mcp.py subprocess)
    mcp_tools = []
    if MCP_AVAILABLE:
        logger.info(f"Initializing MCP client (stdio subprocess)")
        try:
            mcp_tools = await get_mcp_tools()
            if mcp_tools:
                logger.info(f"MCP enabled: {len(mcp_tools)} tools available")
                global mcp_client_available
                mcp_client_available = True
            else:
                logger.warning("MCP server returned no tools")
        except Exception as e:
            logger.error(f"Failed to initialize MCP tools: {e}")
    else:
        logger.warning("MCP library not available")
        logger.warning("Thruk MCP disabled")

    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_sessions_background())

    yield

    # Shutdown
    logger.info("Shutting down chatbot service")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# Create FastAPI application
app = FastAPI(
    title="Thruk Chatbot",
    description="AI-powered chatbot for Thruk monitoring system",
    version="1.0.0",
    lifespan=lifespan
)


def extract_username_from_header(request: Request) -> str:
    """
    Extract username from X-WEBAUTH-USER header or use default.

    Args:
        request: FastAPI request object

    Returns:
        Username from header or DEFAULT_USERNAME if absent/empty
    """
    username = request.headers.get("X-WEBAUTH-USER", "").strip()

    if not username:
        username = DEFAULT_USERNAME
        logger.debug(f"No X-WEBAUTH-USER header, using default: {DEFAULT_USERNAME}")
    else:
        logger.debug(f"Extracted username from header: {username}")

    return username


def get_session_from_cookie(request: Request) -> Optional[str]:
    """
    Extract session_id from cookie.

    Args:
        request: FastAPI request object

    Returns:
        Session ID if present, None otherwise
    """
    return request.cookies.get("session_id")


@app.middleware("http")
async def session_middleware(request: Request, call_next: Callable) -> Response:
    """
    Session middleware to track activity and validate sessions.

    Updates last_activity for valid sessions on each request.

    Args:
        request: Incoming HTTP request
        call_next: Next middleware/endpoint handler

    Returns:
        HTTP response from downstream handler
    """
    session_id = get_session_from_cookie(request)

    if session_id:
        session = session_store.get_session(session_id)

        if session:
            if session.is_expired():
                logger.info(f"Session {session_id[:8]} expired")
                # Session expired - will be handled by endpoint
            else:
                # Update activity for valid session
                session.update_activity()
                logger.debug(f"Updated activity for session {session_id[:8]}")

    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, response: Response) -> HTMLResponse:
    """
    Initialize session and load chatbot UI.

    Extracts username from X-WEBAUTH-USER header or uses default.
    Creates new session and sets session cookie.

    Args:
        request: Incoming HTTP request
        response: HTTP response object

    Returns:
        HTML page with username displayed and session cookie set
    """
    # Extract username from header
    username = extract_username_from_header(request)

    # Create new session
    session = session_store.create_session(username=username)

    logger.info(
        f"New session created for user '{username}'",
        extra={"session_id": session.session_id[:8], "username": username}
    )

    # Set session cookie
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "username": username,
            "session_id": session.session_id[:8],  # Truncated for display
            "session_timeout_minutes": SESSION_TIMEOUT_MINUTES  # For heartbeat calculation
        }
    )

    # Set HTTP-only cookie for security
    response.set_cookie(
        key="session_id",
        value=session.session_id,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TIMEOUT_MINUTES * 60
    )

    return response


@app.post("/api/session/heartbeat")
async def session_heartbeat(request: Request) -> Dict[str, Any]:
    """
    Reset session inactivity timer.

    Called on user interactions to keep session alive.

    Args:
        request: Incoming HTTP request

    Returns:
        Session status information including username and expiration time

    Raises:
        HTTPException: 401 if session is invalid or expired
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session:
        logger.warning(f"Heartbeat for non-existent session {session_id[:8]}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_not_found",
                "message": "Session not found",
                "session_id": session_id[:8]
            }
        )

    if session.is_expired():
        from datetime import timedelta
        elapsed_seconds = (datetime.now() - session.last_activity).total_seconds()
        logger.warning(
            f"Heartbeat for expired session {session_id[:8]}",
            extra={
                "elapsed_seconds": elapsed_seconds,
                "timeout_seconds": session.timeout_minutes * 60,
                "last_activity": session.last_activity.isoformat()
            }
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": f"Session has ended after {int(elapsed_seconds/60)} minutes of inactivity",
                "expired_at": datetime.now().isoformat(),
                "last_activity": session.last_activity.isoformat()
            }
        )

    # Update activity
    session.update_activity()
    logger.info(
        f"Heartbeat successful for session {session_id[:8]}",
        extra={"username": session.username}
    )

    # Calculate time until expiration
    from datetime import timedelta
    timeout_delta = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    elapsed = datetime.now() - session.last_activity
    expires_in = int((timeout_delta - elapsed).total_seconds())

    return {
        "session_id": session_id[:8],
        "username": session.username,
        "last_activity": session.last_activity.isoformat(),
        "expires_in_seconds": expires_in
    }


@app.get("/api/session/status")
async def session_status(request: Request) -> Dict[str, Any]:
    """
    Check session status.

    Args:
        request: Incoming HTTP request

    Returns:
        Current session information including expiration status

    Raises:
        HTTPException: 401 if session is invalid or expired
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": "Session has ended after inactivity"
            }
        )

    if session.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": "Session has ended after inactivity",
                "expired_at": datetime.now().isoformat()
            }
        )

    # Calculate time until expiration
    from datetime import timedelta
    timeout_delta = timedelta(minutes=SESSION_TIMEOUT_MINUTES)
    elapsed = datetime.now() - session.last_activity
    expires_in = int((timeout_delta - elapsed).total_seconds())

    return {
        "session_id": session_id[:8],
        "username": session.username,
        "is_active": session.is_active and not session.is_expired(),
        "expires_in_seconds": expires_in
    }


async def call_llm_openai(conversation_history: List[Message], username: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Call OpenAI-compatible LLM with conversation history and MCP tool support.
    Uses manual tool calling loop.

    Args:
        conversation_history: List of Message objects
        username: Current user's username

    Returns:
        Tuple of (assistant response text, list of tool calls made)

    Raises:
        HTTPException: If OpenAI is not configured or API call fails
    """
    if not openai_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM service not configured. Please set OPENAI_API_KEY."
        )

    # Convert conversation history to OpenAI format
    messages = [
        {"role": msg.role, "content": msg.content}
        for msg in conversation_history
    ]

    # Add system message at the beginning
    system_message = {
        "role": "system",
        "content": f"You are a helpful assistant for the Thruk monitoring system. "
                  f"The current user is: {username}. "
                  f"You have access to Thruk monitoring tools to query hosts, services, downtimes, and other monitoring data. "
                  f"Use the available tools when the user asks about monitoring information. "
                  f"Provide clear, concise answers about monitoring, hosts, services, and related topics.\n\n"
                  f"IMPORTANT ERROR HANDLING:\n"
                  f"- If a tool returns an error (e.g., 'error' field in response), YOU MUST report this error to the user clearly.\n"
                  f"- Never claim success when a tool returned an error.\n"
                  f"- If an error mentions validation failures or invalid names, explain what was wrong.\n\n"
                  f"DOWNTIME VERIFICATION:\n"
                  f"- After scheduling any downtime (host, service, hostgroup, servicegroup), if no error occurred, "
                  f"immediately call thruk_list_downtimes to verify the downtime was actually created.\n"
                  f"- Only report success after confirming the downtime appears in the active downtimes list."
    }
    messages.insert(0, system_message)

    # Get available MCP tools
    tools = await get_mcp_tools()

    logger.debug(f"Calling LLM with {len(messages)} messages and {len(tools)} tools")

    try:
        # Initial LLM call with tools
        call_params = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "temperature":0.7,
            "max_tokens": 1000
        }

        # Add tools if available
        if tools:
            call_params["tools"] = tools
            call_params["tool_choice"] = "auto"

        response = await openai_client.chat.completions.create(**call_params)

        choice = response.choices[0]
        tool_calls_made = []

        # Check if LLM wants to call tools
        if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
            logger.info(f"LLM requested {len(choice.message.tool_calls)} tool calls")

            # Add assistant's tool call message to conversation
            messages.append({
                "role": "assistant",
                "content": choice.message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in choice.message.tool_calls
                ]
            })

            # Execute each tool call
            for tool_call in choice.message.tool_calls:
                import json
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                logger.info(f"Executing MCP tool: {tool_name}")

                # Call the MCP tool
                tool_result = await call_mcp_tool(tool_name, tool_args, username)

                # Extract actual data from FastMCP CallToolResult object
                if hasattr(tool_result, 'data') and tool_result.data:
                    # Use .data attribute (dict) if available
                    tool_output = tool_result.data
                elif hasattr(tool_result, 'content') and isinstance(tool_result.content, list) and len(tool_result.content) > 0:
                    # Extract text from first TextContent object
                    first_content = tool_result.content[0]
                    if hasattr(first_content, 'text'):
                        # Try to parse as JSON, otherwise use as-is
                        try:
                            tool_output = json.loads(first_content.text)
                        except (json.JSONDecodeError, AttributeError):
                            tool_output = first_content.text
                    else:
                        tool_output = str(first_content)
                elif hasattr(tool_result, 'result'):
                    # Fallback to .result attribute if present
                    tool_output = tool_result.result
                else:
                    # Last resort: use the object as-is (assume it's already serializable)
                    tool_output = tool_result

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_output) if not isinstance(tool_output, str) else tool_output
                })

                tool_calls_made.append({
                    "tool": tool_name,
                    "arguments": tool_args,
                    "result": tool_output
                })

            # Make second LLM call with tool results
            response = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )

            assistant_message = response.choices[0].message.content
        else:
            # No tool calls, just return the response
            assistant_message = choice.message.content

        # Ensure assistant_message is never None (prevents empty bubbles in UI)
        if assistant_message is None:
            assistant_message = ""

        logger.debug(f"LLM response received: {len(assistant_message or '')} characters, {len(tool_calls_made)} tool calls")

        return assistant_message, tool_calls_made

    except Exception as e:
        logger.error(f"LLM API error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM API error: {str(e)}"
        )


async def call_llm_gemini(conversation_history: List[Message], username: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Call Google Gemini API with conversation history and MCP tool support.
    Uses automatic function calling (SDK handles tool loop).

    Args:
        conversation_history: List of Message objects
        username: Current user's username

    Returns:
        Tuple of (assistant response text, list of tool calls made)

    Raises:
        HTTPException: If Gemini is not configured or API call fails
    """
    if not gemini_client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gemini service not configured. Please set GEMINI_API_KEY."
        )

    # Convert conversation history to Gemini format
    # Gemini expects a single prompt or list of parts
    # For multi-turn conversations, concatenate with clear delimiters
    conversation_text = ""
    for msg in conversation_history:
        if msg.role == "user":
            conversation_text += f"User: {msg.content}\n\n"
        elif msg.role == "assistant":
            conversation_text += f"Assistant: {msg.content}\n\n"

    # Build system instruction
    system_instruction = (
        f"You are a helpful assistant for the Thruk monitoring system. "
        f"The current user is: {username}. "
        f"You have access to Thruk monitoring tools to query hosts, services, downtimes, and other monitoring data. "
        f"Use the available tools when the user asks about monitoring information. "
        f"Provide clear, concise answers about monitoring, hosts, services, and related topics.\n\n"
        f"IMPORTANT ERROR HANDLING:\n"
        f"- If a tool returns an error (e.g., 'error' field in response), YOU MUST report this error to the user clearly.\n"
        f"- Never claim success when a tool returned an error.\n"
        f"- If an error mentions validation failures or invalid names, explain what was wrong.\n\n"
        f"DOWNTIME VERIFICATION:\n"
        f"- After scheduling any downtime (host, service, hostgroup, servicegroup), if no error occurred, "
        f"immediately call thruk_list_downtimes to verify the downtime was actually created.\n"
        f"- Only report success after confirming the downtime appears in the active downtimes list."
    )

    logger.debug(f"Calling Gemini with conversation history and automatic function calling")

    try:
        # Find thruk_mcp.py path (same logic as get_mcp_tools)
        if os.getenv("OMD_ROOT"):
            thruk_mcp_path = os.path.join(os.getenv("OMD_ROOT"), "lib", "python", "thruk_mcp", "thruk_mcp.py")
        else:
            thruk_mcp_path = os.path.join(os.path.dirname(__file__), "..", "thruk_mcp", "thruk_mcp.py")
            thruk_mcp_path = os.path.abspath(thruk_mcp_path)

        if not os.path.exists(thruk_mcp_path):
            logger.error(f"Thruk MCP server not found at {thruk_mcp_path}")
            # Fall back to no tools
            mcp_session = None
        else:
            # Create persistent MCP session for this API call
            transport = PythonStdioTransport(thruk_mcp_path, env=os.environ.copy())
            mcp_session = Client(transport)

        # Call Gemini with automatic function calling
        if mcp_session:
            async with mcp_session:
                response = await gemini_client.aio.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=conversation_text,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        tools=[mcp_session.session],  # Pass MCP session directly
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=False
                        ),
                        temperature=0.7,
                        max_output_tokens=1000
                    )
                )
        else:
            # No tools available
            response = await gemini_client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=conversation_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    max_output_tokens=1000
                )
            )

        # Extract response text
        assistant_message = response.text if response.text else ""

        # Extract tool calls made (if available in response metadata)
        # Note: Gemini's automatic function calling may not expose individual tool calls
        # We'll log what we can but may not have full details
        tool_calls_made = []

        # Try to extract tool usage from response metadata
        if hasattr(response, 'usage_metadata') and response.usage_metadata:
            logger.debug(f"Gemini usage metadata: {response.usage_metadata}")

        # Log candidates info for debugging
        if hasattr(response, 'candidates') and response.candidates:
            for i, candidate in enumerate(response.candidates):
                logger.debug(f"Candidate {i}: finish_reason={candidate.finish_reason}")

                # Log all parts in the candidate for debugging
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    logger.debug(f"Candidate {i} has {len(candidate.content.parts)} parts")
                    for j, part in enumerate(candidate.content.parts):
                        part_type = type(part).__name__
                        logger.debug(f"  Part {j}: {part_type}")

                        # Log function calls if present
                        if hasattr(part, 'function_call') and part.function_call:
                            logger.info(f"    Function call: {part.function_call.name}")
                            logger.debug(f"    Arguments: {part.function_call.args}")
                            tool_calls_made.append({
                                "tool": part.function_call.name,
                                "arguments": dict(part.function_call.args) if part.function_call.args else {},
                                "result": "(handled by Gemini SDK)"
                            })

                        # Log function responses if present
                        if hasattr(part, 'function_response') and part.function_response:
                            logger.info(f"    Function response: {part.function_response.name}")
                            logger.debug(f"    Response content: {part.function_response.response}")

                # Old way (deprecated but keep for compatibility)
                if hasattr(candidate, 'function_calls') and candidate.function_calls:
                    logger.info(f"Function calls made (old format): {len(candidate.function_calls)}")
                    for fc in candidate.function_calls:
                        tool_calls_made.append({
                            "tool": fc.name,
                            "arguments": fc.args,
                            "result": "(handled by Gemini SDK)"
                        })

        logger.debug(f"Gemini response received: {len(assistant_message)} characters")
        if tool_calls_made:
            logger.info(f"Total tool calls detected: {len(tool_calls_made)}")

        return assistant_message, tool_calls_made

    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Gemini API error: {str(e)}"
        )


async def call_llm(conversation_history: List[Message], username: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Call LLM with conversation history and MCP tool support.
    Routes to appropriate provider based on LLM_PROVIDER configuration.

    Args:
        conversation_history: List of Message objects
        username: Current user's username

    Returns:
        Tuple of (assistant response text, list of tool calls made)

    Raises:
        HTTPException: If LLM is not configured or API call fails
    """
    if LLM_PROVIDER == "openai":
        return await call_llm_openai(conversation_history, username)
    elif LLM_PROVIDER == "gemini":
        return await call_llm_gemini(conversation_history, username)
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unknown LLM provider: {LLM_PROVIDER}"
        )


@app.post("/api/chat")
async def chat(request: Request) -> Dict[str, Any]:
    """
    Send chat message to LLM.

    Processes user message, invokes Thruk MCP tools if needed (passing username),
    and returns assistant response.

    Updates session activity timestamp.

    Args:
        request: Incoming HTTP request with JSON body containing 'message' field

    Returns:
        Dictionary with 'response' (assistant message) and 'tool_calls' (MCP tools used)

    Raises:
        HTTPException: 400 if message is invalid, 401 if session expired,
                      500/503 if LLM fails
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session or session.is_expired():
        # Calculate idle time if session still exists
        idle_minutes = None
        if session:
            idle_seconds = (datetime.now() - session.last_activity).total_seconds()
            idle_minutes = int(idle_seconds / 60)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": f"Session has expired after {SESSION_TIMEOUT_MINUTES} minutes of inactivity",
                "timeout_minutes": SESSION_TIMEOUT_MINUTES,
                "idle_minutes": idle_minutes
            }
        )

    # Update activity
    session.update_activity()

    # Parse request body
    try:
        body = await request.json()
        user_message = body.get("message", "")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request body: {e}"
        )

    if not user_message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message cannot be empty"
        )

    # Add user message to conversation history
    session.conversation_history.append(
        Message(role="user", content=user_message)
    )

    logger.info(
        f"User message received from {session.username}",
        extra={
            "session_id": session_id[:8],
            "username": session.username,
            "message_length": len(user_message)
        }
    )

    # Log actual message content at DEBUG level
    logger.debug(
        f"Message content: {user_message}",
        extra={
            "session_id": session_id[:8],
            "username": session.username
        }
    )

    # Call LLM with conversation history (with MCP tool support)
    try:
        assistant_response, tool_calls = await call_llm(session.conversation_history, session.username)
    except HTTPException:
        # Re-raise HTTP exceptions (already logged in call_llm)
        raise
    except Exception as e:
        logger.error(f"Unexpected error during LLM call: {e}", exc_info=True)

        # Show detailed errors to omdadmin for debugging
        if session.username == "omdadmin":
            import traceback
            error_detail = {
                "error": "LLM API Error (Admin View)",
                "type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail
            )
        else:
            # Generic error for regular users
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An error occurred while processing your request."
            )

    # Log assistant response at DEBUG level
    logger.debug(
        f"Assistant response: {(assistant_response or '')[:200]}...",
        extra={
            "session_id": session_id[:8],
            "username": session.username,
            "tool_calls_made": len(tool_calls)
        }
    )

    # Add assistant response to conversation history
    if assistant_response:
        session.conversation_history.append(
            Message(role="assistant", content=assistant_response)
        )

    return {
        "response": assistant_response,
        "tool_calls": tool_calls
    }


# Health check endpoint
@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for container orchestration.

    Returns:
        Dictionary with status, active session count, and timestamp
    """
    return {
        "status": "healthy",
        "active_sessions": session_store.get_session_count(),
        "timestamp": datetime.now().isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "chatbot:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=True,
        log_level="debug"
    )
