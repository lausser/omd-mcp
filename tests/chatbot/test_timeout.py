"""
Tests for session timeout functionality

Tests that sessions expire after the configured timeout period,
activity tracking resets the timeout, and multiple sessions timeout independently.

Note: These tests manually set session timestamps rather than mocking time,
since datetime is an immutable built-in type that cannot be easily patched.
"""

import pytest
import time
from datetime import datetime, timedelta
from chatbot.session_manager import UserSession, SessionStore, Message


class TestSessionTimeout:
    """Test session timeout behavior."""

    def test_session_expires_after_15_minutes(self):
        """Test that a session expires after 15 minutes of inactivity."""
        store = SessionStore(timeout_minutes=15)
        session = store.create_session(username="alice")
        session_id = session.session_id

        # Verify session is not expired initially
        assert not session.is_expired()
        assert session.is_active

        # Manually set last_activity to 14 minutes ago - should NOT be expired
        session.last_activity = datetime.now() - timedelta(minutes=14)
        assert not session.is_expired()

        # Set last_activity to 14 minutes 59 seconds ago - should NOT be expired (near boundary)
        session.last_activity = datetime.now() - timedelta(minutes=14, seconds=59)
        assert not session.is_expired()

        # Set last_activity to past 15 minutes - should be expired
        session.last_activity = datetime.now() - timedelta(minutes=15, seconds=1)
        assert session.is_expired()

        # Verify session is still in store but expired
        retrieved_session = store.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.is_expired()

    def test_activity_resets_timeout(self):
        """Test that updating activity resets the timeout timer."""
        store = SessionStore(timeout_minutes=15)
        session = store.create_session(username="bob")
        session_id = session.session_id

        # Set last_activity to 10 minutes ago
        old_activity = datetime.now() - timedelta(minutes=10)
        session.last_activity = old_activity

        # Update activity (simulate user interaction)
        session.update_activity()

        # Verify last_activity was updated
        assert session.last_activity > old_activity
        assert not session.is_expired()

        # Set last_activity to 14 minutes ago from NOW
        # Should NOT be expired
        session.last_activity = datetime.now() - timedelta(minutes=14)
        assert not session.is_expired()

        # Set last_activity to 15 minutes 1 second ago - should be expired
        session.last_activity = datetime.now() - timedelta(minutes=15, seconds=1)
        assert session.is_expired()

    def test_multiple_sessions_timeout_independently(self):
        """Test that multiple sessions timeout independently based on their own activity."""
        store = SessionStore(timeout_minutes=15)

        # Create three sessions
        session1 = store.create_session(username="alice")
        session1_id = session1.session_id

        session2 = store.create_session(username="bob")
        session2_id = session2.session_id

        session3 = store.create_session(username="charlie")
        session3_id = session3.session_id

        # Set different last_activity times for each session
        # Session 1: 16 minutes ago (expired)
        session1.last_activity = datetime.now() - timedelta(minutes=16)

        # Session 2: 10 minutes ago (not expired)
        session2.last_activity = datetime.now() - timedelta(minutes=10)

        # Session 3: 5 minutes ago (not expired)
        session3.last_activity = datetime.now() - timedelta(minutes=5)

        # Check expiration status
        assert session1.is_expired()  # 16 minutes > 15 minute timeout
        assert not session2.is_expired()  # 10 minutes < 15 minute timeout
        assert not session3.is_expired()  # 5 minutes < 15 minute timeout

        # Update activity on session3
        session3.update_activity()
        assert not session3.is_expired()  # Just updated, definitely not expired

        # Now make session2 expired
        session2.last_activity = datetime.now() - timedelta(minutes=15, seconds=1)
        assert session1.is_expired()  # Still expired
        assert session2.is_expired()  # Now expired too
        assert not session3.is_expired()  # Still active (just updated)


class TestSessionCleanup:
    """Test cleanup of expired sessions."""

    def test_cleanup_removes_expired_sessions(self):
        """Test that cleanup_expired_sessions removes only expired sessions."""
        store = SessionStore(timeout_minutes=15)

        # Create three sessions
        session1 = store.create_session(username="alice")
        session1_id = session1.session_id

        session2 = store.create_session(username="bob")
        session2_id = session2.session_id

        session3 = store.create_session(username="charlie")
        session3_id = session3.session_id

        # Verify all three sessions exist
        assert store.get_session(session1_id) is not None
        assert store.get_session(session2_id) is not None
        assert store.get_session(session3_id) is not None

        # Make session1 expired (16 minutes ago)
        session1.last_activity = datetime.now() - timedelta(minutes=16)

        # Session2 and session3 are still active (recent)
        # No need to set - they were just created

        # Run cleanup
        cleaned = store.cleanup_expired_sessions()

        # Should have cleaned up 1 session
        assert cleaned == 1

        # Session1 should be removed
        assert store.get_session(session1_id) is None

        # Sessions 2 and 3 should still exist
        assert store.get_session(session2_id) is not None
        assert store.get_session(session3_id) is not None

        # Make session2 expired
        session2.last_activity = datetime.now() - timedelta(minutes=16)

        # Run cleanup again
        cleaned = store.cleanup_expired_sessions()

        # Should have cleaned up 1 more session (session2)
        assert cleaned == 1

        # Sessions 1 and 2 should be gone
        assert store.get_session(session1_id) is None
        assert store.get_session(session2_id) is None

        # Session 3 should still exist
        assert store.get_session(session3_id) is not None


class TestTimeoutAccuracy:
    """Test that session timeout timing is accurate (SC-003)."""

    def test_timeout_accuracy_with_short_timeout(self):
        """
        Test that session timeout occurs within expected time window.

        SC-003 requires 15min±5s accuracy. This test validates the timeout mechanism
        using a shorter timeout period for practical testing (5 seconds with ±1s tolerance).
        The same mechanism applies to the production 15-minute timeout.
        """
        # Use a short timeout for testing (5 seconds)
        timeout_seconds = 5
        tolerance_seconds = 1  # ±1 second tolerance

        store = SessionStore(timeout_minutes=timeout_seconds / 60.0)  # Convert to minutes
        session = store.create_session(username="accuracy_test_user")

        # Record creation time
        start_time = time.time()

        # Wait for timeout to occur (poll every 0.1 seconds)
        max_wait = timeout_seconds + tolerance_seconds + 2  # Extra buffer to avoid infinite loop
        expired_time = None

        while (time.time() - start_time) < max_wait:
            if session.is_expired():
                expired_time = time.time()
                break
            time.sleep(0.1)

        # Verify session expired
        assert expired_time is not None, "Session did not expire within expected time window"

        # Calculate actual timeout duration
        actual_timeout = expired_time - start_time

        # Verify timeout accuracy: should be within timeout_seconds ± tolerance_seconds
        expected_min = timeout_seconds - tolerance_seconds
        expected_max = timeout_seconds + tolerance_seconds

        assert expected_min <= actual_timeout <= expected_max, \
            f"Timeout accuracy outside acceptable range: expected {timeout_seconds}±{tolerance_seconds}s, got {actual_timeout:.2f}s"

        # Additional verification: session should be marked as expired
        assert session.is_expired()
        assert session.is_active  # is_active flag is independent of expiration

    @pytest.mark.slow
    def test_production_timeout_accuracy(self):
        """
        Test that production 15-minute timeout is accurate (SC-003).

        This test validates the actual 15-minute timeout with ±5 second tolerance.
        Marked as @pytest.mark.slow because it takes ~15 minutes to run.

        Run with: pytest -v -m slow tests/chatbot/test_timeout.py
        """
        # Production timeout: 15 minutes
        timeout_minutes = 15
        tolerance_seconds = 5  # ±5 seconds as per SC-003

        store = SessionStore(timeout_minutes=timeout_minutes)
        session = store.create_session(username="production_accuracy_test")

        # Record creation time
        start_time = time.time()

        # Wait for timeout to occur (poll every 5 seconds to reduce CPU usage)
        max_wait_seconds = (timeout_minutes * 60) + tolerance_seconds + 10
        expired_time = None

        while (time.time() - start_time) < max_wait_seconds:
            if session.is_expired():
                expired_time = time.time()
                break
            time.sleep(5)  # Poll every 5 seconds

        # Verify session expired
        assert expired_time is not None, \
            "Session did not expire within expected 15-minute window"

        # Calculate actual timeout duration
        actual_timeout_seconds = expired_time - start_time
        expected_timeout_seconds = timeout_minutes * 60

        # Verify timeout accuracy: 15 minutes ± 5 seconds
        expected_min = expected_timeout_seconds - tolerance_seconds
        expected_max = expected_timeout_seconds + tolerance_seconds

        assert expected_min <= actual_timeout_seconds <= expected_max, \
            f"Production timeout accuracy outside SC-003 requirement: " \
            f"expected {timeout_minutes}min±{tolerance_seconds}s, " \
            f"got {actual_timeout_seconds:.1f}s ({actual_timeout_seconds/60:.2f}min)"

        # Verify session state
        assert session.is_expired()
        assert session.is_active  # is_active flag is independent of expiration
