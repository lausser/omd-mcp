# Feature Specification: Authenticated Session Management

**Feature Branch**: `001-session-management`
**Created**: 2025-12-16
**Status**: Draft
**Input**: User description: "Add authenticated session management with Apache reverse proxy integration. Users authenticate via Apache basic auth (X-WEBAUTH-USER header). For standalone/test deployments without Apache, default to username "chatuser" when X-WEBAUTH-USER is not present. Each user gets an isolated session with their username displayed in the UI. Sessions timeout after 15 minutes of inactivity, disabling UI controls and showing "session has ended after inactivity" message, with full session cleanup. User context passed to Thruk MCP for authorization-aware API calls respecting per-user privileges."

## System Context

This feature applies to the **Chatbot Service** (not the Thruk MCP server). The architecture consists of:

**Chatbot Service**:
- Web UI for user interaction
- Manages user sessions (this feature)
- Communicates with LLM APIs (OpenAI, Gemini, Anthropic)
- Invokes Thruk MCP server tools when instructed by LLM
- Receives X-WEBAUTH-USER header from Apache proxy

**Thruk MCP Server**:
- Exposes Thruk API functionality as MCP tools
- Listing tools: hosts, services, hostgroups, servicegroups, downtimes (with comments)
- Downtime tools: schedule downtime for hosts (with/without services), services, hostgroup hosts, servicegroup services
- Receives username from Chatbot with each tool invocation
- Uses username for authorization when calling Thruk API

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
