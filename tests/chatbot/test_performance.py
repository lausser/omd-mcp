"""
Performance tests for session management

Tests performance requirements:
- SC-001: Username display within 1 second
- SC-002: Support 50+ concurrent sessions
- SC-004: Resource cleanup within 30 seconds
"""

import pytest
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from chatbot.session_manager import UserSession, SessionStore, Message


class TestConcurrentSessions:
    """Test concurrent session performance (SC-002)."""

    def test_50_concurrent_sessions(self):
        """
        Test that system supports at least 50 concurrent sessions.

        SC-002: System supports at least 50 concurrent user sessions
        without performance degradation.
        """
        num_sessions = 50
        store = SessionStore(timeout_minutes=15)

        # Measure time to create 50 sessions
        start_time = time.time()

        sessions = []
        for i in range(num_sessions):
            session = store.create_session(username=f"user_{i}")
            sessions.append(session)

        creation_time = time.time() - start_time

        # Verify all sessions were created
        assert len(sessions) == num_sessions
        assert len(store.sessions) == num_sessions

        # Verify all sessions are active and not expired
        for session in sessions:
            assert session.is_active
            assert not session.is_expired()

        # Verify each session is retrievable and has correct username
        for i, session in enumerate(sessions):
            retrieved = store.get_session(session.session_id)
            assert retrieved is not None
            assert retrieved.username == f"user_{i}"
            assert retrieved.session_id == session.session_id

        # Performance check: Creating 50 sessions should be fast
        # Allow 5 seconds for 50 sessions (0.1s per session average)
        assert creation_time < 5.0, \
            f"Creating {num_sessions} sessions took {creation_time:.2f}s (expected <5s)"

        # Test concurrent session updates (simulate activity)
        start_time = time.time()

        for session in sessions:
            session.update_activity()
            session.conversation_history.append(
                Message("user", f"Test message from {session.username}")
            )

        update_time = time.time() - start_time

        # Verify all sessions have messages
        for session in sessions:
            assert len(session.conversation_history) == 1
            assert session.conversation_history[0].role == "user"

        # Performance check: Updating 50 sessions should be fast
        assert update_time < 2.0, \
            f"Updating {num_sessions} sessions took {update_time:.2f}s (expected <2s)"

        print(f"\n✅ Concurrent session performance:")
        print(f"   - Created {num_sessions} sessions in {creation_time:.3f}s")
        print(f"   - Updated {num_sessions} sessions in {update_time:.3f}s")
        print(f"   - Average creation time: {creation_time/num_sessions*1000:.1f}ms per session")
        print(f"   - Average update time: {update_time/num_sessions*1000:.1f}ms per session")

    def test_concurrent_session_isolation(self):
        """
        Test that concurrent sessions remain isolated from each other.

        Verifies that operations on one session don't affect others.
        """
        num_sessions = 50
        store = SessionStore(timeout_minutes=15)

        # Create 50 sessions with different conversation histories
        sessions = [store.create_session(username=f"user_{i}") for i in range(num_sessions)]

        # Add different numbers of messages to each session
        for i, session in enumerate(sessions):
            for j in range(i % 5):  # 0-4 messages per session
                session.conversation_history.append(
                    Message("user", f"Message {j} from {session.username}")
                )

        # Verify each session has the correct number of messages
        for i, session in enumerate(sessions):
            expected_messages = i % 5
            assert len(session.conversation_history) == expected_messages

            # Verify message content
            for j, msg in enumerate(session.conversation_history):
                assert msg.role == "user"
                assert f"Message {j} from user_{i}" in msg.content

        # Verify no cross-contamination between sessions
        for i in range(len(sessions)):
            for j in range(len(sessions)):
                if i != j:
                    session_i = sessions[i]
                    session_j = sessions[j]
                    # Verify session IDs are unique
                    assert session_i.session_id != session_j.session_id
                    # Verify usernames are different
                    assert session_i.username != session_j.username


class TestUsernameDisplayPerformance:
    """Test username display performance (SC-001)."""

    def test_username_display_performance(self):
        """
        Test that username is available within 1 second.

        SC-001: Each authenticated user can see their username displayed
        in the chatbot interface within 1 second of page load.
        """
        store = SessionStore(timeout_minutes=15)

        # Measure time to create session and retrieve username
        start_time = time.time()

        session = store.create_session(username="display_test_user")
        username = session.username
        session_id = session.session_id

        # Retrieve session (simulating what happens on page load)
        retrieved_session = store.get_session(session_id)
        retrieved_username = retrieved_session.username

        elapsed_time = time.time() - start_time

        # Verify username is correct
        assert username == "display_test_user"
        assert retrieved_username == "display_test_user"

        # Performance requirement: <1 second
        assert elapsed_time < 1.0, \
            f"Username retrieval took {elapsed_time:.3f}s (expected <1s per SC-001)"

        print(f"\n✅ Username display performance:")
        print(f"   - Username available in {elapsed_time*1000:.1f}ms (expected <1000ms)")

    def test_multiple_username_retrievals(self):
        """
        Test that username retrieval is fast for multiple concurrent users.

        Simulates multiple users loading the page simultaneously.
        """
        num_users = 20
        store = SessionStore(timeout_minutes=15)

        # Create sessions for multiple users
        sessions = [
            store.create_session(username=f"user_{i}")
            for i in range(num_users)
        ]

        # Measure time to retrieve all usernames
        start_time = time.time()

        usernames = []
        for session in sessions:
            retrieved = store.get_session(session.session_id)
            usernames.append(retrieved.username)

        elapsed_time = time.time() - start_time

        # Verify all usernames retrieved correctly
        assert len(usernames) == num_users
        for i, username in enumerate(usernames):
            assert username == f"user_{i}"

        # Each user should get their username in <1s (SC-001)
        # For 20 users, allow proportionally more time, but average should be fast
        avg_time_per_user = elapsed_time / num_users
        assert avg_time_per_user < 0.1, \
            f"Average username retrieval: {avg_time_per_user*1000:.1f}ms (expected <100ms)"

        print(f"\n✅ Multiple username retrieval performance:")
        print(f"   - Retrieved {num_users} usernames in {elapsed_time*1000:.1f}ms")
        print(f"   - Average: {avg_time_per_user*1000:.1f}ms per user")


class TestResourceCleanupPerformance:
    """Test resource cleanup performance (SC-004)."""

    def test_resource_cleanup_performance(self):
        """
        Test that expired sessions release resources within 30 seconds.

        SC-004: Timed-out sessions release all resources (connections, memory)
        within 30 seconds of timeout.
        """
        # Use a very short timeout for testing (2 seconds)
        timeout_seconds = 2
        store = SessionStore(timeout_minutes=timeout_seconds / 60.0)

        # Create multiple sessions with mock resources
        num_sessions = 10
        sessions = []

        for i in range(num_sessions):
            session = store.create_session(username=f"cleanup_user_{i}")
            # Simulate resource allocation
            session.mcp_connection = f"mock_mcp_connection_{i}"
            session.llm_connection = f"mock_llm_connection_{i}"
            session.conversation_history.append(Message("user", f"Test message {i}"))
            sessions.append(session)

        # Verify all sessions have resources
        for session in sessions:
            assert session.mcp_connection is not None
            assert session.llm_connection is not None
            assert len(session.conversation_history) > 0

        # Record when sessions should expire
        # (they just got created, so they'll expire in timeout_seconds)
        # Make them expired by manipulating last_activity
        for session in sessions:
            session.last_activity = datetime.now() - timedelta(seconds=timeout_seconds + 1)

        # Verify all sessions are now expired
        for session in sessions:
            assert session.is_expired()

        # Measure time to cleanup expired sessions
        cleanup_start = time.time()

        cleaned_count = store.cleanup_expired_sessions()

        cleanup_time = time.time() - cleanup_start

        # Verify all sessions were cleaned up
        assert cleaned_count == num_sessions

        # Verify sessions are removed from store
        for session in sessions:
            assert store.get_session(session.session_id) is None

        # Performance requirement: cleanup within 30 seconds (SC-004)
        # For 10 sessions, should be much faster
        assert cleanup_time < 30.0, \
            f"Cleanup of {num_sessions} sessions took {cleanup_time:.2f}s (expected <30s per SC-004)"

        # In practice, cleanup should be very fast for small numbers
        assert cleanup_time < 1.0, \
            f"Cleanup of {num_sessions} sessions took {cleanup_time:.2f}s (expected <1s for this test)"

        print(f"\n✅ Resource cleanup performance:")
        print(f"   - Cleaned {num_sessions} expired sessions in {cleanup_time*1000:.1f}ms")
        print(f"   - Average: {cleanup_time/num_sessions*1000:.1f}ms per session")

    @pytest.mark.slow
    def test_large_scale_cleanup_performance(self):
        """
        Test cleanup performance with many sessions (stress test).

        Validates that cleanup scales well with larger numbers of sessions.
        """
        # Use a very short timeout for testing (1 second)
        timeout_seconds = 1
        store = SessionStore(timeout_minutes=timeout_seconds / 60.0)

        # Create 100 sessions
        num_sessions = 100
        sessions = []

        for i in range(num_sessions):
            session = store.create_session(username=f"stress_user_{i}")
            session.mcp_connection = f"mock_mcp_{i}"
            session.llm_connection = f"mock_llm_{i}"
            # Add some conversation history
            for j in range(5):
                session.conversation_history.append(
                    Message("user" if j % 2 == 0 else "assistant", f"Message {j}")
                )
            sessions.append(session)

        # Make all sessions expired
        for session in sessions:
            session.last_activity = datetime.now() - timedelta(seconds=timeout_seconds + 1)

        # Measure cleanup time
        cleanup_start = time.time()
        cleaned_count = store.cleanup_expired_sessions()
        cleanup_time = time.time() - cleanup_start

        # Verify all cleaned up
        assert cleaned_count == num_sessions

        # Should still be well under 30 seconds even for 100 sessions
        assert cleanup_time < 30.0, \
            f"Cleanup of {num_sessions} sessions took {cleanup_time:.2f}s (SC-004 requires <30s)"

        # Should be much faster in practice
        assert cleanup_time < 5.0, \
            f"Cleanup of {num_sessions} sessions took {cleanup_time:.2f}s (expected <5s)"

        print(f"\n✅ Large-scale cleanup performance:")
        print(f"   - Cleaned {num_sessions} sessions in {cleanup_time*1000:.1f}ms")
        print(f"   - Average: {cleanup_time/num_sessions*1000:.2f}ms per session")
        print(f"   - Well within SC-004 requirement of 30s")
