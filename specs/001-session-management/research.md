# Phase 0: Research & Technical Decisions

**Feature**: Authenticated Session Management
**Date**: 2025-12-16

## Research Questions from Technical Context

### 1. Web Framework for Chatbot Service

**Decision**: FastAPI

**Rationale**:
- README.md mentions Python 3.11+ requirement
- FastAPI provides:
  - Built-in async/await support for LLM streaming responses
  - Easy HTTP header extraction via dependency injection
  - Session middleware support (Starlette sessions)
  - WebSocket support for real-time chat updates
  - Automatic OpenAPI documentation
  - High performance (ASGI-based)
- Compatible with existing containerization (Dockerfile, Podman/Docker)

**Alternatives Considered**:
- **Flask**: Simpler but lacks native async support, would need Flask-SocketIO for real-time features
- **Django**: Too heavyweight for this use case, adds unnecessary complexity
- **Starlette**: FastAPI is built on Starlette, using FastAPI gives higher-level abstractions

**Implementation Approach**:
- Use `fastapi.Request` to extract X-WEBAUTH-USER header
- Custom middleware for session management and timeout tracking
- In-memory session store (Python dict with threading locks)
- Background tasks for session cleanup

### 2. MCP SDK and Client Implementation

**Decision**: FastMCP (Python MCP SDK)

**Rationale**:
- README.md documentation references FastMCP: https://gofastmcp.com/
- FastMCP provides both MCP server and client capabilities
- Thruk MCP service likely already uses FastMCP for server implementation
- Supports custom parameters in tool invocations (username parameter)
- Built on modern Python async patterns

**MCP Tool Parameter Strategy**:
```python
# Chatbot invokes Thruk MCP tools with username
result = await mcp_client.call_tool(
    "thruk_list_hosts",
    {"username": session.username}
)
```

**Alternatives Considered**:
- **Anthropic MCP SDK**: Official but may have different API patterns
- **Custom MCP client**: Unnecessary reinvention, FastMCP is battle-tested

**Connection Management**:
- MCP client connection established per session
- Connection stored in session object
- Closed during session cleanup (FR-010)

### 3. Testing Framework

**Decision**: pytest with pytest-asyncio and freezegun

**Rationale**:
- **pytest**: Industry standard for Python testing, clean syntax, powerful fixtures
- **pytest-asyncio**: Native async/await test support for FastAPI and MCP async code
- **pytest-mock**: Simplified mocking (wraps unittest.mock)
- **freezegun**: Time manipulation for testing 15-minute timeout without waiting
- **httpx**: Async HTTP client for testing FastAPI applications

**Test Strategy**:
```python
# Example timeout test with time mocking
@pytest.mark.asyncio
async def test_session_timeout():
    with freeze_time("2025-12-16 10:00:00") as frozen_time:
        session = create_session("testuser")
        frozen_time.tick(delta=timedelta(minutes=15))
        assert session.is_expired()
```

**Alternatives Considered**:
- **unittest**: Standard library but verbose, lacks pytest's fixture system
- **timemachine**: Alternative to freezegun, less mature
- **asynctest**: Deprecated in favor of pytest-asyncio

### 4. Session Storage Pattern

**Decision**: In-memory dictionary with threading.Lock

**Rationale**:
- Spec assumption: single-instance deployment (no distributed sessions)
- Python dict provides O(1) session lookups by session ID
- threading.Lock ensures thread-safe concurrent session access
- No external dependencies (Redis, database) needed

**Data Structure**:
```python
sessions: Dict[str, UserSession] = {}
session_lock = threading.Lock()

class UserSession:
    username: str
    created_at: datetime
    last_activity: datetime
    mcp_connection: MCPClient
    llm_connection: LLMClient
    conversation_history: List[Message]
```

**Cleanup Strategy**:
- Background task runs every 60 seconds
- Checks all sessions for `last_activity > 15 minutes`
- Calls cleanup method: close connections, remove from dict

**Alternatives Considered**:
- **Redis**: Overkill for single-instance, adds deployment complexity
- **SQLite**: Persistence not needed (browser refresh = new session per spec)
- **asyncio.Lock**: Would require all session access to be async, threading.Lock is simpler

## Resolved Technical Context Updates

**Primary Dependencies**:
- FastAPI (web framework)
- FastMCP (MCP client SDK)
- uvicorn (ASGI server)
- Jinja2 (HTML templating)

**Testing**:
- pytest
- pytest-asyncio
- pytest-mock
- freezegun
- httpx (for FastAPI testing)

## Implementation Notes

### Environment Variables to Add (.env.example)

```bash
# Session Management
SESSION_TIMEOUT_MINUTES=15
DEFAULT_USERNAME=chatuser
SESSION_CLEANUP_INTERVAL_SECONDS=60
```

### MCP Tool Schema Extension (Thruk MCP Server)

All existing tools need to accept optional `username` parameter:

```python
@mcp.tool()
async def thruk_list_hosts(username: str = "chatuser"):
    """List hosts visible to the specified user."""
    # Pass username to Thruk API for authorization
```

### Security Considerations

- X-WEBAUTH-USER header trusted only when from Apache (not user-controllable)
- Session IDs generated with secrets.token_urlsafe(32)
- No session data persisted to disk (in-memory only)
- Username not considered sensitive (visible in UI)

## Next Phase: Design

With these decisions, Phase 1 will produce:
- `data-model.md`: UserSession, SessionState entities
- `contracts/`: Session management API endpoints (create, heartbeat, cleanup)
- `quickstart.md`: Local development setup with session testing
