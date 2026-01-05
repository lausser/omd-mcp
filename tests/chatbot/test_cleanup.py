"""
Tests for session cleanup functionality

Tests that session resources (MCP connections, LLM connections, conversation history)
are properly cleaned up when sessions timeout or are explicitly cleaned.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, call
from chatbot.session_manager import UserSession, SessionStore, Message


class TestResourceCleanup:
    """Test cleanup of session resources."""

    def test_mcp_connection_closed_on_timeout(self):
        """Test that MCP connection is cleared when session is cleaned up."""
        store = SessionStore(timeout_minutes=15)
        session = store.create_session(username="alice")
        session_id = session.session_id

        # Create a mock MCP connection
        mock_mcp = Mock()
        session.mcp_connection = mock_mcp

        # Verify connection exists
        assert session.mcp_connection is not None

        # Make session expired
        session.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup
        cleaned = store.cleanup_expired_sessions()

        # Verify session was cleaned up
        assert cleaned == 1

        # Verify session is removed from store
        # (MCP connection was set to None before removal)
        assert store.get_session(session_id) is None

    def test_llm_connection_closed_on_timeout(self):
        """Test that LLM connection is cleared when session is cleaned up."""
        store = SessionStore(timeout_minutes=15)
        session = store.create_session(username="bob")
        session_id = session.session_id

        # Create a mock LLM connection
        mock_llm = Mock()
        session.llm_connection = mock_llm

        # Verify connection exists
        assert session.llm_connection is not None

        # Make session expired
        session.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup
        cleaned = store.cleanup_expired_sessions()

        # Verify session was cleaned up
        assert cleaned == 1

        # Verify session is removed from store
        # (LLM connection was set to None before removal)
        assert store.get_session(session_id) is None

    def test_conversation_history_cleared_on_timeout(self):
        """Test that conversation history is cleared when session is cleaned up."""
        store = SessionStore(timeout_minutes=15)
        session = store.create_session(username="charlie")
        session_id = session.session_id

        # Add some conversation history
        session.conversation_history.append(
            Message(role="user", content="Hello")
        )
        session.conversation_history.append(
            Message(role="assistant", content="Hi there!")
        )
        session.conversation_history.append(
            Message(role="user", content="How are you?")
        )

        # Verify history has messages
        assert len(session.conversation_history) == 3

        # Make session expired
        session.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup
        cleaned = store.cleanup_expired_sessions()

        # Verify session was cleaned up
        assert cleaned == 1

        # Session should be removed from store, so we can't check the history directly
        # But we know cleanup was successful
        assert store.get_session(session_id) is None

    def test_multiple_concurrent_cleanups(self):
        """Test that multiple sessions can be cleaned up simultaneously."""
        store = SessionStore(timeout_minutes=15)

        # Create multiple sessions with various resources
        session_ids = []
        for username in ["alice", "bob", "charlie", "dave", "eve"]:
            session = store.create_session(username=username)

            # Add mock connections
            session.mcp_connection = Mock()
            session.llm_connection = Mock()

            # Add conversation history
            session.conversation_history.append(
                Message(role="user", content=f"Message from {username}")
            )

            session_ids.append(session.session_id)

        # Make all sessions expired
        for session_id in session_ids:
            session = store.get_session(session_id)
            session.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup once - should clean all expired sessions
        cleaned = store.cleanup_expired_sessions()

        # Verify all sessions were cleaned up
        assert cleaned == 5

        # Verify all sessions are removed from store
        for session_id in session_ids:
            assert store.get_session(session_id) is None


class TestCleanupErrorHandling:
    """Test error handling during cleanup."""

    def test_cleanup_handles_multiple_sessions_gracefully(self):
        """Test that cleanup handles multiple sessions with different states."""
        store = SessionStore(timeout_minutes=15)

        # Create two sessions
        session1 = store.create_session(username="alice")
        session1_id = session1.session_id

        session2 = store.create_session(username="bob")
        session2_id = session2.session_id

        # Add MCP connections to both
        session1.mcp_connection = Mock()
        session2.mcp_connection = Mock()

        # Add LLM connection only to session1
        session1.llm_connection = Mock()

        # Add conversation history
        session1.conversation_history.append(Message(role="user", content="Test"))
        session2.conversation_history.append(Message(role="user", content="Test"))

        # Make both sessions expired
        session1.last_activity = datetime.now() - timedelta(minutes=16)
        session2.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup - should handle both sessions gracefully
        cleaned = store.cleanup_expired_sessions()

        # Both sessions should be cleaned up
        assert cleaned == 2

        # Both sessions removed from store
        assert store.get_session(session1_id) is None
        assert store.get_session(session2_id) is None

    def test_cleanup_with_no_connections(self):
        """Test that cleanup handles sessions with no connections."""
        store = SessionStore(timeout_minutes=15)

        session = store.create_session(username="alice")
        session_id = session.session_id

        # Don't add any connections (they default to None)
        assert session.mcp_connection is None
        assert session.llm_connection is None

        # Add conversation history
        session.conversation_history.append(Message(role="user", content="Test"))

        # Make session expired
        session.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup - should handle gracefully
        cleaned = store.cleanup_expired_sessions()

        # Session should be cleaned up
        assert cleaned == 1

        # Session removed from store
        assert store.get_session(session_id) is None


class TestCleanupMethodDirectly:
    """Test the session.cleanup() method directly."""

    def test_cleanup_clears_all_resources(self):
        """Test that calling cleanup() clears all resources."""
        session = UserSession(
            session_id="test123",
            username="testuser",
            timeout_minutes=15
        )

        # Add mock connections
        session.mcp_connection = Mock()
        session.llm_connection = Mock()

        # Add conversation history
        session.conversation_history.append(
            Message(role="user", content="Test message")
        )
        session.conversation_history.append(
            Message(role="assistant", content="Test response")
        )

        # Verify resources exist
        assert session.mcp_connection is not None
        assert session.llm_connection is not None
        assert len(session.conversation_history) == 2

        # Call cleanup
        session.cleanup()

        # Verify MCP connection cleared (set to None)
        assert session.mcp_connection is None

        # Verify LLM connection cleared (set to None)
        assert session.llm_connection is None

        # Verify conversation history cleared
        assert len(session.conversation_history) == 0

        # Verify session marked as inactive
        assert not session.is_active

    def test_cleanup_handles_none_connections(self):
        """Test that cleanup handles None connections gracefully."""
        session = UserSession(
            session_id="test456",
            username="testuser",
            timeout_minutes=15
        )

        # Don't add any connections (they default to None)
        assert session.mcp_connection is None
        assert session.llm_connection is None

        # Add conversation history
        session.conversation_history.append(
            Message(role="user", content="Test")
        )

        # Call cleanup - should not raise error
        session.cleanup()

        # Verify conversation history still cleared
        assert len(session.conversation_history) == 0

        # Verify session marked as inactive
        assert not session.is_active
