# MCP Chatbot with Thruk Integration

A chatbot application that integrates with Thruk monitoring system via Model Context Protocol (MCP).

## 🏗️ Architecture

- **Chatbot Service**: Web UI and LLM integration
- **Thruk MCP Service**: MCP server providing Thruk monitoring tools
- **Communication**: HTTP/Streamable HTTP between services

## ✨ Features

### Session Management
- **User Authentication**: X-WEBAUTH-USER header integration (Apache proxy) or standalone mode
- **Session Isolation**: Each user gets their own isolated session with conversation history
- **Automatic Timeout**: Configurable inactivity timeout (default: 15 minutes)
- **Timeout Detection**: Frontend detects expired sessions and displays clear notification
- **Resource Cleanup**: Automatic cleanup of expired sessions (MCP connections, LLM connections, conversation history)
- **Session Heartbeat**: Keep-alive mechanism prevents timeout during active use
- **Secure Cookies**: HTTP-only, SameSite=Lax session cookies

### LLM Integration
- **OpenAI-Compatible API**: Works with OpenAI, Anthropic Claude via proxy, or local models
- **Conversation History**: Full conversation context maintained per session
- **User Context**: Username passed to LLM for personalized responses
- **MCP Tool Access**: LLM can call Thruk MCP tools for real-time monitoring data
- **Function Calling**: Automatic tool execution with results passed back to LLM
- **Graceful Degradation**: Falls back to placeholder if LLM not configured
- **Configurable**: API endpoint, model, and credentials via environment variables

### UI Features
- **Modern Chat Interface**: Clean, responsive design with message history
- **Real-time Feedback**: Typing indicators, error messages, session status
- **Session Info Display**: Shows username and truncated session ID
- **Timeout Notifications**: Yellow banner and inline message when session expires
- **Auto-refresh Prompt**: Clear instructions when session timeout detected

## 📦 Deployment Options

This project supports three deployment modes:

1. **🐳 Containerized (Development)** - Run chatbot and MCP services in containers
   - Best for: Development, testing, standalone deployment
   - See: Quick Start section below

2. **🏢 OMD Integration - Site Level** - Deploy to individual OMD sites
   - Best for: Testing, single-site deployments
   - Quick start: [omd/QUICKSTART.md](omd/QUICKSTART.md)
   - Full guide: [omd/README.md](omd/README.md)

3. **🚀 OMD Integration - System Level (Recommended for Production)** - Install via Ansible
   - Best for: Production, multi-site OMD deployments
   - Install once, available to all sites
   - Managed via `omd config` commands
   - Quick start: [ansible/QUICKSTART.md](ansible/QUICKSTART.md)
   - Full guide: [ansible/README.md](ansible/README.md)

## 📋 Prerequisites (Containerized Deployment)

- Python 3.11+
- Podman (recommended) or Docker with docker-compose
- `.env` file with API credentials (copy from `.env.example`)

## 🚀 Quick Start (Containerized)

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your actual credentials
nano .env
```

Required configuration:
- `THRUK_API_KEY`: Your Thruk API key (or secret.key from OMD - see OMD Integration below)
- `THRUK_BASE_URL`: Your Thruk server URL (e.g., https://your-server.com/thruk)
- `MCP_SERVER_URL`: Thruk MCP server SSE endpoint (e.g., http://thruk-mcp:8001/sse)
- `OPENAI_API_KEY`: Your LLM API key
- `OPENAI_BASE_URL`: API endpoint (default: https://api.openai.com/v1)
- `OPENAI_MODEL`: Model to use (e.g., gpt-4, claude-3, etc.)

**Note for OMD Integration**: When running in an OMD site, the chatbot automatically loads `$OMD_ROOT/var/thruk/secret.key` if `THRUK_API_KEY` is not explicitly set. This enables multi-user authentication where the chatbot authenticates to Thruk as each session user via the `X-Thruk-Auth-User` header.

### Session Management Configuration

The chatbot includes robust session management with configurable timeouts and automatic cleanup:

- `SESSION_TIMEOUT_MINUTES` (default: `15`)
  - Session inactivity timeout in minutes
  - Sessions expire after this period of no user interaction
  - Frontend automatically detects expiration and prompts refresh
  - Example: `SESSION_TIMEOUT_MINUTES=30` for 30-minute timeout

- `SESSION_CLEANUP_INTERVAL_SECONDS` (default: `60`)
  - Background cleanup task interval in seconds
  - How often expired sessions are removed from memory
  - Lower values = faster cleanup, higher CPU usage
  - Example: `SESSION_CLEANUP_INTERVAL_SECONDS=120` for 2-minute cleanup interval

- `DEFAULT_USERNAME` (default: `chatuser`)
  - Default username when X-WEBAUTH-USER header is absent
  - Used in standalone/development deployments without Apache proxy
  - Example: `DEFAULT_USERNAME=anonymous`

### Other Optional Configuration

- `LOG_LEVEL`: Logging level - DEBUG, INFO, WARNING, ERROR (default: INFO)
- `THRUK_VERIFY_SSL`: SSL certificate verification (default: true, false in OMD for self-signed certs)

### 2. Run with Podman

```bash
# Start an OMD container
podman run --rm -it \
    -p 8443:443 \
    -v `pwd`:/src/omd-mcp \
    --entrypoint \
    bash docker.io/consol/omd-labs-debian:nightly 
root@1234567890:/# /usr/sbin/apache2ctl -D FOREGROUND

# Install the chatbot in 1234567890 1234567890
podman exec -it 1234567890 bash
root@1234567890:/# omd rm demo
root@1234567890:/# cd /src/omd-mcp/ansible
root@1234567890:/# ansible-playbook -i inventory install-all.yml
root@1234567890:/# omd create demo

# Enable the chatbot and add openai-compatible url and token
podman exec -it 1234567890 bash
root@1234567890:/# su - demo
OMD[demo@1234567890]:~$ omd config set CHATBOT on
OMD[demo@1234567890]:~$ edit etc/chatbot/chatbot.conf
OMD[demo@1234567890]:~$ omd restart

# Access the chatbot UI
https://localhost:8443/demo/chatbot

```

## 🔐 Session Management

The chatbot includes a comprehensive session management system that ensures security and proper resource cleanup:

### How Sessions Work

1. **Session Creation**: When you access the chatbot UI (`http://localhost:8000`), a new session is automatically created
2. **User Authentication**:
   - In OMD deployments: Username extracted from Apache's `X-WEBAUTH-USER` header
   - In standalone/development: Uses `DEFAULT_USERNAME` environment variable (default: `chatuser`)
3. **Session Isolation**: Each user gets their own isolated session with:
   - Separate conversation history
   - Independent MCP connections
   - Isolated LLM context
4. **Automatic Timeout**: Sessions expire after `SESSION_TIMEOUT_MINUTES` of inactivity (default: 15 minutes)
5. **Resource Cleanup**: Expired sessions automatically release MCP connections, LLM connections, and conversation history

### Session Timeout Behavior

**What happens when a session times out:**
- Frontend displays a yellow notification banner: "Your session has ended after X minutes of inactivity"
- User can refresh the page to create a new session
- Previous conversation history is lost (sessions are not persisted)
- All resources (MCP/LLM connections) are cleaned up automatically

**How to prevent timeout:**
- The frontend automatically sends heartbeat requests every 50% of the timeout interval
- Any user interaction (typing, sending messages) resets the inactivity timer
- Page Visibility API prevents timeout when browser tab is in background:
  - When you switch back to the chatbot tab, an immediate heartbeat is sent
  - This prevents timeouts during brief tab switches

### Testing Session Management Locally

```bash
# 1. Set a short timeout for testing (e.g., 2 minutes)
echo "SESSION_TIMEOUT_MINUTES=2" >> .env

# 2. Start the chatbot
podman compose up -d chatbot

# 3. Open browser to http://localhost:8000
# 4. Send a message
# 5. Wait 2+ minutes without interaction
# 6. Try to send another message
# Expected: Session timeout notification appears

# 7. Check logs to see cleanup
podman compose logs -f chatbot | grep -i "session"
```

### Authentication in Development vs Production

**Development (Standalone)**:
```bash
# No Apache proxy - uses DEFAULT_USERNAME
DEFAULT_USERNAME=testuser
# All sessions will be created as "testuser"
```

**Production (OMD Integration)**:
```bash
# Apache proxy sends X-WEBAUTH-USER header
# Chatbot extracts actual username from header
# Each user gets their own isolated session
# Example: user "alice" and "bob" have separate sessions
```

**Testing Authentication Locally**:
```bash
# Simulate Apache header with curl
curl -H "X-WEBAUTH-USER: alice" http://localhost:8000/

# Or use browser extension to set custom headers
# Chrome: ModHeader, Firefox: Modify Header Value
```

### Session Security Features

- **HTTP-Only Cookies**: Session ID stored in HTTP-only cookie (prevents XSS attacks)
- **SameSite Protection**: Cookies set to `SameSite=Lax` (prevents CSRF attacks)
- **Automatic Expiration**: Cookie expires after `SESSION_TIMEOUT_MINUTES`
- **Resource Limits**: Background cleanup prevents memory leaks from abandoned sessions
- **Per-User Isolation**: Each user's session data is completely isolated
- **No Persistence**: Sessions are not stored to disk (memory-only for security)

### Monitoring Sessions

```bash
# Check active session count
curl http://localhost:8000/health
# Returns: {"status": "healthy", "active_sessions": 3, "timestamp": "..."}

# View session-related logs
podman compose logs chatbot | grep -i session

# Watch for session creation/cleanup in real-time
podman compose logs -f chatbot | grep -E "(Session created|Session.*expired|Cleaned up)"
```

## 📁 Project Structure

```
.
├── chatbot/                    # Chatbot service
│   ├── __init__.py            # Package initializer
│   ├── chatbot.py             # Main FastAPI application
│   ├── session_manager.py    # Session management
│   ├── templates/             # Jinja2 templates
│   │   └── index.html        # Chat UI
│   ├── Containerfile          # Container image (multi-stage)
│   └── requirements.txt       # Python dependencies
│
├── thruk_mcp/                 # Thruk MCP service
│   ├── __init__.py            # Package initializer
│   ├── thruk_mcp.py          # FastMCP server (placeholder)
│   ├── Containerfile          # Container image (multi-stage)
│   └── requirements.txt       # Python dependencies
│
├── tests/                     # Test suite
│   ├── chatbot/              # Chatbot tests
│   └── integration/          # Integration tests
│
├── specs/                     # Feature specifications
│   └── 001-session-management/  # Session management spec
│
├── .env                       # Environment variables (DO NOT COMMIT)
├── .env.example              # Example configuration
├── .dockerignore             # Docker build exclusions
├── docker-compose.yml        # Service orchestration
├── CLAUDE.md                 # AI development guidelines
├── SESSION.md                # Session management requirements
└── README.md                 # This file
```

## 🔧 Development

### Local Development (Without Containers)

```bash
# Install dependencies
pip install -r chatbot/requirements.txt
pip install -r thruk_mcp/requirements.txt

# Configure environment
cp .env.example .env
nano .env

# Run services locally
# Terminal 1: Start Thruk MCP
cd thruk_mcp
python thruk_mcp.py --listen 8001

# Terminal 2: Start Chatbot
cd chatbot
python chatbot.py

# Access: http://localhost:8000
```

### Container Development

```bash
# Rebuild specific service
podman compose build chatbot
podman compose build thruk-mcp

# Rebuild all services
podman compose build

# Restart specific service
podman compose restart chatbot

# View live logs
podman compose logs -f chatbot

# Execute commands in running container
podman exec -it chatbot bash
podman exec -it thruk-mcp bash

# Inspect container filesystem
podman exec chatbot ls -la /app/chatbot/
```

### Running Tests

```bash
# Install test dependencies
pip install -r tests/requirements.txt

# Run all tests
pytest

# Run specific test suite
pytest tests/chatbot/

# Run with coverage
pytest --cov=chatbot --cov=thruk_mcp
```

## 📖 Available MCP Tools

The Thruk MCP service currently provides these tools (placeholder implementation):

### Implemented
- `health_check()` - Returns MCP server health status
- `get_thruk_status(username: str)` - Placeholder for Thruk status retrieval

### Planned (To Be Implemented)
- `thruk_list_hosts` - List all monitored hosts
- `thruk_list_services` - List services for a host
- `thruk_list_hostgroups` - List host groups
- `thruk_list_servicegroups` - List service groups
- `thruk_get_host_details` - Get detailed host information
- `thruk_get_service_details` - Get detailed service information
- `thruk_schedule_downtime` - Schedule maintenance downtime
- `thruk_list_downtimes` - List active downtimes

**Note**: The MCP server (`thruk_mcp/thruk_mcp.py`) is currently a placeholder. Replace it with full Thruk API integration as needed.

## 🔒 Security

- **Never commit `.env`** - Contains secrets and API keys (already in `.gitignore`)
- **Use `.env.example`** - Template for required configuration
- **Non-root containers** - Both services run as non-root users:
  - Chatbot: UID 1000, user `chatbot`
  - Thruk MCP: UID 1001, user `thruk-mcp`
- **Multi-stage builds** - Minimal attack surface in production images
- **Session Management Security**:
  - Configurable inactivity timeout (default: 15 minutes)
  - HTTP-only cookies prevent XSS attacks
  - SameSite=Lax cookies prevent CSRF attacks
  - Automatic session cleanup on timeout
  - Frontend timeout detection with clear user notification
  - Session heartbeat keeps active sessions alive
  - Per-user session isolation
- **SSL verification** - Can be disabled for development (`THRUK_VERIFY_SSL=false`)
- **X-WEBAUTH-USER header** - Username propagation from Apache proxy (see SESSION.md)

### Container Security Features

- **Read-only permissions** - Application files owned by service users
- **No sudo/root access** - Containers run with limited privileges
- **Isolated networks** - Services communicate over internal `mcp-internal` network
- **Resource limits** - CPU and memory constraints defined in docker-compose.yml

## 🐛 Troubleshooting

### Container Issues

```bash
# Check container status
podman compose ps
podman ps

# View logs
podman compose logs -f chatbot
podman compose logs -f thruk-mcp

# Restart specific service
podman compose restart chatbot

# Restart all services
podman compose restart

# Force clean restart
podman compose down
podman compose up -d

# Check resource usage
podman stats

# Inspect container
podman inspect chatbot
```

### Common Issues

**Template not found error:**
```bash
# Verify templates directory exists
podman exec chatbot ls -la /app/chatbot/templates/

# Check templates path in code
podman exec chatbot grep -A 3 "Templates" /app/chatbot/chatbot.py
```

**Port already in use:**
```bash
# Find process using port 8000
lsof -i :8000
# or
netstat -tulpn | grep 8000

# Kill the process or change port in docker-compose.yml
```

**Container won't start:**
```bash
# Check full logs
podman logs chatbot

# Exec into container (if running)
podman exec -it chatbot bash

# Run container interactively for debugging
podman run -it --rm localhost/omd-mcp_chatbot:latest bash
```

**Network connectivity issues:**
```bash
# Test inter-container communication
podman exec chatbot curl -s http://thruk-mcp:8001/sse

# Check network
podman network ls
podman network inspect mcp-internal

# Verify services can resolve each other
podman exec chatbot ping thruk-mcp
```

**Environment variables not loaded:**
```bash
# Check if .env file exists
ls -la .env

# Verify container sees environment variables
podman exec chatbot env | grep THRUK
podman exec chatbot env | grep OPENAI
```

### Health Checks

```bash
# Chatbot health
curl http://localhost:8000/health

# MCP SSE endpoint
curl -H "Accept: text/event-stream" http://localhost:8001/sse --max-time 2

# Test from within container
podman exec chatbot curl http://localhost:8000/health
```

## 📚 Documentation

### Project Documentation
- [SESSION.md](SESSION.md) - Session management and Apache proxy integration
- [CLAUDE.md](CLAUDE.md) - AI development guidelines
- [specs/001-session-management/](specs/001-session-management/) - Session management specification

### External Documentation
- [FastMCP Documentation](https://gofastmcp.com/) - MCP server framework
- [Thruk API Documentation](https://thruk.org/documentation/rest.html) - Thruk REST API
- [Podman Compose](https://github.com/containers/podman-compose) - Container orchestration

## 🏗️ Container Architecture

### Image Details
- **Base Image**: `python:3.11-slim` (Debian-based)
- **Build Type**: Multi-stage builds
- **Final Size**: Chatbot ~300MB, MCP ~267MB
- **Security**: Non-root users, minimal attack surface

### Networking
- **Network**: `mcp-internal` (bridge mode)
- **Service Discovery**: DNS-based (e.g., `http://thruk-mcp:8001`)
- **External Ports**:
  - Chatbot: 8000
  - MCP: 8001 (optional, for debugging)

### Environment Configuration
Environment variables are loaded from `.env` file:
- Located at project root
- Never committed to git
- Used by both local dev and containers
- Injected into containers at runtime

## 🤝 Contributing

1. Copy `.env.example` to `.env` with your credentials
2. Create feature branch from `main`
3. Make changes and test locally
4. Test containerized deployment: `podman compose up -d`
5. Run tests: `pytest`
6. Ensure `.env` is not committed
7. Submit pull request

## 📄 License

[Add your license here]
