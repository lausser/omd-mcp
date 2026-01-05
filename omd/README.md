# OMD Deployment Files

This directory contains templates and scripts for deploying the chatbot into an OMD (Open Monitoring Distribution) site.

## Quick Start

```bash
# 1. Copy this repository to your OMD container
podman cp /path/to/omd-mcp CONTAINER_ID:/tmp/

# 2. Access the container and switch to your site user
podman exec -it CONTAINER_ID bash
su - YOUR_SITE_NAME

# 3. Run the installation script
cd /tmp/omd-mcp
./omd/install-chatbot.sh

# 4. Enable chatbot via OMD config
omd stop
omd config set CHATBOT on
omd start

# 5. Start chatbot service
etc/init.d/chatbot start

# 6. Access the chatbot
# https://your-server/YOUR_SITE_NAME/chatbot/
```

The installation script installs **OMD hooks** that integrate chatbot with OMD's configuration system (`omd config`).

## Files in This Directory

### OMD Hooks (Recommended Integration Method)

- **`hooks/CHATBOT`** - Main service hook
  - Enables/disables chatbot service
  - Creates default configuration files
  - Manages Apache integration via symlinks
  - Usage: `omd config set CHATBOT on`

- **`hooks/CHATBOT_TCP_PORT`** - Port configuration hook
  - Manages chatbot backend port
  - Auto-detects port conflicts across OMD sites
  - Dynamically generates Apache proxy configuration
  - Usage: `omd config set CHATBOT_TCP_PORT 8001`

See [hooks/README.md](hooks/README.md) for detailed hook documentation.

### Templates (Fallback for Non-OMD Deployments)

- **`templates/chatbot.init`** - Init script for the chatbot service
  - Installed to: `etc/init.d/chatbot`
  - Manages service lifecycle (start/stop/restart/status)
  - Sources configuration from `etc/chatbot/chatbot.conf`

- **`templates/chatbot.apache.conf`** - Apache reverse proxy configuration (static)
  - For non-hook deployments
  - Hooks generate this file dynamically with correct ports

- **`templates/site.conf.snippet`** - OMD service configuration
  - For manual site.conf editing
  - Hooks manage this automatically

- **`templates/chatbot.conf`** - Application configuration template
  - Installed to: `etc/chatbot/chatbot.conf`
  - Contains LLM settings, API keys, logging, session config
  - Created automatically by CHATBOT hook on first enable

### Scripts

- **`install-chatbot.sh`** - Automated installation script
  - Copies chatbot code to `local/lib/chatbot/`
  - Installs Python dependencies
  - **Installs OMD hooks** (if `lib/omd/hooks/` exists)
  - Creates init.d script
  - Must be run as OMD site user
  - After installation, use `omd config set CHATBOT on`

## Manual Installation

If you prefer to install manually instead of using the script:

### 1. Copy Chatbot Code

```bash
cp -r /path/to/omd-mcp/chatbot $OMD_ROOT/local/lib/
```

### 2. Install Dependencies

```bash
pip install -r $OMD_ROOT/local/lib/chatbot/requirements.txt
```

**Note**: If you encounter Python version issues (FastMCP requires Python 3.11+), you can:
- Skip FastMCP for now: `pip install fastapi uvicorn jinja2 httpx python-dotenv`
- Or install a newer Python version in your OMD site

### 3. Create Init Script

```bash
cp templates/chatbot.init $OMD_ROOT/etc/init.d/chatbot
chmod 755 $OMD_ROOT/etc/init.d/chatbot
```

### 4. Create Apache Config

```bash
cp templates/chatbot.apache.conf $OMD_ROOT/etc/apache/conf.d/chatbot.conf
chmod 600 $OMD_ROOT/etc/apache/conf.d/chatbot.conf
```

### 5. Update site.conf

```bash
cat templates/site.conf.snippet >> $OMD_ROOT/etc/omd/site.conf
```

### 6. Create application config

```bash
mkdir -p $OMD_ROOT/etc/chatbot
cp templates/chatbot.conf $OMD_ROOT/etc/chatbot/chatbot.conf
```

Edit the configuration as needed:
```bash
vi $OMD_ROOT/etc/chatbot/chatbot.conf
# Set OPENAI_API_KEY and other settings
```

### 7. Start Services

```bash
omd start chatbot
omd reload apache
```

### 8. Verify

```bash
omd status chatbot
curl http://127.0.0.1:8000/health
```

## Configuration

### Port Configuration

The default chatbot port is 8000. To change it:

1. Edit `etc/omd/site.conf`:
   ```bash
   CONFIG_CHATBOT_TCP_PORT='8001'
   ```

2. Update `etc/apache/conf.d/chatbot.conf`:
   ```apache
   ProxyPass http://127.0.0.1:8001 retry=0 disablereuse=On
   ProxyPassReverse http://127.0.0.1:8001
   ```

3. Restart services:
   ```bash
   omd restart chatbot
   omd reload apache
   ```

### LLM Configuration

Configure the OpenAI-compatible LLM backend in `etc/chatbot/chatbot.conf`:

```bash
# For OpenAI
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://api.openai.com/v1"
OPENAI_MODEL="gpt-4o"

# For local LLM (e.g., LM Studio)
OPENAI_API_KEY=""  # Not needed for local
OPENAI_BASE_URL="http://localhost:1234/v1"
OPENAI_MODEL="local-model"
```

### Logging

Configure log level in `etc/chatbot/chatbot.conf`:

```bash
LOG_LEVEL="DEBUG"  # DEBUG, INFO, WARNING, ERROR
```

View logs:
```bash
tail -f $OMD_ROOT/var/log/chatbot.log
```

## Requirements

### System Requirements

- OMD installation (any recent version)
- Python 3.9+ (Python 3.11+ recommended for full MCP support)
- Apache with mod_proxy and mod_proxy_http
- Thruk (for authentication)

### Supported Platforms

Tested and working on:
- ✅ **Debian 12 (bookworm)** - Python 3.11.2, full MCP support
- ✅ **Rocky Linux 9** - Python 3.9, limited MCP support (core chatbot works)
- ✅ **Rocky Linux 10** - Expected to work with modern Python

The Apache configuration template auto-detects module paths for both Debian/Ubuntu (`/usr/lib/apache2/modules/`) and RHEL/Rocky (`/usr/lib64/httpd/modules/`).

### Python Packages

Required packages (from `chatbot/requirements.txt`):
- fastapi >= 0.104.0
- uvicorn[standard] >= 0.24.0
- jinja2 >= 3.1.2
- httpx >= 0.25.0
- python-dotenv >= 1.0.0
- fastmcp >= 0.2.0 (requires Python 3.11+)

## Troubleshooting

### Service Won't Start

```bash
# Check logs
tail -f var/log/chatbot.log

# Check if port is in use
netstat -tlnp | grep 8000

# Verify Python dependencies
pip list | grep -i fastapi
```

### Authentication Issues

```bash
# Test backend directly (bypasses auth)
curl -H "X-WEBAUTH-USER: testuser" http://127.0.0.1:8000/

# Check Apache logs
tail -f var/log/apache/error_log
```

### Python Version Issues

If you get "fastmcp requires Python 3.11+":

**Option 1**: Install without MCP support (chatbot will work, but no Thruk integration)
```bash
pip install fastapi uvicorn jinja2 httpx python-dotenv
```

**Option 2**: Install Python 3.11+ in your OMD site
```bash
cd $OMD_ROOT/local
# Download and install Python 3.11+ to local/
# Update init script to use local/bin/python3.11
```

## Documentation

For detailed information, see:

- **[OMD_INTEGRATION.md](../docs/OMD_INTEGRATION.md)** - Complete integration guide
  - Architecture overview
  - Security considerations
  - Limitations and known issues
  - Configuration management
  - Production readiness checklist

- **[OMD_ACCESS_GUIDE.md](../docs/OMD_ACCESS_GUIDE.md)** - User access guide
  - How to access the chatbot
  - Authentication flow
  - API access
  - Troubleshooting

- **[README.md](../README.md)** - Main project documentation
  - Development setup
  - Container deployment
  - Testing

## Testing the Installation

After installation, verify everything is working:

```bash
# 1. Check service status
omd status chatbot

# 2. Check backend health
curl http://127.0.0.1:8000/health

# 3. Check process
ps aux | grep uvicorn

# 4. Check logs
tail -20 var/log/chatbot.log

# 5. Access through browser
# https://your-server/$OMD_SITE/chatbot/
```

Expected results:
- Service status: "chatbot...OK"
- Health check: `{"status":"healthy","active_sessions":0,...}`
- Process: uvicorn running as site user
- Logs: No errors, service started successfully
- Browser: Login page, then chatbot interface

## Support

For issues or questions:
1. Check the troubleshooting sections in the documentation
2. Review logs: `var/log/chatbot.log` and `var/log/apache/error_log`
3. Open an issue in the repository with logs and configuration details
