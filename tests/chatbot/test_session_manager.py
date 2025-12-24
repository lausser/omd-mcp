"""
Tests for session_manager module

Tests session creation, default usernames, and session isolation.
"""

import pytest
from datetime import datetime, timedelta
from chatbot.session_manager import UserSession, SessionStore, Message


class TestSessionCreation:
    """Test session creation with various usernames."""

    def test_create_session_with_username(self):
        """Test creating a session with a specific username."""
        store = SessionStore()
        session = store.create_session(username="alice")

        assert session.username == "alice"
        assert session.session_id is not None
        assert len(session.session_id) > 0
        assert session.is_active is True
        assert session.created_at is not None
        assert session.last_activity is not None

    def test_create_session_default_username(self):
        """Test that default username 'chatuser' can be used."""
        store = SessionStore()
        session = store.create_session(username="chatuser")

        assert session.username == "chatuser"
        assert session.is_active is True

    def test_create_session_empty_username_raises_error(self):
        """Test that empty username raises ValueError."""
        store = SessionStore()

        with pytest.raises(ValueError, match="Username cannot be empty"):
            store.create_session(username="")


class TestSessionIsolation:
    """Test that different users get isolated sessions."""

    def test_session_isolation(self):
        """Test that two users get independent sessions with no data sharing."""
        store = SessionStore()

        # Create sessions for two different users
        session_alice = store.create_session(username="alice")
        session_bob = store.create_session(username="bob")

        # Sessions should have different IDs
        assert session_alice.session_id != session_bob.session_id

        # Sessions should have different usernames
        assert session_alice.username == "alice"
        assert session_bob.username == "bob"

        # Add message to Alice's session
        alice_message = Message(role="user", content="Hello from Alice")
        session_alice.conversation_history.append(alice_message)

        # Bob's session should have no messages
        assert len(session_alice.conversation_history) == 1
        assert len(session_bob.conversation_history) == 0

        # Verify sessions are stored independently
        retrieved_alice = store.get_session(session_alice.session_id)
        retrieved_bob = store.get_session(session_bob.session_id)

        assert retrieved_alice.username == "alice"
        assert retrieved_bob.username == "bob"
        assert len(retrieved_alice.conversation_history) == 1
        assert len(retrieved_bob.conversation_history) == 0


class TestUserSession:
    """Test UserSession model behavior."""

    def test_session_id_uniqueness(self):
        """Test that each session gets a unique ID."""
        store = SessionStore()
        session1 = store.create_session("user1")
        session2 = store.create_session("user2")
        session3 = store.create_session("user3")

        ids = {session1.session_id, session2.session_id, session3.session_id}
        assert len(ids) == 3  # All unique

    def test_session_activity_tracking(self):
        """Test that last_activity is tracked correctly."""
        session = UserSession(
            session_id="test123",
            username="testuser"
        )

        original_activity = session.last_activity

        # Simulate time passing
        import time
        time.sleep(0.1)

        session.update_activity()

        assert session.last_activity > original_activity

    def test_message_validation(self):
        """Test that Message validates role and content."""
        # Valid message
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

        # Invalid role
        with pytest.raises(ValueError, match="Invalid role"):
            Message(role="invalid", content="test")

        # Empty content
        with pytest.raises(ValueError, match="content cannot be empty"):
            Message(role="user", content="")
