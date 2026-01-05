# OMD Integration Guide

This document describes how the chatbot service has been integrated into OMD (Open Monitoring Distribution).

## Overview

The chatbot has been integrated as a native OMD service, running within an OMD site and accessible through the Apache frontend with Thruk authentication.

## Architecture

```
[User] --> [Apache :8443] --> [Thruk Cookie Auth] --> [Chatbot Backend :8000]
```

- **Frontend**: Apache reverse proxy with SSL (port 8443 externally, port 5000 internally)
- **Authentication**: Thruk cookie-based authentication system
- **Backend**: FastAPI chatbot service (port 8000, localhost only)
- **User Propagation**: X-WEBAUTH-USER header forwarded from Apache to chatbot

## Integration Components

### 1. Service Files

**Location**: `${OMD_ROOT}/local/lib/chatbot/`
- `chatbot.py` - Main FastAPI application
- `session_manager.py` - Session management logic
- `templates/` - Jinja2 templates
- `requirements.txt` - Python dependencies

### 2. Init Script

**Location**: `${OMD_ROOT}/etc/init.d/chatbot`
- Standard OMD init script using `__generic_init` pattern
- Manages chatbot service lifecycle (start/stop/restart/status)
- Configures environment variables from site.conf
- Starts uvicorn server on configured port

**Usage**:
```bash
omd start chatbot   # Start chatbot service
omd stop chatbot    # Stop chatbot service
omd restart chatbot # Restart chatbot service
omd status chatbot  # Check service status
```

### 3. Apache Configuration

**Location**: `${OMD_ROOT}/etc/apache/conf.d/chatbot.conf`
- Reverse proxy from `/${OMD_SITE}/chatbot` to `http://127.0.0.1:8000`
- X-WEBAUTH-USER header forwarding (supports both Thruk cookie auth and basic auth)
- Health check endpoint configuration
- API endpoint configuration

**Authentication Flow**:
1. User accesses `https://hostname/SITE/chatbot`
2. Thruk cookie auth intercepts and validates user
3. Apache sets X-WEBAUTH-USER header from REMOTE_USER
4. Chatbot backend receives authenticated username
5. Session created with authenticated user

### 4. OMD Site Configuration

**Location**: `${OMD_ROOT}/etc/omd/site.conf`

OMD service control variables (only):
```bash
CONFIG_CHATBOT='on'                    # Enable/disable chatbot service
CONFIG_CHATBOT_TCP_PORT='8000'         # Chatbot backend port
```

### 5. Application Configuration

**Location**: `${OMD_ROOT}/etc/chatbot/chatbot.conf`

Application-specific settings (sourced as bash script):
```bash
# Session Management
SESSION_TIMEOUT_MINUTES=15
DEFAULT_USERNAME="chatuser"
SESSION_CLEANUP_INTERVAL_SECONDS=60

# Logging
LOG_LEVEL="INFO"

# LLM Configuration
OPENAI_API_KEY=""
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_MODEL="gpt-4"

# Thruk MCP Integration
THRUK_API_KEY=""
```

This follows OMD conventions where:
- `site.conf` = Service enablement and port configuration
- `etc/chatbot/chatbot.conf` = Application-specific configuration

## Installation

### Automated Installation (Recommended)

Use the provided installation script:

```bash
# 1. Copy repository to your OMD container/server
podman cp /path/to/omd-mcp CONTAINER_ID:/tmp/
# or: scp -r omd-mcp server:/tmp/

# 2. Access the container/server and switch to site user
podman exec -it CONTAINER_ID bash
su - SITENAME

# 3. Run the installation script
cd /tmp/omd-mcp
./omd/install-chatbot.sh

# 4. Start services
omd start chatbot
omd reload apache
```

The script will:
- Copy chatbot code to `local/lib/chatbot/`
- Install Python dependencies
- Create init.d script from template
- Create Apache configuration from template
- Add configuration variables to site.conf

### Manual Installation

For manual installation or customization, see the [omd/README.md](../omd/README.md) file.

### Template Files

All configuration templates are available in the `omd/templates/` directory:
- `chatbot.init` - Init script template
- `chatbot.apache.conf` - Apache configuration template
- `site.conf.snippet` - Configuration variables template

These templates are production-ready and can be customized as needed.

## Accessing the Chatbot

### Web Interface

**URL**: `https://hostname:8443/SITE/chatbot/`

- Requires authentication through Thruk (OMD's SSO system)
- Users must log in with OMD credentials before accessing chatbot
- Authenticated username automatically propagated to chatbot sessions

### Health Check

**URL**: `https://hostname:8443/SITE/chatbot/health`

- Intended for monitoring systems
- Returns JSON: `{"status":"healthy","active_sessions":0,"timestamp":"..."}`
- Currently requires authentication (protected by Thruk cookie auth)

### API Endpoints

**Base URL**: `https://hostname:8443/SITE/chatbot/api/`

- Session management endpoints
- Inherits authentication from parent location
- Returns JSON responses

## Limitations and Known Issues

### 1. Python Version Constraint

**Issue**: OMD sites typically use Python 3.9, but FastMCP requires Python 3.11+

**Impact**:
- MCP server integration not yet available
- Chatbot can run but cannot connect to Thruk MCP server
- LLM features will work, but Thruk monitoring integration pending

**Workaround Options**:
- Install Python 3.11+ in OMD site's local directory
- Wait for FastMCP to support Python 3.9
- Use alternative MCP client library

### 2. Authentication on Health Endpoint

**Issue**: Health check endpoint requires Thruk cookie authentication

**Impact**: External monitoring systems cannot easily access health endpoint

**Workaround Options**:
- Use authenticated requests with valid Thruk session
- Access backend directly: `curl http://127.0.0.1:8000/health` (from OMD site user)
- Add RewriteCond to Thruk cookie auth config to exclude chatbot health check

### 3. MCP Integration Pending

**Issue**: thruk_mcp service not yet integrated into OMD

**Impact**: Chatbot cannot query Thruk monitoring data

**Next Steps**:
- Resolve Python version constraint
- Integrate thruk_mcp as separate OMD service
- Configure MCP server URL in chatbot environment

## Verification

Confirm the integration is working:

```bash
# Check service status
omd status chatbot

# Check process
ps aux | grep "uvicorn chatbot"

# Check backend health (from OMD site)
curl http://127.0.0.1:8000/health

# Check Apache config
cat etc/apache/conf.d/chatbot.conf

# View logs
tail -f var/log/chatbot.log
```

## Configuration Management

### Changing Chatbot Port

```bash
# Edit OMD site config
vi etc/omd/site.conf
# Change: CONFIG_CHATBOT_TCP_PORT='8001'

# Update Apache config
vi etc/apache/conf.d/chatbot.conf
# Update ProxyPass line to match new port

# Reload services
omd restart chatbot
omd reload apache
```

### Enabling Debug Logging

```bash
# Edit application config
vi etc/chatbot/chatbot.conf
# Change: LOG_LEVEL="DEBUG"

# Restart chatbot
omd restart chatbot

# View debug logs
tail -f var/log/chatbot.log
```

### Configuring LLM Backend

```bash
# Edit application config
vi etc/chatbot/chatbot.conf

# Set OpenAI configuration
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_MODEL="gpt-4o"

# Or configure for local LLM
OPENAI_API_KEY=""  # Not needed for local
OPENAI_BASE_URL="http://localhost:1234/v1"
OPENAI_MODEL="local-model"

# Restart chatbot
omd restart chatbot
```

## Security Considerations

1. **Authentication**: All chatbot access requires Thruk authentication
2. **Authorization**: Uses X-WEBAUTH-USER header (trusted from Apache)
3. **Network**: Backend only listens on 127.0.0.1 (not exposed externally)
4. **TLS**: External access through Apache SSL (port 8443)
5. **Session Timeout**: Configurable (default: 15 minutes)
6. **API Keys**: Stored in site.conf (file permissions: 600, owner: site user)

## Troubleshooting

### Service Won't Start

```bash
# Check logs
tail -f var/log/chatbot.log

# Check if port is already in use
netstat -tlnp | grep 8000

# Check Python environment
which python3
python3 --version

# Check dependencies
pip list | grep -i fastapi
```

### Authentication Issues

```bash
# Verify Apache config is loaded
omd reload apache

# Check for X-WEBAUTH-USER header in backend logs
grep "X-WEBAUTH-USER" var/log/chatbot.log

# Test backend directly (bypasses auth)
curl -H "X-WEBAUTH-USER: testuser" http://127.0.0.1:8000/
```

### Apache Proxy Issues

```bash
# Check Apache error log
tail -f var/log/apache/error_log

# Verify proxy modules are loaded
httpd -M | grep proxy

# Test backend connectivity from Apache
curl http://127.0.0.1:8000/health
```

## Next Steps

1. **Resolve Python Version**:
   - Install Python 3.11+ in OMD site local directory
   - Or explore alternative MCP client libraries

2. **Integrate MCP Server**:
   - Create init.d script for thruk_mcp
   - Add Apache config if needed
   - Configure MCP_SERVER_URL in chatbot environment

3. **Enhance Health Check**:
   - Make health endpoint truly public (exclude from Thruk auth)
   - Add more health metrics (MCP connectivity, LLM status, etc.)

4. **Production Readiness**:
   - Configure log rotation
   - Set up monitoring alerts
   - Add resource limits
   - Configure backup for session data (if persisted)

5. **Documentation**:
   - Add chatbot to OMD site documentation
   - Create user guide for chatbot features
   - Document MCP integration when available

## References

- OMD Documentation: https://omdistro.org/
- Thruk Documentation: https://thruk.org/
- FastAPI Documentation: https://fastapi.tiangolo.com/
- MCP Documentation: https://modelcontextprotocol.io/
