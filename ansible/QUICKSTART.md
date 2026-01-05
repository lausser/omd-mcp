# Quick Start: Install Chatbot with Ansible

## 1. Run Playbook on Localhost

```bash
# Option A: Using inventory file (recommended)
cd /path/to/omd-mcp
sudo ansible-playbook -i ansible/inventory ansible/install-chatbot.yml

# Option B: Without inventory file
sudo ansible-playbook -i localhost, -c local ansible/install-chatbot.yml

# If already running as root
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml
```

## 2. For Remote Server

```bash
# Edit inventory file
cat > ansible/inventory <<EOF
[omd_servers]
omd-server ansible_host=192.168.1.100 ansible_user=root
EOF

# Run playbook
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml
```

## 3. Verify Installation

```bash
ansible-playbook -i inventory install-chatbot.yml --tags verify
```

## 4. Create Test Site

```bash
# On the OMD server
omd create testchatbot
su - testchatbot

# Enable chatbot
omd stop
omd config set CHATBOT on
omd start

# Install Python dependencies
cd etc/chatbot
./install-deps.sh

# Configure API keys
vi etc/chatbot/chatbot.conf
# Set LLM_PROVIDER (openai or gemini)
# For OpenAI: Set OPENAI_API_KEY, OPENAI_BASE_URL, etc.
# For Gemini: Set GEMINI_API_KEY, GEMINI_MODEL, etc.

# Start chatbot
etc/init.d/chatbot start

# Check status
curl http://127.0.0.1:8000/health
```

## 5. Access Chatbot

Open browser: `https://your-server/testchatbot/chatbot/`

## What Gets Installed

```
/omd/versions/default/
├── lib/
│   ├── omd/hooks/
│   │   ├── CHATBOT           ← Config management hooks
│   │   └── CHATBOT_TCP_PORT
│   └── python/chatbot/       ← Shared Python code (all sites)
│       ├── __init__.py
│       ├── chatbot.py
│       └── session_manager.py
├── share/chatbot/            ← Shared templates (all sites)
│   └── templates/
│       └── index.html
└── skel/etc/                 ← Config templates for new sites
    ├── chatbot/
    │   ├── chatbot.conf       ← Edit this
    │   ├── install-deps.sh    ← Run this to install Python deps
    │   ├── requirements.txt
    │   └── README
    ├── init.d/chatbot         ← Service init script (0755)
    └── rc.d/91-chatbot -> ../init.d/chatbot
```

**Note**: Code and templates are shared across all sites via symlinks.
Each site has its own config in `etc/chatbot/` and packages in `local/lib/python/`.

## Tags Reference

```bash
# Install only hooks
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml --tags hooks

# Install only shared code and templates
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml --tags shared

# Install only skel files (config templates)
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml --tags skel

# Update code (affects all sites immediately - just restart)
ansible-playbook -i ansible/inventory ansible/install-chatbot.yml --tags code
```

## For Container Testing

```bash
# Get container ID
CONTAINER_ID=$(podman ps | grep omd | awk '{print $1}')

# Run playbook
ansible-playbook install-chatbot.yml \
  -e "ansible_connection=podman" \
  -e "ansible_host=$CONTAINER_ID" \
  -i localhost,
```
