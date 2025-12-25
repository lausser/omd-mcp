# omd-mcp Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-12-24

## Active Technologies

- Python 3.11+ (per README.md prerequisites) + FastAPI (web framework), FastMCP (MCP SDK), uvicorn (ASGI server), Jinja2 (templates) (001-session-management)

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

- 001-session-management: Added Python 3.11+ (per README.md prerequisites) + FastAPI (web framework), FastMCP (MCP SDK), uvicorn (ASGI server), Jinja2 (templates)

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

<!-- MANUAL ADDITIONS END -->
