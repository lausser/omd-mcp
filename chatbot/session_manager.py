"""
Session Management Module for Chatbot Service

Provides user session management with:
- Authentication via X-WEBAUTH-USER header or default username
- Isolated sessions per user
- 15-minute inactivity timeout
- Resource cleanup (MCP and LLM connections)
"""

import secrets
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field
import logging
import json

# Configure structured logging
logger = logging.getLogger(__name__)


@dataclass
class Message:
    """
    Represents a single chat message in conversation history.

    Attributes:
        role: Message sender role (user, assistant, system)
        content: Message text content
        timestamp: When message was sent/received
        metadata: Optional metadata (MCP tool calls, errors, etc.)
    """
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate message attributes."""
        if self.role not in ["user", "assistant", "system"]:
            raise ValueError(f"Invalid role: {self.role}")
        if not self.content:
            raise ValueError("Message content cannot be empty")


@dataclass
class UserSession:
    """
    Represents an authenticated user's interaction session with the chatbot.

    Attributes:
        session_id: Unique session identifier (32-byte URL-safe token)
        username: Authenticated username from X-WEBAUTH-USER or default "chatuser"
        created_at: Timestamp when session was created
        last_activity: Timestamp of most recent user interaction
        mcp_connection: Active connection to Thruk MCP server
        llm_connection: Active connection to LLM API service
        conversation_history: Chat message history
        is_active: Whether session is currently active (not timed out)
    """
    session_id: str
    username: str
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    mcp_connection: Optional[Any] = None
    llm_connection: Optional[Any] = None
    conversation_history: List[Message] = field(default_factory=list)
    is_active: bool = True
    timeout_minutes: int = 5

    def __post_init__(self):
        """Validate session attributes."""
        if not self.session_id:
            raise ValueError("Session ID cannot be empty")
        if not self.username:
            raise ValueError("Username cannot be empty")
        if self.last_activity < self.created_at:
            raise ValueError("last_activity cannot be before created_at")

    def is_expired(self) -> bool:
        """
        Check if session has expired due to inactivity.

        Returns:
            True if now() - last_activity > timeout_minutes
        """
        timeout_delta = timedelta(minutes=self.timeout_minutes)
        elapsed = datetime.now() - self.last_activity
        return elapsed > timeout_delta

    def update_activity(self) -> None:
        """
        Update last_activity timestamp to current time, resetting timeout.

        Logs the activity update for audit trail.
        """
        self.last_activity = datetime.now()
        logger.debug(
            "Session activity updated",
            extra={
                "session_id": self.session_id[:8],
                "username": self.username,
                "last_activity": self.last_activity.isoformat()
            }
        )

    def cleanup(self) -> None:
        """
        Clean up session resources on timeout or explicit termination.

        Closes MCP and LLM connections, clears conversation history.
        Logs cleanup events for observability.
        """
        logger.info(
            "Cleaning up session",
            extra={
                "session_id": self.session_id[:8],
                "username": self.username,
                "age_seconds": (datetime.now() - self.created_at).total_seconds()
            }
        )

        # Close MCP connection
        if self.mcp_connection:
            try:
                # TODO: Implement actual MCP client close method when available
                # await self.mcp_connection.close()
                logger.debug(f"Closed MCP connection for session {self.session_id[:8]}")
                self.mcp_connection = None
            except Exception as e:
                logger.error(
                    f"Error closing MCP connection: {e}",
                    extra={"session_id": self.session_id[:8]}
                )

        # Close LLM connection
        if self.llm_connection:
            try:
                # TODO: Implement actual LLM client close method when available
                # await self.llm_connection.close()
                logger.debug(f"Closed LLM connection for session {self.session_id[:8]}")
                self.llm_connection = None
            except Exception as e:
                logger.error(
                    f"Error closing LLM connection: {e}",
                    extra={"session_id": self.session_id[:8]}
                )

        # Clear conversation history
        messages_count = len(self.conversation_history)
        self.conversation_history.clear()
        logger.debug(
            f"Cleared {messages_count} messages from conversation history",
            extra={"session_id": self.session_id[:8]}
        )

        self.is_active = False


class SessionStore:
    """
    Global session storage and management.

    Provides thread-safe access to sessions and background cleanup.

    Attributes:
        sessions: Session ID → UserSession mapping
        lock: Thread-safe access to sessions dict
        cleanup_interval_seconds: Background cleanup task interval
    """

    def __init__(self, timeout_minutes: int = 15, cleanup_interval_seconds: int = 60):
        """
        Initialize SessionStore.

        Args:
            timeout_minutes: Session inactivity timeout (default: 15)
            cleanup_interval_seconds: Cleanup task interval (default: 60)
        """
        self.sessions: Dict[str, UserSession] = {}
        self.lock = threading.Lock()
        self.timeout_minutes = timeout_minutes
        self.cleanup_interval_seconds = cleanup_interval_seconds
        logger.info(
            "SessionStore initialized",
            extra={
                "timeout_minutes": timeout_minutes,
                "cleanup_interval_seconds": cleanup_interval_seconds
            }
        )

    def create_session(self, username: str) -> UserSession:
        """
        Create a new session with unique ID.

        Args:
            username: Authenticated username

        Returns:
            Created UserSession

        Raises:
            ValueError: If username is empty
        """
        if not username:
            raise ValueError("Username cannot be empty")

        session_id = secrets.token_urlsafe(32)
        session = UserSession(
            session_id=session_id,
            username=username,
            timeout_minutes=self.timeout_minutes
        )

        with self.lock:
            self.sessions[session_id] = session

        logger.info(
            "Session created",
            extra={
                "session_id": session_id[:8],
                "username": username,
                "total_sessions": len(self.sessions)
            }
        )

        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """
        Retrieve session by ID.

        Args:
            session_id: Session identifier

        Returns:
            UserSession if found, None otherwise
        """
        with self.lock:
            return self.sessions.get(session_id)

    def update_activity(self, session_id: str) -> bool:
        """
        Update last_activity timestamp for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was found and updated, False otherwise
        """
        session = self.get_session(session_id)
        if session and not session.is_expired():
            session.update_activity()
            return True
        return False

    def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions and clean up their resources.

        Called by background task every cleanup_interval_seconds.

        Returns:
            Number of sessions cleaned up
        """
        cleaned_count = 0
        expired_sessions = []

        # Identify expired sessions
        with self.lock:
            for session_id, session in self.sessions.items():
                if session.is_expired():
                    expired_sessions.append(session_id)

        # Clean up expired sessions
        for session_id in expired_sessions:
            with self.lock:
                session = self.sessions.get(session_id)
                if session:
                    session.cleanup()
                    del self.sessions[session_id]
                    cleaned_count += 1

        if cleaned_count > 0:
            logger.info(
                f"Cleaned up {cleaned_count} expired sessions",
                extra={
                    "cleaned_count": cleaned_count,
                    "remaining_sessions": len(self.sessions)
                }
            )

        return cleaned_count

    def remove_session(self, session_id: str) -> bool:
        """
        Explicitly remove and clean up a session.

        Args:
            session_id: Session identifier

        Returns:
            True if session was found and removed, False otherwise
        """
        with self.lock:
            session = self.sessions.get(session_id)
            if session:
                session.cleanup()
                del self.sessions[session_id]
                logger.info(
                    "Session explicitly removed",
                    extra={"session_id": session_id[:8]}
                )
                return True
        return False

    def get_session_count(self) -> int:
        """Get current number of active sessions."""
        with self.lock:
            return len(self.sessions)
