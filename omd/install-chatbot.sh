#!/bin/bash
# OMD Chatbot Installation Script
# Run this script as the OMD site user

set -e

# Check if running as OMD site user
if [ -z "$OMD_ROOT" ]; then
    echo "ERROR: This script must be run as an OMD site user"
    echo "Usage: su - SITENAME && cd /path/to/omd-mcp && ./omd/install-chatbot.sh"
    exit 1
fi

echo "Installing chatbot into OMD site: $OMD_SITE"
echo "OMD_ROOT: $OMD_ROOT"
echo

# Determine the repository root (script is in omd/ subdirectory)
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "Repository root: $REPO_ROOT"
echo

# Step 1: Copy chatbot code (code to local/lib, templates to share)
echo "Step 1: Copying chatbot files"

# Copy Python code to local/lib/chatbot
if [ -d "$OMD_ROOT/local/lib/chatbot" ]; then
    echo "  Warning: local/lib/chatbot directory already exists, backing up..."
    mv "$OMD_ROOT/local/lib/chatbot" "$OMD_ROOT/local/lib/chatbot.backup.$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$OMD_ROOT/local/lib/chatbot"
cp "$REPO_ROOT/chatbot/__init__.py" "$OMD_ROOT/local/lib/chatbot/"
cp "$REPO_ROOT/chatbot/chatbot.py" "$OMD_ROOT/local/lib/chatbot/"
cp "$REPO_ROOT/chatbot/session_manager.py" "$OMD_ROOT/local/lib/chatbot/"
echo "  ✓ Python code copied to local/lib/chatbot/"

# Copy templates to share/chatbot
if [ -d "$OMD_ROOT/share/chatbot" ]; then
    echo "  Warning: share/chatbot directory already exists, backing up..."
    mv "$OMD_ROOT/share/chatbot" "$OMD_ROOT/share/chatbot.backup.$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "$OMD_ROOT/share/chatbot"
cp -r "$REPO_ROOT/chatbot/templates" "$OMD_ROOT/share/chatbot/"
echo "  ✓ Templates copied to share/chatbot/"
echo

# Step 2: Install Python dependencies
echo "Step 2: Installing Python dependencies"
if [ ! -f "$REPO_ROOT/chatbot/requirements.txt" ]; then
    echo "  ERROR: requirements.txt not found at $REPO_ROOT/chatbot/requirements.txt"
    exit 1
fi

# Check Python version
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "  Python version: $PYTHON_VERSION"

# Install core dependencies (OMD pip auto-targets local/lib/python)
echo "  Installing core packages..."
python3 -m pip install -r "$REPO_ROOT/chatbot/requirements.txt"
echo "  ✓ Core dependencies installed"

# Install optional dependencies (LLM and MCP integration)
echo "  Installing optional dependencies (LLM + MCP)..."
if [ -f "$REPO_ROOT/chatbot/requirements-optional.txt" ]; then
    python3 -m pip install -r "$REPO_ROOT/chatbot/requirements-optional.txt"
    echo "  ✓ Optional dependencies installed (OpenAI, MCP)"
else
    echo "  Warning: requirements-optional.txt not found, skipping optional dependencies"
    echo "  You may need to manually install: pip install openai mcp httpx-sse"
fi
echo

# Step 3: Install OMD hooks
echo "Step 3: Installing OMD hooks"
if [ -d "$OMD_ROOT/lib/omd/hooks" ]; then
    cp "$REPO_ROOT/omd/hooks/CHATBOT" "$OMD_ROOT/lib/omd/hooks/"
    cp "$REPO_ROOT/omd/hooks/CHATBOT_TCP_PORT" "$OMD_ROOT/lib/omd/hooks/"
    chmod 755 "$OMD_ROOT/lib/omd/hooks/CHATBOT"
    chmod 755 "$OMD_ROOT/lib/omd/hooks/CHATBOT_TCP_PORT"
    echo "  ✓ Hooks installed in lib/omd/hooks/"
else
    echo "  Warning: lib/omd/hooks/ not found, skipping hook installation"
    echo "  You will need to manage configuration manually"
fi
echo

# Step 4: Create init.d script
echo "Step 4: Creating init.d script"
cp "$REPO_ROOT/omd/templates/chatbot.init" "$OMD_ROOT/etc/init.d/chatbot"
chmod 755 "$OMD_ROOT/etc/init.d/chatbot"
echo "  ✓ Init script created at etc/init.d/chatbot"
echo

# Step 5: Enable chatbot via OMD config (if hooks are installed)
echo "Step 5: Configuring chatbot via OMD"
if [ -f "$OMD_ROOT/lib/omd/hooks/CHATBOT" ]; then
    # Stop site to enable config changes
    echo "  Note: Site must be stopped to change configuration"
    echo "  Run these commands after installation:"
    echo "    omd stop"
    echo "    omd config set CHATBOT on"
    echo "    omd start"
    echo "  ✓ Hooks installed, use 'omd config' to manage chatbot"
else
    # Fallback: manual configuration
    echo "  Warning: Hooks not available, using manual configuration"
    if grep -q "CONFIG_CHATBOT=" "$OMD_ROOT/etc/omd/site.conf" 2>/dev/null; then
        echo "  Warning: Chatbot config already exists in site.conf"
    else
        echo "" >> "$OMD_ROOT/etc/omd/site.conf"
        cat "$REPO_ROOT/omd/templates/site.conf.snippet" >> "$OMD_ROOT/etc/omd/site.conf"
        echo "  ✓ OMD configuration added to site.conf (manual mode)"
    fi

    # Create default chatbot.conf
    mkdir -p "$OMD_ROOT/etc/chatbot"
    if [ ! -f "$OMD_ROOT/etc/chatbot/chatbot.conf" ]; then
        cp "$REPO_ROOT/omd/templates/chatbot.conf" "$OMD_ROOT/etc/chatbot/chatbot.conf"
    fi

    # Create Apache config from template
    if [ ! -f "$OMD_ROOT/etc/apache/conf.d/chatbot.conf" ]; then
        cp "$REPO_ROOT/omd/templates/chatbot.apache.conf" "$OMD_ROOT/etc/apache/conf.d/chatbot.conf"
        chmod 600 "$OMD_ROOT/etc/apache/conf.d/chatbot.conf"
    fi
fi
echo

# Step 6: Display next steps
echo "============================================"
echo "Installation complete!"
echo "============================================"
echo
echo "Next steps:"
echo
if [ -f "$OMD_ROOT/lib/omd/hooks/CHATBOT" ]; then
    echo "1. Enable chatbot via OMD config system:"
    echo "   omd stop"
    echo "   omd config set CHATBOT on"
    echo "   omd start"
    echo
    echo "2. Configure the chatbot (required for LLM features):"
    echo "   vi etc/chatbot/chatbot.conf"
    echo "   # Set OPENAI_API_KEY and other application settings"
    echo
    echo "3. Start the chatbot service:"
    echo "   etc/init.d/chatbot start"
    echo
    echo "4. Check service status:"
    echo "   omd config show | grep CHATBOT"
    echo "   curl http://127.0.0.1:\$CONFIG_CHATBOT_TCP_PORT/health"
    echo
    echo "5. Change port (optional):"
    echo "   omd stop"
    echo "   echo 'CHATBOT_TCP_PORT=8001' | omd config change"
    echo "   omd start"
else
    echo "1. Configure the chatbot (required for LLM features):"
    echo "   vi etc/chatbot/chatbot.conf"
    echo "   # Set OPENAI_API_KEY and other application settings"
    echo
    echo "2. Start the chatbot service:"
    echo "   omd start chatbot"
    echo
    echo "3. Reload Apache to pick up the new configuration:"
    echo "   omd reload apache"
    echo
    echo "4. Check service status:"
    echo "   omd status chatbot"
    echo "   curl http://127.0.0.1:8000/health"
fi
echo
echo "Access the chatbot in your browser:"
echo "   https://your-server/\$OMD_SITE/chatbot/"
echo "   (for this site: https://your-server/$OMD_SITE/chatbot/)"
echo
echo "For more information, see:"
echo "  - $REPO_ROOT/docs/OMD_INTEGRATION.md"
echo "  - $REPO_ROOT/docs/OMD_ACCESS_GUIDE.md"
echo
