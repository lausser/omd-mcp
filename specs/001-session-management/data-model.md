# Data Model: Authenticated Session Management

**Feature**: 001-session-management
**Created**: 2025-12-16

## Entities

### UserSession

Represents an authenticated user's interaction session with the chatbot.

**Attributes**:
- `session_id` (str): Unique session identifier (32-byte URL-safe token)
- `username` (str): Authenticated username from X-WEBAUTH-USER or default "chatuser"
- `created_at` (datetime): Timestamp when session was created
- `last_activity` (datetime): Timestamp of most recent user interaction
- `mcp_connection` (MCPClient | None): Active connection to Thruk MCP server
- `llm_connection` (LLMClient | None): Active connection to LLM API service
- `conversation_history` (List[Message]): Chat message history
- `is_active` (bool): Whether session is currently active (not timed out)

**Validation Rules**:
- `session_id` must be unique across all sessions
- `username` must be non-empty string (fallback to "chatuser" if empty/missing)
- `created_at` is immutable after creation
- `last_activity` must be >= `created_at`
- Session expires when `now() - last_activity > 15 minutes`

**State Transitions**:
```
CREATED → ACTIVE → TIMED_OUT → CLEANED_UP

CREATED: session_id generated, username set, connections null
ACTIVE: connections established, last_activity updates on interaction
TIMED_OUT: 15min inactivity, UI disabled, cleanup pending
CLEANED_UP: connections closed, removed from session store
```

**Methods**:
- `is_expired() -> bool`: Returns True if `now() - last_activity > 15min`
- `update_activity()`: Sets `last_activity = now()`, resets timeout
- `cleanup()`: Closes MCP and LLM connections, clears conversation history

### SessionStore

Global session storage and management.

**Attributes**:
- `sessions` (Dict[str, UserSession]): Session ID → UserSession mapping
- `lock` (threading.Lock): Thread-safe access to sessions dict
- `cleanup_interval_seconds` (int): Background cleanup task interval (default 60s)

**Methods**:
- `create_session(username: str) -> UserSession`: Creates new session with unique ID
- `get_session(session_id: str) -> UserSession | None`: Retrieves session by ID
- `update_activity(session_id: str)`: Updates last_activity timestamp
- `cleanup_expired_sessions()`: Background task to remove expired sessions
- `remove_session(session_id: str)`: Explicitly removes and cleans up session

### Message

Represents a single chat message in conversation history.

**Attributes**:
- `role` (Literal["user", "assistant", "system"]): Message sender role
- `content` (str): Message text content
- `timestamp` (datetime): When message was sent/received
- `metadata` (Dict[str, Any]): Optional metadata (MCP tool calls, errors, etc.)

**Validation Rules**:
- `role` must be one of: "user", "assistant", "system"
- `content` must be non-empty
- `timestamp` is immutable

## Relationships

```
SessionStore (1) ──── contains ──── (many) UserSession
UserSession (1) ──── has ──── (many) Message
UserSession (1) ──── may have ──── (0..1) MCPClient
UserSession (1) ──── may have ──── (0..1) LLMClient
```

## Data Flow

### Session Creation (FR-001, FR-002, FR-003)

```
1. HTTP Request arrives → Extract X-WEBAUTH-USER header
2. If header present and non-empty → username = header value
3. If header absent/empty → username = "chatuser"
4. SessionStore.create_session(username)
5. Generate session_id with secrets.token_urlsafe(32)
6. Create UserSession(session_id, username, now(), now(), [], None, None)
7. Store in sessions dict with lock
8. Return session_id to client (HTTP cookie or response)
```

### Activity Tracking (FR-006, FR-013)

```
1. User interaction event (click, type, submit)
2. Extract session_id from request (cookie/header)
3. SessionStore.get_session(session_id)
4. If session exists and not expired → session.update_activity()
5. Continue processing request
```

### Timeout & Cleanup (FR-007 through FR-012)

```
1. Background task runs every 60s
2. SessionStore.cleanup_expired_sessions()
3. For each session in sessions.values():
    a. If session.is_expired():
        - session.cleanup() → close MCP connection, close LLM connection
        - conversation_history.clear()
        - Remove from sessions dict
4. If session timed out during active request:
    - Return error response with timeout message
    - UI disables submit buttons, shows "session has ended after inactivity"
```

## Storage Constraints

**Memory Estimation** (50 concurrent sessions):
- UserSession object: ~1KB
- Conversation history (avg 50 messages): ~50KB
- MCP/LLM connections: ~10KB
- **Total per session**: ~61KB
- **50 sessions**: ~3MB (well within container limits)

**Thread Safety**:
- All access to `SessionStore.sessions` dict must acquire `lock`
- Read operations: `with lock: session = sessions.get(session_id)`
- Write operations: `with lock: sessions[session_id] = new_session`
- Cleanup: `with lock: del sessions[session_id]`

## Example Usage

```python
# Session creation
store = SessionStore()
session = store.create_session(username="alice")
print(f"Session ID: {session.session_id}")  # Returns: "Xy7k9Pm..."

# Activity tracking
@app.post("/chat")
async def chat(request: Request):
    session_id = request.cookies.get("session_id")
    session = store.get_session(session_id)

    if not session or session.is_expired():
        raise HTTPException(401, "Session expired")

    session.update_activity()  # Reset timeout
    # Process chat request...

# Cleanup (background task)
async def cleanup_loop():
    while True:
        await asyncio.sleep(60)
        store.cleanup_expired_sessions()
```
