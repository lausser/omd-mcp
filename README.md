# MCP Chatbot with Thruk Integration

A chatbot application that integrates with Thruk monitoring system via Model Context Protocol (MCP).

## 🏗️ Architecture

- **Chatbot Service**: Web UI and LLM integration
- **Thruk MCP Service**: MCP server providing Thruk monitoring tools
- **Communication**: HTTP/Streamable HTTP between services

## 📋 Prerequisites

- Python 3.11+
- Podman (recommended) or Docker with docker-compose
- `.env` file with API credentials (copy from `.env.example`)

## 🚀 Quick Start

### 1. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your actual credentials
nano .env
```

Required configuration:
- `THRUK_API_KEY`: Your Thruk API key
- `THRUK_BASE_URL`: Your Thruk server URL (e.g., https://your-server.com/thruk)
- `OPENAI_API_KEY`: Your LLM API key
- `OPENAI_BASE_URL`: API endpoint (default: https://api.openai.com/v1)
- `OPENAI_MODEL`: Model to use (e.g., gpt-4, claude-3, etc.)

### 2. Run with Podman Compose

```bash
# Build and start both services
podman compose build
podman compose up -d

# View logs
podman compose logs -f

# View specific service logs
podman compose logs -f chatbot
podman compose logs -f thruk-mcp

# Check status
podman compose ps

# Access the chatbot UI
http://localhost:8000

# Access MCP SSE endpoint (for debugging)
http://localhost:8001/sse
```

### 3. Run with Docker Compose

```bash
# Same commands, just use 'docker' instead of 'podman'
docker compose build
docker compose up -d
docker compose logs -f
```

### 4. Stop Services

```bash
# Stop all services
podman compose down

# Stop and remove volumes (if any)
podman compose down -v
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
- **Session management** - 15-minute inactivity timeout, HTTP-only cookies
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
