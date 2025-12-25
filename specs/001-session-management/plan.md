# Implementation Plan: Authenticated Session Management

**Branch**: `001-session-management` | **Date**: 2025-12-16 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-session-management/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Add authenticated session management to the Chatbot Service with Apache reverse proxy integration. Users authenticate via X-WEBAUTH-USER header (defaulting to "chatuser" for standalone mode). Each user receives an isolated session with 15-minute inactivity timeout, UI-based username display, and complete resource cleanup on expiration. Username propagates to Thruk MCP server for authorization-aware Thruk API calls respecting per-user privileges.

## Technical Context

**Language/Version**: Python 3.11+ (per README.md prerequisites)
**Primary Dependencies**: FastAPI (web framework), FastMCP (MCP SDK), uvicorn (ASGI server), Jinja2 (templates)
**Storage**: In-memory session storage (Python dict with threading.Lock, single instance)
**Testing**: pytest with pytest-asyncio, pytest-mock, freezegun (time mocking), httpx (FastAPI testing)
**Target Platform**: Linux server (containerized with Podman/Docker, Kubernetes)
**Project Type**: Web application (Chatbot Service + Thruk MCP Service)
**Performance Goals**: 50+ concurrent sessions, <1s username display, 15min±5s timeout accuracy
**Constraints**: Session timeout 15 minutes, resource cleanup within 30s, single-instance deployment
**Scale/Scope**: Chatbot Service modifications only (session management layer)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Service Separation (Principle I)**
- [x] Changes maintain clear separation between Chatbot and Thruk MCP services
  - Session management is Chatbot-only, MCP server remains stateless
- [x] Services communicate only via HTTP/Streamable HTTP using MCP protocol
  - Username passed via MCP tool invocation parameters
- [x] Each service remains independently deployable and testable
  - Chatbot changes don't affect MCP server deployment

**MCP Protocol Compliance (Principle II)**
- [x] All MCP tool schemas follow Model Context Protocol specification
  - Existing MCP tools extended with username parameter (FR-015)
- [x] Tool implementations include proper error responses and capability negotiation
  - Session timeout errors handled before MCP invocation
- [x] Changes are compatible with Claude Code, Claude Desktop, and other MCP clients
  - Username parameter is optional/backward compatible

**Configuration-Driven Integration (Principle III)**
- [x] No hardcoded URLs, API keys, or deployment assumptions in code
  - Default username "chatuser" is configurable via environment variable
- [x] All external integrations configured via environment variables
  - Session timeout duration, default username externalizable
- [x] .env.example documentation is complete and synchronized
  - Will add session-related config variables

**Containerization Standards (Principle IV)**
- [x] Dockerfiles follow best practices (minimal base, non-root users, health checks)
  - Existing Dockerfiles meet standards, no changes needed
- [x] Services deployable via Docker Compose (dev) and Kubernetes (production)
  - Session management works in both environments
- [x] Resource limits (CPU, memory) are configurable
  - In-memory session storage respects container limits

**Error Resilience & Observability (Principle V)**
- [x] Inter-service communication handles network failures gracefully
  - Session cleanup closes connections properly on timeout
- [x] Structured logging (JSON format) implemented for all services
  - Session lifecycle events logged (creation, timeout, cleanup)
- [x] Sensitive data (API keys, credentials) redacted from logs and errors
  - Username is not sensitive; no credentials in session data

**Pre-Research Evaluation**: ✅ PASSED - All constitutional requirements met

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
chatbot/                        # Chatbot Service (session management implementation here)
├── chatbot.py                 # Main application (add session middleware)
├── session_manager.py         # NEW: Session management module
├── chatbot.json               # MCP configuration
├── Dockerfile                 # Container image (no changes)
├── requirements.txt           # Dependencies (add session libs)
└── templates/                 # NEW: HTML templates
    └── index.html             # Web UI with username display

thruk_mcp/                     # Thruk MCP Service (minimal changes)
├── thruk_mcp.py              # MCP server (add username parameter to tools)
├── Dockerfile                # Container image (no changes)
└── requirements.txt          # Dependencies (no changes)

tests/                         # NEW: Test suite
├── chatbot/
│   ├── test_session_manager.py
│   ├── test_timeout.py
│   └── test_cleanup.py
└── integration/
    └── test_username_propagation.py

.env.example                   # Update with session config variables
docker-compose-full.yml        # No changes needed
kubernetes-deployment.yaml     # No changes needed
```

**Structure Decision**: Web application with two services. Session management implemented entirely in `chatbot/` directory. The `chatbot.py` main application will be extended with session middleware, a new `session_manager.py` module will handle session lifecycle, and HTML templates will display username. Thruk MCP service (`thruk_mcp/`) receives minimal changes to accept username parameters in existing MCP tools.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No constitution violations. All checks passed.

## Post-Design Constitution Re-evaluation

*Re-check after Phase 1 design complete.*

**Service Separation (Principle I)**: ✅ PASSED
- Design maintains strict separation: `chatbot/session_manager.py` vs `thruk_mcp/*.py`
- MCP username parameter is optional/backward compatible
- No shared state between services

**MCP Protocol Compliance (Principle II)**: ✅ PASSED
- Username parameter added to all tools via FastMCP SDK
- Session timeout handled before MCP invocation (no protocol violations)
- Backward compatible with existing MCP clients

**Configuration-Driven Integration (Principle III)**: ✅ PASSED
- `.env` variables: SESSION_TIMEOUT_MINUTES, DEFAULT_USERNAME, SESSION_CLEANUP_INTERVAL_SECONDS
- No hardcoded values in design
- Quickstart.md documents all configuration

**Containerization Standards (Principle IV)**: ✅ PASSED
- Session management works with existing Dockerfiles (no changes)
- In-memory storage compatible with container resource limits
- Deployable via Docker Compose and Kubernetes

**Error Resilience & Observability (Principle V)**: ✅ PASSED
- Session cleanup explicitly closes MCP and LLM connections
- Data model includes logging points for session lifecycle
- Username logged for audit trail (not sensitive data)

**Final Evaluation**: ✅ ALL CONSTITUTIONAL REQUIREMENTS MET

## Phase 0: Research Artifacts

**Created**: `research.md`

**Key Decisions**:
- Web framework: FastAPI
- MCP SDK: FastMCP
- Testing: pytest with pytest-asyncio, freezegun
- Session storage: In-memory Python dict with threading.Lock

## Phase 1: Design Artifacts

**Created**:
- `data-model.md`: UserSession, SessionStore, Message entities
- `contracts/session-api.yaml`: OpenAPI spec for session management endpoints
- `contracts/thruk-mcp-extension.md`: Username parameter extension for all MCP tools
- `quickstart.md`: Local development setup guide

**Architecture**:
- Chatbot Service: FastAPI app with session middleware
- Session Manager: `session_manager.py` module (new)
- MCP Tools: Extended with optional `username` parameter
- HTML Templates: `templates/index.html` for username display

## Next Phase: Task Generation

Run `/speckit.tasks` to generate implementation tasks based on:
- User stories (P1: auth/init, P2: timeout, P3: cleanup)
- Data model entities
- API contracts
- Constitution compliance

**Implementation order**: P1 (MVP) → P2 (security) → P3 (production-ready)
