# Ansible Playbooks for OMD Chatbot

This directory contains Ansible playbooks to install the chatbot into OMD as a system-wide component.

## Overview

The playbook installs chatbot files into `/omd/versions/default/` so that:
- All new OMD sites automatically get chatbot files
- Existing sites can enable chatbot via `omd config set CHATBOT on`
- Each site manages its own Python dependencies locally

## Directory Structure

```
ansible/
├── install-chatbot.yml          # Main playbook
├── inventory.example            # Example inventory file
├── roles/
│   └── chatbot/
│       ├── tasks/
│       │   ├── main.yml         # Main task orchestrator
│       │   ├── install-hooks.yml    # Install OMD hooks
│       │   ├── install-skel.yml     # Install skel files
│       │   └── verify.yml       # Verification tasks
│       └── templates/
│           └── install-deps.sh.j2   # Dependency installer template
└── README.md                    # This file
```

## What Gets Installed

### OMD Hooks (System-wide)
```
/omd/versions/default/lib/omd/hooks/
├── CHATBOT               # Enable/disable hook
└── CHATBOT_TCP_PORT      # Port configuration hook
```

### Skel Files (Copied to each site)
```
/omd/versions/default/skel/
├── etc/
│   ├── chatbot/
│   │   ├── chatbot.conf          # Application config template
│   │   ├── requirements.txt      # Python dependencies
│   │   ├── install-deps.sh       # Dependency installer script
│   │   └── README                # Documentation
│   ├── init.d/
│   │   └── chatbot               # Init script
│   └── rc.d/
│       └── chatbot -> ../init.d/chatbot
└── local/
    └── lib/
        └── chatbot/              # Application code
            ├── __init__.py
            ├── chatbot.py
            ├── session_manager.py
            └── templates/
                └── index.html
```

## Prerequisites

- Ansible 2.9 or later
- OMD installed on target server
- Root access to target server
- This repository available on Ansible controller

## Quick Start

### 1. Create Inventory

```bash
cp inventory.example inventory

# Edit inventory to add your OMD servers
vi inventory
```

Example inventory:
```ini
[omd_servers]
omd-prod ansible_host=192.168.1.100 ansible_user=root

[omd_servers:vars]
omd_version=default
```

### 2. Test Connection

```bash
ansible -i inventory omd_servers -m ping
```

### 3. Run Playbook

```bash
# Install everything
ansible-playbook -i inventory install-chatbot.yml

# Install only hooks
ansible-playbook -i inventory install-chatbot.yml --tags hooks

# Install only skel files
ansible-playbook -i inventory install-chatbot.yml --tags skel

# Verify installation
ansible-playbook -i inventory install-chatbot.yml --tags verify
```

### 4. For Local Container Testing

```bash
# If testing on local Podman container
ansible-playbook -i inventory install-chatbot.yml \
  -e "ansible_connection=docker" \
  -e "ansible_host=CONTAINER_ID"
```

## Post-Installation (On OMD Server)

### For New Sites

When you create a new OMD site, chatbot files are automatically copied:

```bash
# Create site
omd create mysite
su - mysite

# Enable chatbot
omd stop
omd config set CHATBOT on
omd start

# Install Python dependencies
cd etc/chatbot
./install-deps.sh

# Configure (set API keys, etc.)
vi etc/chatbot/chatbot.conf

# Start chatbot
etc/init.d/chatbot start

# Access at: https://your-server/mysite/chatbot/
```

### For Existing Sites

```bash
# Switch to site user
su - existingsite

# Copy chatbot files from skel manually
cp -r /omd/versions/default/skel/local/lib/chatbot local/lib/
cp -r /omd/versions/default/skel/etc/chatbot etc/
cp /omd/versions/default/skel/etc/init.d/chatbot etc/init.d/
ln -s ../init.d/chatbot etc/rc.d/chatbot

# Enable via config
omd stop
omd config set CHATBOT on
omd start

# Install dependencies
cd etc/chatbot
./install-deps.sh

# Start chatbot
etc/init.d/chatbot start
```

## Playbook Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `omd_version` | `default` | OMD version to install into |
| `omd_root` | `/omd/versions/{{ omd_version }}` | OMD version root path |
| `chatbot_repo` | `{{ playbook_dir }}/..` | Path to chatbot repository |

### Override Variables

```bash
# Install to specific OMD version
ansible-playbook -i inventory install-chatbot.yml -e "omd_version=5.30"

# Use different chatbot source
ansible-playbook -i inventory install-chatbot.yml -e "chatbot_repo=/path/to/repo"
```

## Tags

| Tag | Description |
|-----|-------------|
| `hooks` | Install only OMD hooks |
| `skel` | Install only skel files |
| `code` | Update only chatbot application code |
| `config` | Update only configuration templates |
| `deps` | Update only dependency files |
| `init` | Update only init scripts |
| `docs` | Update only documentation |
| `verify` | Run verification checks (use with `--tags verify`) |

## Updating Existing Installation

```bash
# Update hooks only
ansible-playbook -i inventory install-chatbot.yml --tags hooks

# Update application code only
ansible-playbook -i inventory install-chatbot.yml --tags code

# Update everything
ansible-playbook -i inventory install-chatbot.yml
```

**Note**: Updates to skel files only affect **new sites**. Existing sites need manual updates.

## Troubleshooting

### Verify Installation

```bash
ansible-playbook -i inventory install-chatbot.yml --tags verify
```

### Check Hooks

```bash
# On OMD server
ls -la /omd/versions/default/lib/omd/hooks/CHATBOT*

# Test hook
su - mysite
/omd/versions/default/lib/omd/hooks/CHATBOT default
```

### Check Skel Files

```bash
# On OMD server
ls -la /omd/versions/default/skel/etc/chatbot/
ls -la /omd/versions/default/skel/local/lib/chatbot/
```

### Check Site Installation

```bash
# On OMD server
su - mysite
omd config show | grep CHATBOT
ls -la etc/chatbot/
ls -la local/lib/chatbot/
```

### Python Dependencies

```bash
# Check if dependencies are installed
python3 -m pip list | grep -E "fastapi|uvicorn|jinja2"

# Reinstall dependencies
cd $OMD_ROOT/etc/chatbot
./install-deps.sh
```

## Platform-Specific Notes

### Debian/Ubuntu

- Apache modules: `/usr/lib/apache2/modules/`
- Works with Python 3.11+ (Debian 12+)

### RHEL/Rocky Linux

- Apache modules: `/usr/lib64/httpd/modules/`
- Python 3.9 on Rocky 9 (limited MCP support)
- Python 3.11+ on Rocky 10 (full support)

The hooks and configuration files auto-detect the correct paths.

## Security Considerations

### File Permissions

The playbook sets:
- Hooks: `0755` (executable by all, writable by root)
- Skel files: `0644` (readable by all, writable by root)
- Init scripts: `0755` (executable)
- Directories: `0755`

### Site Isolation

Each OMD site:
- Runs as its own user
- Has isolated Python environment (`local/lib/python`)
- Has isolated configuration (`etc/chatbot/chatbot.conf`)
- Cannot access other sites' data

### Sensitive Data

API keys and tokens are stored in `etc/chatbot/chatbot.conf`:
- File is owned by site user
- Should have restrictive permissions (`0600`)
- Not included in backups by default

## Future: MCP Server Playbook

A similar playbook for the Thruk MCP server will be created:

```
ansible/
├── install-mcp.yml              # MCP server playbook
└── roles/
    └── thruk-mcp/
        ├── tasks/
        └── templates/
```

This will install:
- `/omd/versions/default/lib/omd/hooks/THRUK_MCP*`
- `/omd/versions/default/skel/etc/thruk-mcp/`
- `/omd/versions/default/skel/local/lib/thruk-mcp/`

## See Also

- [../omd/README.md](../omd/README.md) - Site-level installation guide
- [../omd/hooks/README.md](../omd/hooks/README.md) - OMD hooks documentation
- [../docs/OMD_INTEGRATION.md](../docs/OMD_INTEGRATION.md) - Integration details
