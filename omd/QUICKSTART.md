# OMD Chatbot - Quick Start Guide

Get the chatbot running in your OMD site in 5 minutes.

## Prerequisites

- OMD installation with a site created
- Access to the OMD site user
- Python 3.9+ (Python 3.11+ recommended)
- This repository available on the server

## Installation

### Step 1: Copy Repository to Server

```bash
# From your workstation
podman cp /path/to/omd-mcp CONTAINER_ID:/tmp/

# Or via SCP
scp -r omd-mcp server:/tmp/
```

### Step 2: Access Site User

```bash
# Access container
podman exec -it CONTAINER_ID bash

# Switch to site user
su - YOUR_SITE_NAME
```

### Step 3: Run Installation Script

```bash
cd /tmp/omd-mcp
./omd/install-chatbot.sh
```

The script will:
- ✓ Copy chatbot code
- ✓ Install dependencies
- ✓ Create init script
- ✓ Configure Apache
- ✓ Update site.conf

### Step 4: Configure (Optional)

```bash
# Edit configuration if needed
vi etc/omd/site.conf

# Set your OpenAI API key (or use local LLM)
CONFIG_CHATBOT_OPENAI_API_KEY='sk-your-key-here'
CONFIG_CHATBOT_OPENAI_MODEL='gpt-4o'
```

### Step 5: Start Services

```bash
omd start chatbot
omd reload apache
```

### Step 6: Verify

```bash
# Check service status
omd status chatbot
# Should show: chatbot...OK

# Check backend health
curl http://127.0.0.1:8000/health
# Should return: {"status":"healthy","active_sessions":0,...}
```

### Step 7: Access Chatbot

Open your browser and navigate to:
```
https://your-server/YOUR_SITE_NAME/chatbot/
```

Login with your OMD credentials and start chatting!

## Troubleshooting

### Service Won't Start

```bash
# Check logs
tail -f var/log/chatbot.log

# Check for port conflicts
netstat -tlnp | grep 8000
```

### Python Version Issues

If you see "fastmcp requires Python 3.11+":

```bash
# Install core packages only (skips MCP)
pip install fastapi uvicorn jinja2 httpx python-dotenv
```

The chatbot will work without MCP (you just won't have Thruk monitoring integration yet).

### Can't Access from Browser

Check:
1. Apache is running: `omd status apache`
2. Chatbot is running: `omd status chatbot`
3. No firewall blocking port 443/5000
4. Using correct URL with site name

## Next Steps

- **Configure LLM**: Set up OpenAI or local LLM in site.conf
- **Customize**: Adjust ports, logging, timeouts in site.conf
- **Integrate MCP**: Set up Thruk MCP server for monitoring queries
- **Monitor**: Check logs and set up alerts

## Documentation

- **[omd/README.md](README.md)** - Full OMD deployment guide
- **[docs/OMD_INTEGRATION.md](../docs/OMD_INTEGRATION.md)** - Detailed integration docs
- **[docs/OMD_ACCESS_GUIDE.md](../docs/OMD_ACCESS_GUIDE.md)** - User access guide

## Support

Issues? Check:
1. Logs: `var/log/chatbot.log`
2. Apache logs: `var/log/apache/error_log`
3. Service status: `omd status`
4. Documentation links above

---

**Estimated time**: 5-10 minutes
**Difficulty**: Easy
**Support level**: Production-ready
