# omd-mcp Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-12-31

## Active Technologies

- Python 3.11+ (per README.md prerequisites) + FastAPI (web framework), FastMCP (MCP SDK), uvicorn (ASGI server), Jinja2 (templates) (001-session-management)
- OpenAI Python SDK (openai>=1.10.0) for LLM integration (optional dependency)
- Google GenAI SDK (google-genai>=0.3.0) for Gemini LLM integration (optional dependency)

## Project Structure

```text
chatbot/             # Chatbot FastAPI service
├── __init__.py
├── chatbot.py      # Main application
├── session_manager.py
├── templates/
├── Containerfile   # Multi-stage container build
└── requirements.txt

thruk_mcp/          # FastMCP server for Thruk integration
├── __init__.py
├── thruk_mcp.py   # MCP server (placeholder)
├── Containerfile   # Multi-stage container build
└── requirements.txt

tests/              # Test suite
specs/              # Feature specifications
docker-compose.yml  # Container orchestration
```

## Commands

```bash
# Local development
cd chatbot && python chatbot.py
cd thruk_mcp && python thruk_mcp.py --listen 8001

# Container development
podman compose build
podman compose up -d
podman compose logs -f

# OMD deployment (Ansible)
cd ansible
ansible-playbook -i inventory install-all.yml         # Install both chatbot and thruk-mcp
ansible-playbook -i inventory install-chatbot.yml     # Install only chatbot

# Inside OMD site after Ansible deployment
omd config set THRUK_MCP on
omd config set CHATBOT on
cd $OMD_ROOT/etc/chatbot && ./install-deps.sh
omd restart chatbot
omd restart thruk-mcp

# Testing
pytest
pytest tests/chatbot/
pytest --cov=chatbot --cov=thruk_mcp

# Code quality
ruff check .
```

## Code Style

Python 3.11+ (per README.md prerequisites): Follow standard conventions

## Recent Changes

- 2026-01-05: Fixed OMD init script Gemini environment variable exports
  - **CRITICAL FIX**: Init script was sourcing chatbot.conf but not exporting Gemini variables
  - Added LLM_PROVIDER, GEMINI_API_KEY, GEMINI_BASE_URL, GEMINI_MODEL, GEMINI_VERTEXAI to exports
  - Fixed issue causing chatbot to default to "openai" even when LLM_PROVIDER="gemini" was configured
  - Chatbot now correctly initializes Gemini client when configured
- 2026-01-05: Added Google Gemini API as alternative LLM provider
  - Supports both cloud (Google AI Studio) and on-premise Gemini deployments
  - Configurable via LLM_PROVIDER environment variable (openai or gemini)
  - Uses Gemini's automatic_function_calling for tool orchestration
  - MCP session passed directly to Gemini SDK (not converted to OpenAI format)
  - Maintains all existing features (session management, error handling, admin debugging)
  - Default model: gemini-2.5-flash
  - Backward compatible: defaults to OpenAI if LLM_PROVIDER not set
- 2026-01-04: Admin Error Visibility
  - Added detailed error messages for user "omdadmin"
  - Admins see full error type, message, and Python traceback in chat UI
  - Regular users continue to see friendly "Sorry, an error occurred" message
  - Error messages with newlines displayed in monospace font with preserved formatting
  - Helps with debugging LLM API issues, rate limits, and configuration problems
- 2026-01-04: Stdio-based MCP Integration (Simplified Architecture)
  - **BREAKING CHANGE**: Converted Thruk MCP from daemon to stdio subprocess
  - Chatbot now spawns thruk_mcp.py on-demand using `PythonStdioTransport`
  - Removed separate thruk-mcp daemon, hooks (THRUK_MCP, THRUK_MCP_TCP_PORT), and init script
  - Simplified Ansible role to only install shared code (no daemon setup)
  - No TCP port needed - communication via stdin/stdout
  - Auto-configuration still works (OMD_ROOT, secret.key auto-loaded in subprocess)
  - Result: One daemon (chatbot) instead of two, simpler deployment
- 2026-01-04: MCP Client Integration - LLM Tool Calling
  - Fixed CallToolResult JSON serialization in chatbot.py (extract .data attribute)
  - LLM can now successfully call Thruk MCP tools and receive responses
  - Added robust handling for different FastMCP response formats
  - Tool results properly converted to JSON for OpenAI API
- 2026-01-05: Implemented Page Visibility API to prevent browser tab throttling
  - **CRITICAL FIX**: Browser throttles `setInterval` when tab is hidden/background, causing missed heartbeats
  - Added Page Visibility API listener to detect when tab becomes hidden/visible
  - Sends immediate heartbeat when tab becomes visible again (prevents session expiration)
  - Console logs when tab is hidden and how long it was hidden
  - Prevents session timeout when user switches to another tab temporarily
- 2026-01-05: Fixed session timeout heartbeat interval calculation
  - **CRITICAL FIX**: Heartbeat was hardcoded to 5 minutes, but session timeout could be less (e.g., 4 minutes)
  - Made heartbeat interval dynamic: calculated as 50% of session timeout
  - Frontend now receives `session_timeout_minutes` from backend
  - Console logs heartbeat interval for debugging
  - Example: 4-minute timeout → 2-minute heartbeat, 15-minute timeout → 7.5-minute heartbeat
- 2026-01-05: Fixed OMD path resolution and permissions for MCP subprocess
  - **CRITICAL FIX**: Changed path resolution to use `$OMD_ROOT/lib/python/thruk_mcp/` instead of relative paths
  - Fixed permission denied errors when spawning MCP subprocess (was trying to use version path)
  - OMD sites now correctly use site's lib/python instead of version's lib/python
  - Both `get_mcp_tools()` and `call_mcp_tool()` now detect OMD environment and use site paths
  - Added debug logging for MCP server path resolution
- 2026-01-05: Fixed Thruk MCP environment variable exports and URL configuration
  - **CRITICAL FIX**: Added `export THRUK_BASE_URL` to init script (was missing, causing 404 errors)
  - Fixed auto-configured THRUK_BASE_URL to include `/thruk` path: `http://127.0.0.1/{OMD_SITE}/thruk`
  - OMD init script now exports THRUK_API_KEY, THRUK_VERIFY_SSL, and THRUK_BASE_URL
  - Fixed empty bubble UI issue: `call_llm` now ensures `assistant_message` is never None
  - Added THRUK_VERIFY_SSL environment variable (default: false in OMD, true in containers)
  - Enhanced error handling for SSL certificate verification failures
  - Added helpful error messages suggesting to disable SSL verification for self-signed certificates
  - Added THRUK_VERIFY_SSL to startup logging
- 2026-01-05: Implemented complete Thruk API tool suite in MCP server
  - **Query Tools**: thruk_list_hosts, thruk_list_services, thruk_list_downtimes, thruk_list_comments
  - **Downtime Scheduling**: thruk_schedule_host_downtime, thruk_schedule_service_downtime, thruk_schedule_hostgroup_downtime
  - Added column selection for efficient data transfer (only essential fields)
  - Implemented sensitive data filtering (removes passwords, secrets, keys, tokens)
  - URL encoding for service descriptions with special characters
  - All tools validate THRUK_BASE_URL and THRUK_API_KEY before making requests
  - Relative time format support (start_time=now, end_time=+30m)
- 2026-01-05: Added pytest configuration and test suite improvements
  - Created pytest.ini to configure custom markers (slow, asyncio)
  - Slow tests now deselected by default (run with: pytest -m slow)
  - Test suite runtime reduced from 63+ minutes to ~10 seconds
  - 27 tests passing, 2 slow tests deselected, 1 async test skipped
  - Prevents long-running 15-minute timeout accuracy test from blocking CI/CD
- 2026-01-04: Thruk MCP integration with auto-configuration
  - Implemented full Thruk REST API integration in MCP server
  - Added auto-loading of Thruk secret.key in OMD environments (from $OMD_ROOT/var/thruk/secret.key)
  - Auto-configured THRUK_BASE_URL to http://127.0.0.1/$OMD_SITE/thruk
  - Multi-user support with per-user authorization via X-Thruk-Auth-User header
  - Comprehensive error handling (timeouts, connection failures, auth errors)
  - Added follow_redirects for HTTP→HTTPS redirects
  - Startup logging for Thruk MCP configuration status
- 2025-12-31: Completed session timeout handling with frontend detection and LLM integration
  - Enhanced frontend error handling for expired sessions (401 responses)
  - Fixed API path resolution for OMD deployment (dynamic base path)
  - Implemented OpenAI-compatible LLM integration with conversation history
  - Added graceful degradation when LLM not configured
  - Session timeout displays detailed message with idle time
  - Heartbeat mechanism stops on session expiration
- 2025-12-24: Initial session management implementation
  - Added Python 3.11+ (per README.md prerequisites) + FastAPI (web framework), FastMCP (MCP SDK), uvicorn (ASGI server), Jinja2 (templates)
  - Session isolation per user with X-WEBAUTH-USER header
  - Background cleanup of expired sessions

<!-- MANUAL ADDITIONS START -->

## Container Architecture

### Deployment
- Both services containerized with Podman/Docker
- Multi-stage builds for minimal image size
- Non-root users for security (chatbot: UID 1000, thruk-mcp: UID 1001)
- Internal network (`mcp-internal`) for service communication

### Images
- **Base**: python:3.11-slim (Debian-based)
- **Chatbot**: ~300MB final size
- **MCP Server**: ~267MB final size
- **Build**: Multi-stage with separate builder and runtime stages

### Configuration
- Environment variables from `.env` file
- Docker Compose orchestration
- Health checks for service readiness
- Resource limits (CPU/memory)

### Development Workflow
1. Make code changes
2. Rebuild: `podman compose build [service]`
3. Restart: `podman compose restart [service]`
4. View logs: `podman compose logs -f [service]`
5. Test: `pytest`

## OMD Integration Notes

### API Path Resolution
- Frontend uses dynamic base path detection: `window.location.pathname + '/api/'`
- Works with OMD site prefix: `/demo/chatbot/api/chat`
- Apache proxy configuration in `omd/templates/chatbot.apache.conf`

### Environment Variables
- Not loaded from `.env` file in OMD deployment
- Set manually before site starts or via OMD configuration (`$OMD_ROOT/etc/chatbot/chatbot.conf`)
- **LLM Provider Selection**:
  - `LLM_PROVIDER`: Provider to use - "openai" or "gemini" (default: openai)
- **OpenAI Configuration** (when LLM_PROVIDER=openai):
  - `OPENAI_API_KEY`: OpenAI or compatible API key (required)
  - `OPENAI_BASE_URL`: API endpoint (default: https://api.openai.com/v1)
  - `OPENAI_MODEL`: Model name (default: gpt-4)
- **Gemini Configuration** (when LLM_PROVIDER=gemini):
  - `GEMINI_API_KEY`: Gemini API key (required)
  - `GEMINI_BASE_URL`: API endpoint for on-premise (optional, empty = cloud)
  - `GEMINI_MODEL`: Model name (default: gemini-2.5-flash)
  - `GEMINI_VERTEXAI`: Enable Vertex AI protocol for enterprise (default: false)
- **Thruk MCP Configuration** (auto-configured in OMD):
  - `THRUK_API_KEY`: Auto-loads from `$OMD_ROOT/var/thruk/secret.key` if not set
  - `THRUK_BASE_URL`: Auto-configured to `http://127.0.0.1/$OMD_SITE` if not set
  - `THRUK_VERIFY_SSL`: SSL certificate verification (default: false in OMD for self-signed certs)
- **Session Management** (optional):
  - `SESSION_TIMEOUT_MINUTES`: Session timeout (default: 15)
  - `LOG_LEVEL`: Logging level (default: INFO)
  - `DEFAULT_USERNAME`: Default user when not authenticated (default: chatuser)

### Dependencies
- Core dependencies: `requirements.txt`
- Optional dependencies: `requirements-optional.txt` (LLM, MCP)
- Install script: `omd/install-deps.sh` handles optional dependencies

### File Locations in OMD Site
- Application: `$OMD_ROOT/lib/python/chatbot/`
- Templates: `$OMD_ROOT/share/chatbot/templates/`
- Logs: `$OMD_ROOT/var/log/chatbot.log`
- Configuration: `$OMD_ROOT/etc/chatbot/chatbot.conf`

<!-- MANUAL ADDITIONS END -->
