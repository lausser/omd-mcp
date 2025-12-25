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
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from chatbot.session_manager import SessionStore, Message

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Session configuration from environment
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "15"))
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "chatuser")
SESSION_CLEANUP_INTERVAL = int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS", "60"))

# Initialize session store
session_store = SessionStore(
    timeout_minutes=SESSION_TIMEOUT_MINUTES,
    cleanup_interval_seconds=SESSION_CLEANUP_INTERVAL
)

# Templates - support both local and containerized environments
import pathlib
_current_dir = pathlib.Path(__file__).parent
_templates_dir = _current_dir / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))


async def cleanup_sessions_background():
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
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.

    Starts background cleanup task on startup.
    """
    # Startup
    logger.info("Starting chatbot service")
    logger.info(f"Session timeout: {SESSION_TIMEOUT_MINUTES} minutes")
    logger.info(f"Default username: {DEFAULT_USERNAME}")

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
async def session_middleware(request: Request, call_next):
    """
    Session middleware to track activity and validate sessions.

    Updates last_activity for valid sessions on each request.
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
async def index(request: Request, response: Response):
    """
    Initialize session and load chatbot UI.

    Extracts username from X-WEBAUTH-USER header or uses default.
    Creates new session and sets session cookie.

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
        "index.html",
        {
            "request": request,
            "username": username,
            "session_id": session.session_id[:8]  # Truncated for display
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
async def session_heartbeat(request: Request):
    """
    Reset session inactivity timer.

    Called on user interactions to keep session alive.

    Returns:
        Session status information
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session or session.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": "Session has ended after inactivity",
                "expired_at": datetime.now().isoformat()
            }
        )

    # Update activity
    session.update_activity()

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
async def session_status(request: Request):
    """
    Check session status.

    Returns:
        Current session information including expiration status
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


@app.post("/api/chat")
async def chat(request: Request):
    """
    Send chat message to LLM.

    Processes user message, invokes Thruk MCP tools if needed (passing username),
    and returns assistant response.

    Updates session activity timestamp.
    """
    session_id = get_session_from_cookie(request)

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No session cookie"
        )

    session = session_store.get_session(session_id)

    if not session or session.is_expired():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "session_expired",
                "message": "Session has ended after inactivity"
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

    # TODO: Implement LLM integration
    # TODO: Implement MCP tool invocation with username parameter
    # For now, return a placeholder response

    assistant_response = f"[Placeholder] Received your message. " \
                        f"Session user: {session.username}. " \
                        f"MCP tools would be invoked with username='{session.username}'."

    # Add assistant response to conversation history
    session.conversation_history.append(
        Message(role="assistant", content=assistant_response)
    )

    return {
        "response": assistant_response,
        "tool_calls": []  # TODO: Populate when MCP integration added
    }


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
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
        log_level="info"
    )
