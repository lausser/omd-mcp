# Feature Specification: Authenticated Session Management

**Feature Branch**: `001-session-management`
**Created**: 2025-12-16
**Last Updated**: 2026-01-22
**Status**: Implemented
**Input**: User description: "Add authenticated session management with Apache reverse proxy integration. Users authenticate via Apache basic auth (X-WEBAUTH-USER header). For standalone/test deployments without Apache, default to username "chatuser" when X-WEBAUTH-USER is not present. Each user gets an isolated session with their username displayed in the UI. Sessions timeout after 15 minutes of inactivity, disabling UI controls and showing "session has ended after inactivity" message, with full session cleanup. User context passed to Thruk MCP for authorization-aware API calls respecting per-user privileges."

## Implementation Status: COMPLETE ✓

All features from this specification have been implemented and tested.

### Completed Features

| Requirement | Status | Location |
|-------------|--------|----------|
| FR-001: X-WEBAUTH-USER header extraction | ✓ | chatbot.py:218 |
| FR-002: Default username "chatuser" | ✓ | chatbot.py:218 |
| FR-003: Isolated sessions per user | ✓ | session_manager.py |
| FR-004: Username displayed in UI | ✓ | templates/index.html |
| FR-005: Username passed to Thruk MCP | ✓ | chatbot.py:880, thruk_mcp.py:194-195 |
| FR-006: Activity timestamp tracking | ✓ | session_manager.py:88 |
| FR-007: 15-minute session timeout | ✓ | session_manager.py:156 |
| FR-008: Disable submit on timeout | ✓ | templates/index.html:95 |
| FR-009: Timeout message display | ✓ | templates/index.html:112 |
| FR-010: Close MCP connections on timeout | ✓ | chatbot.py:1004-1007 |
| FR-011: Close LLM connections on timeout | ✓ | session cleanup |
| FR-012: Discard session state on timeout | ✓ | session_manager.py:172-176 |
| FR-013: Reset timer on interaction | ✓ | templates/index.html:247 |
| FR-014: Session isolation | ✓ | session_manager.py:47-52 |
| FR-015: MCP accepts username parameter | ✓ | thruk_mcp.py (all tools) |
| FR-016: Username in Thruk API calls | ✓ | thruk_mcp.py:194-195 |
| FR-017: Per-user authorization | ✓ | Thruk secret.key auth |

## Additional Implemented Features (Beyond Original Scope)

### LLM Provider Support

- **OpenAI Provider**: Full support with configurable model (default: gpt-4o)
- **Google Gemini Provider**: Full support with automatic function calling (default: gemini-2.5-flash)
- **Environment-based selection**: `LLM_PROVIDER=openai|gemini`
- **Vertex AI enterprise support**: `GEMINI_VERTEXAI=true`

### Thruk MCP Tools Implemented

| Tool | Purpose |
|------|---------|
| `thruk_list_hosts` | List all monitored hosts with status |
| `thruk_list_services` | List services for host(s) |
| `thruk_list_hostgroups` | List all host groups |
| `thruk_get_hostgroup` | Get details for specific hostgroup |
| `thruk_list_hostgroup_hosts` | List hosts belonging to a hostgroup |
| `thruk_list_servicegroups` | List all service groups |
| `thruk_list_downtimes` | List active downtimes |
| `thruk_list_comments` | List comments |
| `thruk_schedule_host_downtime` | Schedule host downtime |
| `thruk_schedule_service_downtime` | Schedule service downtime |
| `thruk_schedule_hostgroup_downtime` | Schedule downtime for all hosts in a hostgroup |
| `thruk_schedule_servicegroup_downtime` | Placeholder for future |

### Downtime Workflow Features

- **Strict 3-step confirmation workflow**: Confirm → Wait for "yes" → Execute immediately
- **Hostgroup downtime support**: Shows member hosts before confirmation
- **Flexible duration format**: `10`, `10m`, `+1h`, `2026-01-22 15:00`
- **Automatic time parsing**: Handles relative and absolute times
- **Comment support**: User-provided downtime reason

### Infrastructure Fixes

1. **Apache Configuration**: Removed deprecated `<IfFile>` directives for Apache 2.4+ compatibility
2. **OMD Init Script**: Proper start/stop/restart/status handlers matching OMD patterns
3. **Python Dependencies**: Updated for Python 3.11+ (fastapi, uvicorn, pydantic v2)
4. **OMD Path Resolution**: Correct `$OMD_ROOT/lib/python/` paths for MCP subprocess
5. **Session Heartbeat**: Dynamic interval (50% of timeout) prevents premature expiration
6. **Page Visibility API**: Prevents browser tab throttling from killing heartbeats

### OMD Integration

- **Auto-configuration**: THRUK_BASE_URL, THRUK_API_KEY auto-loaded from OMD environment
- **Secret.key auth**: Uses Thruk's secret.key for multi-user authorization
- **SSL handling**: THRUK_VERIFY_SSL configurable (default: false in OMD)
- **Container deployment**: Multi-stage Docker builds with non-root users
- **Ansible deployment**: Full install-all.yml for automated OMD deployment

## System Context

This feature applies to the **Chatbot Service** (not the Thruk MCP server). The architecture consists of:

**Chatbot Service**:
- Web UI for user interaction
- Manages user sessions
- Communicates with LLM APIs (OpenAI, Gemini)
- Invokes Thruk MCP server tools when instructed by LLM
- Receives X-WEBAUTH-USER header from Apache proxy

**Thruk MCP Server**:
- Exposes Thruk API functionality as MCP tools (stdio transport)
- Receives username from Chatbot with each tool invocation
- Uses username for authorization via X-Thruk-Auth-User header
- Auto-configures from OMD environment variables

**Data Flow**: User → Apache → Chatbot (session + username) → LLM API → Chatbot → Thruk MCP (username) → Thruk API (authorization)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - User Authentication and Session Initialization (Priority: P1)

As a monitoring operator, I need to authenticate and start a chatbot session so that I can interact with the Thruk monitoring system through natural language commands with my own privileges.

**Why this priority**: This is the foundation for all other functionality. Without user authentication and session initialization, no other features can work. This is the minimum viable product.

**Independent Test**: Can be fully tested by authenticating via Apache (or standalone mode), verifying the username appears in the UI, and confirming that a unique session is created for each user login.

**Acceptance Scenarios**:

1. **Given** the chatbot runs behind Apache with basic auth, **When** a user successfully authenticates, **Then** the chatbot receives the X-WEBAUTH-USER header and displays the authenticated username in the UI
2. **Given** the chatbot runs in standalone mode without Apache, **When** a user accesses the chatbot, **Then** the system defaults to username "chatuser" and displays it in the UI
3. **Given** two different users authenticate simultaneously, **When** each user interacts with the chatbot, **Then** each user has an isolated session with no data sharing between sessions
4. **Given** a user has an active session, **When** the user submits a query about Thruk resources, **Then** the user's identity is passed to Thruk MCP for authorization-aware API calls

---

### User Story 2 - Session Timeout Protection (Priority: P2)

As a system administrator, I need sessions to automatically expire after inactivity so that abandoned sessions don't consume resources or pose security risks.

**Why this priority**: While authentication is critical, automatic timeout is essential for security and resource management. This builds on the P1 foundation to add production-ready safeguards.

**Independent Test**: Can be tested by creating an active session, waiting 15 minutes without interaction, and verifying that the UI shows the timeout message and disables controls.

**Acceptance Scenarios**:

1. **Given** a user has an active session, **When** 15 minutes pass without any user interaction, **Then** all submit buttons are disabled and a "session has ended after inactivity" message is displayed
2. **Given** a user session has timed out, **When** the user attempts to submit a query, **Then** the system prevents the submission and maintains the timeout message
3. **Given** a user has an active session, **When** the user interacts with the chatbot within the 15-minute window, **Then** the inactivity timer resets and the session remains active
4. **Given** multiple users have concurrent sessions, **When** one user's session times out, **Then** other users' active sessions are unaffected

---

### User Story 3 - Resource Cleanup on Timeout (Priority: P3)

As a system administrator, I need session resources to be properly cleaned up on timeout so that the system doesn't leak connections or memory.

**Why this priority**: Resource cleanup is important for system stability but can be implemented after core functionality is working. This ensures the system is production-ready.

**Independent Test**: Can be tested by monitoring system resources (connections, memory) before and after session timeout, verifying that all connections to MCP and AI services are closed.

**Acceptance Scenarios**:

1. **Given** a user session times out after 15 minutes of inactivity, **When** the timeout occurs, **Then** all connections to the Thruk MCP service are closed and released
2. **Given** a user session times out after 15 minutes of inactivity, **When** the timeout occurs, **Then** all connections to the AI/LLM service are closed and released
3. **Given** a user session times out, **When** the cleanup process completes, **Then** all session state data in memory is discarded
4. **Given** multiple sessions timeout simultaneously, **When** cleanup occurs, **Then** the system processes all cleanups without errors or resource contention

---

### Edge Cases

- What happens when the X-WEBAUTH-USER header is present but empty?
- What happens when a user refreshes the browser during an active session?
- What happens if the Apache proxy becomes unavailable mid-session?
- What happens when a session times out while a query is being processed?
- What happens if cleanup fails for a timed-out session?
- What happens when a user tries to start a new session after timing out?
- What happens if the system clock changes during session timeout tracking?

## Requirements *(mandatory)*

### Functional Requirements

**Chatbot Service (Session Management)**:

- **FR-001**: Chatbot MUST extract username from X-WEBAUTH-USER HTTP header when present
- **FR-002**: Chatbot MUST default to username "chatuser" when X-WEBAUTH-USER header is absent or empty
- **FR-003**: Chatbot MUST create an isolated session for each unique user login
- **FR-004**: Chatbot MUST display the authenticated username prominently in the user interface
- **FR-005**: Chatbot MUST include the authenticated username when invoking Thruk MCP server tools
- **FR-006**: Chatbot MUST track user interaction activity timestamps for each session
- **FR-007**: Chatbot MUST expire sessions after 15 minutes of inactivity
- **FR-008**: Chatbot MUST disable all submit buttons when a session times out
- **FR-009**: Chatbot MUST display "session has ended after inactivity" message when a session times out
- **FR-010**: Chatbot MUST close all connections to Thruk MCP service when a session times out
- **FR-011**: Chatbot MUST close all connections to LLM API service when a session times out
- **FR-012**: Chatbot MUST discard all session state data (conversation history, context) when a session times out
- **FR-013**: Chatbot MUST reset the inactivity timer when the user performs any interaction
- **FR-014**: Chatbot MUST maintain session isolation such that no user can access another user's session data

**Thruk MCP Server (Authorization)**:

- **FR-015**: Thruk MCP server MUST accept username parameter with each tool invocation
- **FR-016**: Thruk MCP server MUST use the provided username when making Thruk API calls for authorization enforcement
- **FR-017**: Thruk MCP server MUST respect per-user privileges defined in Thruk (which hosts/services/groups the user can view and manage)

### Key Entities

- **User Session**: Represents an authenticated user's interaction session with the chatbot. Contains username, creation timestamp, last activity timestamp, session state, active connections to MCP and AI services.
- **User Identity**: Represents the authenticated user extracted from X-WEBAUTH-USER or defaulted to "chatuser". Used for authorization in Thruk API calls.
- **Session State**: Represents the conversation history, context, and active requests for a user session. Includes message history, pending queries, and connection handles.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Each authenticated user can see their username displayed in the chatbot interface within 1 second of page load
- **SC-002**: System supports at least 50 concurrent user sessions without performance degradation
- **SC-003**: Sessions automatically timeout after exactly 15 minutes (±5 seconds) of inactivity
- **SC-004**: Timed-out sessions release all resources (connections, memory) within 30 seconds of timeout
- **SC-005**: User interactions reset the inactivity timer within 1 second
- **SC-006**: 100% of Thruk API calls include the authenticated username for proper authorization enforcement
- **SC-007**: Session isolation is complete - zero data leakage between different user sessions
- **SC-008**: System correctly handles both Apache-authenticated and standalone/test mode deployments without configuration changes

## Testing Environment

**Standalone MCP Server Testing**:
- Podman container running OMD (Open Monitoring Distribution)
- Container provides Thruk Web UI and API endpoint
- Pre-populated with sample host and service objects for testing
- Allows isolated testing of Thruk MCP server without full deployment
- Test users can be configured in OMD to verify per-user authorization

**Integration Testing**:
- Chatbot service connects to containerized Thruk MCP server
- Different test usernames can verify session isolation and authorization
- Timeout behavior can be tested without affecting production systems

## Assumptions

- Apache basic authentication is already configured and working for production deployments
- The X-WEBAUTH-USER header is trustworthy and set by Apache, not client-provided (not user-controllable)
- Thruk MCP server already has mechanisms to accept username and pass it to Thruk API for authorization
- Thruk API enforces per-user authorization based on the provided username
- "Inactivity" is defined as no user interactions (clicks, typing, submissions) - passive page viewing doesn't count as activity
- Session timeout is a hard cutoff - no grace period or warning before the 15-minute mark
- The Chatbot service runs as a single service instance (session state stored in-process, not distributed across multiple instances)
- Browser refresh creates a new session (no session persistence across page reloads)
- The Thruk MCP server is stateless - it does not manage sessions, only receives username per tool invocation
- Session management is exclusively a Chatbot service concern, not an MCP server concern

## Summary of Implemented Features (2026-01-22)

### Core Session Management ✓
- [x] Username extraction from X-WEBAUTH-USER header
- [x] Default username "chatuser" for standalone mode
- [x] Isolated sessions per user with unique session IDs
- [x] Username displayed in UI with last activity time
- [x] 15-minute inactivity timeout with auto-logout
- [x] Heartbeat mechanism (50% of timeout interval)
- [x] Page Visibility API prevents browser throttling issues

### Thruk Integration ✓
- [x] 14 MCP tools for monitoring operations
- [x] Host listing with status, groups, and state
- [x] Service listing with status
- [x] Hostgroup listing and membership queries
- [x] Downtime scheduling for hosts, services, and hostgroups
- [x] Downtime and comment listing
- [x] Per-user authorization via secret.key
- [x] Auto-configuration from OMD environment

### LLM Integration ✓
- [x] OpenAI provider with GPT-4o
- [x] Google Gemini provider with gemini-2.5-flash
- [x] Vertex AI enterprise support
- [x] Automatic function calling for tool invocation
- [x] Session state passed to Gemini SDK

### Infrastructure ✓
- [x] Apache 2.4+ compatible configuration
- [x] OMD init script with proper start/stop/restart
- [x] Python 3.11+ with FastAPI, uvicorn, Pydantic v2
- [x] Stdio-based MCP transport (no separate daemon)
- [x] Ansible deployment automation
- [x] Container builds with multi-stage Dockerfiles
- [x] Non-root container users for security

### UI/UX ✓
- [x] Clean chat interface with message history
- [x] Timeout warning with remaining time display
- [x] Disabled controls on session expiration
- [x] Error visibility for admin users (omdadmin)
- [x] Responsive design for monitoring workflows

## Commands Reference

### Development
```bash
# Local development
cd chatbot && python chatbot.py

# Container development
podman compose up -d
podman compose logs -f chatbot

# OMD deployment
cd /src/omd-mcp/ansible
ansible-playbook -i inventory install-all.yml
su - demo
omd restart chatbot
```

### Testing
```bash
pytest
pytest --cov=chatbot --cov=thruk_mcp
ruff check .
```
