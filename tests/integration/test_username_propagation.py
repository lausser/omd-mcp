"""
Integration tests for username propagation to MCP tools.

Tests that username from session is correctly passed to Thruk MCP server.
"""

import pytest
from chatbot.session_manager import SessionStore


class TestUsernamePropagation:
    """Test that username is passed to MCP tools."""

    def test_username_passed_to_mcp_tools(self):
        """
        Test that authenticated username is included when invoking MCP tools.

        This is a placeholder test that will be fully implemented when
        MCP client integration is added to chatbot.py.
        """
        store = SessionStore()
        session = store.create_session(username="alice")

        # Verify session has correct username
        assert session.username == "alice"

        # TODO: When MCP client is integrated:
        # 1. Mock MCP tool invocation
        # 2. Verify tool is called with username parameter
        # 3. Assert tool_call.parameters["username"] == "alice"

        # Placeholder assertion for now
        assert session.username is not None
        assert len(session.username) > 0

    def test_default_username_propagation(self):
        """Test that default 'chatuser' is used in standalone mode."""
        store = SessionStore()
        session = store.create_session(username="chatuser")

        assert session.username == "chatuser"

        # TODO: Verify MCP tools receive "chatuser" when no auth header present
