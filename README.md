# MCP Chatbot with Thruk Integration

A chatbot application that integrates with Thruk monitoring system via Model Context Protocol (MCP).

## 🏗️ Architecture

- **Chatbot Service**: Web UI and LLM integration
- **Thruk MCP Service**: MCP server providing Thruk monitoring tools
- **Communication**: HTTP/Streamable HTTP between services

## 📋 Prerequisites

- Python 3.11+
- Podman or Docker
- Kubernetes (k3s) for production deployment

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
- `THRUK_BASE_URL`: Your Thruk server URL
- `OPENAI_API_KEY`: Your LLM API key
- `OPENAI_BASE_URL`: API endpoint (OpenAI, Anthropic, local, etc.)
- `OPENAI_MODEL`: Model to use (e.g., gpt-4, claude-3, etc.)

### 2. Run with Podman/Docker

```bash
# Build and start both services
podman-compose -f docker-compose-full.yml up -d

# View logs
podman-compose -f docker-compose-full.yml logs -f

# Access the chatbot
http://localhost:8000
```

### 3. Deploy to Kubernetes (k3s)

```bash
# 1. Configure environment (IMPORTANT!)
cp .env.example .env
nano .env  # Add your actual credentials

# 2. Build images
podman build -t chatbot:latest ./chatbot
podman build -t thruk-mcp:latest ./thruk_mcp

# 3. Load into k3s
./k3s-load-images.sh

# 4. Deploy (automatically creates secret from .env)
./k8s-deploy.sh deploy

# Access via NodePort
http://localhost:30800

# Update secrets if needed
./k8s-deploy.sh update-secrets
```

## 📁 Project Structure

```
.
├── chatbot/                    # Chatbot service
│   ├── chatbot.py             # Main application
│   ├── chatbot.json           # MCP configuration
│   ├── Dockerfile             # Container image
│   └── requirements.txt       # Dependencies
│
├── thruk_mcp/                 # Thruk MCP service
│   ├── thruk_mcp.py          # MCP server
│   ├── Dockerfile            # Container image
│   └── requirements.txt      # Dependencies
│
├── .env                       # Environment variables (DO NOT COMMIT)
├── .env.example              # Example configuration
├── docker-compose-full.yml   # Podman/Docker setup
├── kubernetes-deployment.yaml # Kubernetes manifests
├── k8s-deploy.sh            # Kubernetes helper
└── k3s-load-images.sh       # k3s image loader
```

## 🔧 Development

### Local Development

```bash
# Install dependencies
pip install -r chatbot/requirements.txt
pip install -r thruk_mcp/requirements.txt

# Run services locally
# Terminal 1: Start Thruk MCP
cd thruk_mcp
python thruk_mcp.py --listen 8001

# Terminal 2: Start Chatbot
cd chatbot
python chatbot.py
```

### Rebuild and Redeploy

#### Podman/Docker
```bash
# Rebuild images
podman-compose -f docker-compose-full.yml build

# Restart services
podman-compose -f docker-compose-full.yml up -d
```

#### Kubernetes
```bash
# Rebuild images
podman build -t chatbot:latest ./chatbot
podman build -t thruk-mcp:latest ./thruk_mcp

# Reload into k3s
./k3s-load-images.sh

# Restart deployment
./k8s-deploy.sh restart
```

## 📖 Available Tools

The Thruk MCP service provides these monitoring tools:

- `thruk_list_hosts` - List all monitored hosts
- `thruk_list_services` - List services for a host
- `thruk_list_hostgroups` - List host groups
- `thruk_list_servicegroups` - List service groups
- `thruk_get_host_details` - Get detailed host information
- `thruk_get_service_details` - Get detailed service information
- `thruk_schedule_downtime` - Schedule maintenance downtime
- `thruk_list_downtimes` - List active downtimes

## 🔒 Security

- **Never commit `.env`** - Contains secrets and API keys
- **Use `.env.example`** - Template for required configuration
- **Kubernetes secrets from .env** - `k8s-deploy.sh` creates secrets dynamically
- **No hardcoded secrets** - `kubernetes-deployment.yaml` contains no sensitive data
- **Non-root containers** - Both services run as non-root users
- **SSL verification** - Can be disabled for development (THRUK_VERIFY_SSL=false)

### How Secrets Work

**Podman/Docker**: Reads `.env` file directly via `env_file` directive

**Kubernetes**: `k8s-deploy.sh` creates a Kubernetes Secret from `.env`:
```bash
# Secret is created automatically on deploy
./k8s-deploy.sh deploy

# Update secrets after changing .env
./k8s-deploy.sh update-secrets
```

The `kubernetes-deployment.yaml` file contains **no hardcoded secrets** and is safe to commit.

## 🐛 Troubleshooting

### Podman/Docker

```bash
# View logs
podman-compose -f docker-compose-full.yml logs -f chatbot
podman-compose -f docker-compose-full.yml logs -f thruk-mcp

# Check container status
podman ps

# Restart services
podman-compose -f docker-compose-full.yml restart
```

### Kubernetes

```bash
# Check pod status
kubectl -n demodemo get pods

# View logs
./k8s-deploy.sh logs chatbot
./k8s-deploy.sh logs thruk-mcp

# Check deployment status
./k8s-deploy.sh status

# Describe pod for events
kubectl -n demodemo describe pod -l app=chatbot
```

## 📚 Documentation

- [Kubernetes Deployment Guide](KUBERNETES_DEPLOYMENT.md) - Detailed k8s setup
- [FastMCP Documentation](https://gofastmcp.com/) - MCP server framework
- [Thruk API Documentation](https://thruk.org/documentation/rest.html) - Thruk REST API

## 🤝 Contributing

1. Copy `.env.example` to `.env` with your credentials
2. Make changes in feature branch
3. Test with both Podman and Kubernetes
4. Ensure `.env` is in `.gitignore`
5. Submit pull request

## 📄 License

[Add your license here]
