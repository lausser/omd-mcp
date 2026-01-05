# OMD Hooks for Chatbot

This directory contains OMD hook scripts that integrate the chatbot into OMD's configuration management system.

## What are OMD Hooks?

OMD hooks are executable scripts that run when you use `omd config` commands. They enable OMD to:
- Validate configuration values
- Generate configuration files dynamically
- Manage service dependencies
- Provide a consistent interface for all services

## Hook Files

### CHATBOT

Main service hook that enables/disables the chatbot service.

**Usage**:
```bash
omd config set CHATBOT on   # Enable chatbot
omd config set CHATBOT off  # Disable chatbot
```

**What it does**:
- Creates `etc/chatbot/chatbot.conf` with default settings (if not exists)
- Creates/removes symlink: `etc/apache/conf.d/chatbot.conf` → `etc/chatbot/apache.conf`
- Manages Apache integration

**Hook interface**:
- `default`: Returns "off" (chatbot disabled by default)
- `choices`: Returns valid values ("on", "off")
- `set`: Performs actions when value changes

### CHATBOT_TCP_PORT

Port configuration hook for the chatbot service.

**Usage**:
```bash
omd config set CHATBOT_TCP_PORT 8001  # Change to port 8001
echo 'CHATBOT_TCP_PORT=8002' | omd config change  # Batch change
```

**What it does**:
- Validates requested port number
- Checks if port is already in use by another OMD site
- Automatically selects alternative port if requested port is taken
- Generates `etc/chatbot/apache.conf` with correct port configuration
- Updates ProxyPass directives for Apache

**Hook interface**:
- `default`: Returns "8000" (default port)
- `choices`: Accepts regex pattern "[1-9][0-9]{0,4}" (ports 1-99999)
- `set`: Validates port, generates Apache config
- `depends`: Only active when `CONFIG_CHATBOT=on`

## Installation

Hooks should be copied to `${OMD_ROOT}/lib/omd/hooks/`:

```bash
# Manual installation
cp CHATBOT ${OMD_ROOT}/lib/omd/hooks/
cp CHATBOT_TCP_PORT ${OMD_ROOT}/lib/omd/hooks/
chmod 755 ${OMD_ROOT}/lib/omd/hooks/CHATBOT*

# Or use the automated installer
cd /path/to/omd-mcp
./omd/install-chatbot.sh
```

## Configuration Workflow

### Initial Setup

```bash
# 1. Install hooks (via install-chatbot.sh or manually)

# 2. Stop site to enable configuration changes
omd stop

# 3. Enable chatbot
omd config set CHATBOT on
# This creates etc/chatbot/chatbot.conf and sets up Apache config

# 4. Customize application settings (optional)
vi etc/chatbot/chatbot.conf
# Set LLM_PROVIDER, OPENAI_API_KEY or GEMINI_API_KEY, etc.

# 5. Start site
omd start

# 6. Start chatbot service
etc/init.d/chatbot start
```

### Changing Port

```bash
# Stop site
omd stop

# Change port
echo 'CHATBOT_TCP_PORT=8001' | omd config change
# Hook regenerates etc/chatbot/apache.conf with new port

# Start site
omd start

# Restart chatbot on new port
etc/init.d/chatbot restart
```

### Viewing Configuration

```bash
# Show all chatbot-related config
omd config show | grep CHATBOT

# Output:
# CHATBOT: on
# CHATBOT_TCP_PORT: 8000
```

### Disabling Chatbot

```bash
# Stop site
omd stop

# Disable chatbot
omd config set CHATBOT off
# Removes Apache config symlink

# Start site
omd start
```

## How Hooks Work

### Port Selection Algorithm

The `CHATBOT_TCP_PORT` hook uses `$OMD_ROOT/lib/omd/port_is_used` to check if a port is available:

1. Check if requested port is used by another OMD site
2. If free, use requested port
3. If taken, find next available port and warn user
4. Return the final port number

This prevents port conflicts across multiple OMD sites.

### Apache Config Generation

The port hook generates `etc/chatbot/apache.conf` with:

```apache
<Location /${OMD_SITE}/chatbot>
    ProxyPass http://127.0.0.1:8000 retry=0 disablereuse=On
    ProxyPassReverse http://127.0.0.1:8000
    # ... authentication headers, etc.
</Location>
```

Port number is dynamically inserted when hook runs.

### Dependencies

The `CHATBOT_TCP_PORT` hook has a `depends` clause:
```bash
depends)
    [ "$CONFIG_CHATBOT" = on ]
;;
```

This ensures the port can only be configured when chatbot is enabled.

## Comparison with Manual Configuration

### With Hooks (Recommended)

✅ Automatic port conflict detection
✅ Dynamic Apache config generation
✅ Consistent with other OMD services
✅ Integrated with `omd config` commands
✅ Configuration validated by hooks

```bash
omd config set CHATBOT on
omd config set CHATBOT_TCP_PORT 8001
```

### Without Hooks (Fallback)

❌ Manual file editing required
❌ No port conflict detection
❌ Must manually update multiple files
❌ Risk of configuration errors

```bash
vi etc/omd/site.conf  # Add CONFIG_CHATBOT='on'
vi etc/chatbot/chatbot.conf  # Create manually
vi etc/apache/conf.d/chatbot.conf  # Create manually
```

## Hook Development Notes

### Testing Hooks

```bash
# Test default value
lib/omd/hooks/CHATBOT default

# Test choices
lib/omd/hooks/CHATBOT choices

# Test set (must stop site first)
omd stop
lib/omd/hooks/CHATBOT set on
omd start
```

### Hook Script Structure

All OMD hooks follow this pattern:

```bash
#!/bin/bash

# Alias: Human-readable name
# Menu: Category in omd config
# Description: Help text

case "$1" in
    default)
        # Return default value
        ;;
    choices)
        # Return valid values or regex pattern
        ;;
    set)
        # Perform actions when value changes
        # $2 contains the new value
        ;;
    depends)
        # Optional: define dependencies
        # Return 0 if dependencies met, 1 otherwise
        ;;
esac
```

### Multi-Platform Support

The hooks detect Apache module paths for both Debian and RHEL-based systems:

```bash
<IfFile "/usr/lib/apache2/modules/mod_proxy.so">
    LoadModule proxy_module /usr/lib/apache2/modules/mod_proxy.so
</IfFile>
<IfFile "/usr/lib64/httpd/modules/mod_proxy.so">
    LoadModule proxy_module /usr/lib64/httpd/modules/mod_proxy.so
</IfFile>
```

This ensures the generated Apache config works on all platforms.

## Troubleshooting

### Hook not appearing in `omd config show`

```bash
# Check if hook file exists and is executable
ls -la $OMD_ROOT/lib/omd/hooks/CHATBOT*

# Should show:
# -rwxr-xr-x ... CHATBOT
# -rwxr-xr-x ... CHATBOT_TCP_PORT

# Fix permissions if needed
chmod 755 $OMD_ROOT/lib/omd/hooks/CHATBOT*
```

### Cannot change config while site is running

```bash
# Error: "Cannot change config variables while site is running"

# Solution: Stop site first
omd stop
omd config set CHATBOT on
omd start
```

### Port conflict error

```bash
# "Chatbot port 8000 is in use. I've chosen 8001 instead."

# This is normal - another site is using port 8000
# The hook automatically selected an available port (8001)

# To use a specific port, try a different number
omd config set CHATBOT_TCP_PORT 8002
```

### Apache config not updating

```bash
# Check if symlink exists
ls -la etc/apache/conf.d/chatbot.conf

# Should show:
# lrwxrwxrwx ... chatbot.conf -> /omd/sites/SITE/etc/chatbot/apache.conf

# If broken, re-enable chatbot
omd stop
omd config set CHATBOT off
omd config set CHATBOT on
omd start
```

## See Also

- [OMD Configuration System](https://omdistro.org/)
- [../README.md](../README.md) - General OMD integration guide
- [../../docs/OMD_INTEGRATION.md](../../docs/OMD_INTEGRATION.md) - Detailed integration docs
