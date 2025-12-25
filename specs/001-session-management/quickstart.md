# Quickstart: Session Management Local Development

**Feature**: 001-session-management
**Last Updated**: 2025-12-16

## Prerequisites

- Python 3.11+
- Podman or Docker
- OMD (Open Monitoring Distribution) container for testing (optional)

## Initial Setup

### 1. Install Dependencies

```bash
# Navigate to project root
cd /home/lausser/git/omd-mcp

# Install chatbot dependencies
pip install -r chatbot/requirements.txt

# Install thruk_mcp dependencies (if testing MCP integration)
pip install -r thruk_mcp/requirements.txt

# Install test dependencies
pip install -r requirements-dev.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add session-specific configuration
nano .env
```

Add these session management variables to `.env`:

```bash
# Session Management Configuration
SESSION_TIMEOUT_MINUTES=15
DEFAULT_USERNAME=chatuser
SESSION_CLEANUP_INTERVAL_SECONDS=60

# Testing Configuration (for development)
# Reduce timeout for faster testing (optional)
# SESSION_TIMEOUT_MINUTES=2  # 2 minutes for quick tests
```

## Running Services

### Option 1: Containerized Services (Recommended)

Run both services in containers using Podman Compose:

```bash
# Ensure .env is configured
cp .env.example .env
nano .env  # Add your credentials

# Build and start both services
podman compose up -d

# View logs
podman compose logs -f

# Access chatbot
open http://localhost:8000

# Check service status
podman compose ps

# Stop services
podman compose down
```

**Expected Behavior**:
- Chatbot runs on port 8000
- MCP server runs on port 8001
- Services communicate over internal network
- Username displays as "chatuser" (default for standalone mode)
- Session cookie set automatically
- 15-minute inactivity timeout

### Option 2: Standalone Chatbot (No Apache)

Run the chatbot service locally without containers or Apache reverse proxy for quick testing:

```bash
# Terminal 1: Start chatbot service
cd chatbot
python chatbot.py

# Access chatbot
open http://localhost:8000
```

**Expected Behavior**:
- Username displays as "chatuser" (default for standalone mode)
- Session cookie set automatically
- 15-minute inactivity timeout

### Option 2: With OMD Test Container

Run the full stack with OMD container for Thruk MCP testing:

```bash
# Terminal 1: Start OMD container with Thruk
podman run -d \
  --name thruk-test \
  -p 8080:80 \
  -e OMD_SITE=test \
  consol/omd-labs-ubuntu:latest

# Wait for OMD to start (check logs)
podman logs -f thruk-test

# Terminal 2: Start Thruk MCP server
cd thruk_mcp
export THRUK_BASE_URL=http://localhost:8080/test/thruk
export THRUK_API_KEY=your_test_api_key
python thruk_mcp.py --listen 8001

# Terminal 3: Start chatbot service
cd chatbot
python chatbot.py

# Access chatbot
open http://localhost:8000
```

**Expected Behavior**:
- Chatbot connects to Thruk MCP on port 8001
- MCP connects to OMD Thruk API
- Username "chatuser" passed through entire chain
- Thruk API returns hosts/services visible to "chatuser"

### Option 3: Behind Simulated Apache Proxy

Test X-WEBAUTH-USER header handling with a simple proxy:

```bash
# Install nginx or use Python proxy script
# Create simple proxy config to add X-WEBAUTH-USER header

# Python proxy example (save as proxy.py):
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def proxy(request: Request, path: str):
    # Simulate Apache setting X-WEBAUTH-USER
    headers = dict(request.headers)
    headers["X-WEBAUTH-USER"] = "testuser"  # Hardcoded for testing

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=f"http://localhost:8000/{path}",
            headers=headers,
            content=await request.body()
        )
        return response.content

# Run proxy on port 9000
uvicorn proxy:app --port 9000

# Access via proxy
open http://localhost:9000
```

**Expected Behavior**:
- Username displays as "testuser" (from X-WEBAUTH-USER header)
- Session isolated per username
- Multiple usernames = multiple independent sessions

## Testing Session Features

### Test 1: Username Display (FR-004)

```bash
# Open chatbot UI
open http://localhost:8000

# Verify username appears in UI
# For standalone: should show "chatuser"
# For proxy: should show injected username
```

**Expected**: Username visible in top-right or header of chatbot UI

### Test 2: Session Timeout (FR-007, FR-008, FR-009)

```bash
# Method 1: Wait 15 minutes (production timeout)
# - Open chatbot
# - Wait 15 minutes without interaction
# - Observe:
#   - Submit buttons disabled
#   - Message: "Session has ended after inactivity"

# Method 2: Use reduced timeout for testing
# Set SESSION_TIMEOUT_MINUTES=1 in .env
# Restart chatbot
# Wait 1 minute
# Observe same behavior

# Method 3: Use automated test
pytest tests/chatbot/test_timeout.py -v
```

**Expected**:
- After timeout: UI shows expiration message
- Submit buttons disabled
- Cannot send new messages

### Test 3: Session Isolation (FR-014)

```bash
# Open two browser windows (different usernames via proxy)
# Window 1: http://localhost:9000 (username: "alice")
# Window 2: Configure proxy to inject "bob"

# In Window 1: Send message "Hello from Alice"
# In Window 2: Send message "Hello from Bob"

# Verify:
# - Window 1 only sees Alice's messages
# - Window 2 only sees Bob's messages
# - Sessions independent
```

### Test 4: Resource Cleanup (FR-010, FR-011, FR-012)

```bash
# Run test with resource monitoring
pytest tests/chatbot/test_cleanup.py -v

# Or monitor manually:
# 1. Start chatbot with debug logging
# 2. Create session
# 3. Wait for timeout
# 4. Check logs for cleanup events:
#    - "Closing MCP connection for session {id}"
#    - "Closing LLM connection for session {id}"
#    - "Session {id} cleaned up"
```

### Test 5: Username Propagation to MCP (FR-005, FR-015, FR-016)

```bash
# Run integration test
pytest tests/integration/test_username_propagation.py -v

# Manual verification:
# 1. Enable debug logging in thruk_mcp service
# 2. Send chat message that triggers MCP tool
#    Example: "Show me all database hosts"
# 3. Check thruk_mcp logs for:
#    "Tool thruk_list_hosts called with username=chatuser"
# 4. Verify Thruk API request includes username
```

## Development Workflow

### Making Changes

1. **Modify session logic** in `chatbot/session_manager.py`
2. **Run tests** to verify changes:
   ```bash
   pytest tests/chatbot/ -v
   ```
3. **Test manually** in browser
4. **Update data model** in `specs/001-session-management/data-model.md` if schema changes

### Running Tests

```bash
# Run all session management tests
pytest tests/chatbot/ tests/integration/ -v

# Run specific test file
pytest tests/chatbot/test_session_manager.py -v

# Run with coverage
pytest --cov=chatbot tests/ --cov-report=html

# Run timeout tests with fast mode (mocked time)
pytest tests/chatbot/test_timeout.py -v  # Uses freezegun, instant results
```

### Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python chatbot/chatbot.py

# Check session state
# Add debug endpoint (temporary):
@app.get("/debug/sessions")
def debug_sessions():
    return {
        "active_sessions": len(session_store.sessions),
        "sessions": [
            {
                "id": s.session_id[:8],
                "username": s.username,
                "age_seconds": (now() - s.created_at).total_seconds(),
                "idle_seconds": (now() - s.last_activity).total_seconds()
            }
            for s in session_store.sessions.values()
        ]
    }
```

## Common Issues

### Issue: "Session expired" immediately

**Cause**: System clock or timeout configuration issue
**Fix**:
```bash
# Check SESSION_TIMEOUT_MINUTES in .env
# Ensure it's set to 15 (or higher for testing)
grep SESSION_TIMEOUT_MINUTES .env

# Check system time
date

# Restart chatbot service
```

### Issue: Username shows "chatuser" when it shouldn't

**Cause**: X-WEBAUTH-USER header not reaching chatbot
**Fix**:
```bash
# Verify header in request
curl -H "X-WEBAUTH-USER: testuser" http://localhost:8000

# Check chatbot logs for header extraction
# Should see: "Extracted username from header: testuser"

# If using proxy, verify proxy is forwarding headers
```

### Issue: MCP tools not receiving username

**Cause**: MCP client not passing username parameter
**Fix**:
```bash
# Check MCP tool invocation in chatbot
# Should include: await mcp_client.call_tool("thruk_list_hosts", {"username": session.username})

# Verify thruk_mcp logs show username parameter
# Should see: "Tool called with username={value}"
```

## Next Steps

After local testing passes:

1. **Run full test suite**: `pytest tests/`
2. **Build Docker images**: `podman build -t chatbot:latest ./chatbot`
3. **Deploy to Kubernetes**: Follow main README deployment instructions
4. **Test in production-like environment** with real Apache proxy

## Useful Commands

```bash
# Clean up test sessions
rm -rf /tmp/session_test_*

# Reset test database (OMD)
podman exec thruk-test omd restart test

# View real-time logs
tail -f chatbot/logs/session.log

# Monitor session cleanup
watch -n 5 'curl -s http://localhost:8000/debug/sessions | jq'
```
