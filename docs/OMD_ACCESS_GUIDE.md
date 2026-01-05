# Accessing the Chatbot in OMD

## Web Browser Access (Recommended)

### Steps to Access

1. **Open your web browser** and navigate to:
   ```
   https://localhost:8443/demo/chatbot/
   ```

2. **Login to Thruk**:
   - You'll be redirected to the Thruk login page
   - Username: `omdadmin`
   - Password: `omd`

3. **Access the chatbot**:
   - After successful login, you'll be redirected back to the chatbot
   - Your username (`omdadmin`) will be automatically set in the session
   - You can now interact with the chatbot

### What Happens Behind the Scenes

```
Browser Request
    ↓
Apache (port 8443) - SSL/TLS termination
    ↓
Thruk Cookie Auth - Validates session
    ↓
    ├─ No valid session? → Redirect to login.cgi
    │                       ↓
    │                    User logs in (omdadmin/omd)
    │                       ↓
    │                    Session cookie created
    │                       ↓
    │                    Redirect back to /demo/chatbot/
    │
    └─ Valid session? → Set REMOTE_USER from cookie
                          ↓
                       Set X-WEBAUTH-USER header
                          ↓
                       Proxy to chatbot backend (port 8000)
                          ↓
                       Chatbot creates session for user
                          ↓
                       Return HTML response
```

## Direct Backend Access (Testing Only)

For testing purposes, you can bypass Apache and access the backend directly:

```bash
# From within the OMD container
podman exec -it 9028c3a60a88 su - demo

# Test with curl (simulating authenticated user)
curl -s http://127.0.0.1:8000/ -H 'X-WEBAUTH-USER: omdadmin'

# Check health endpoint
curl -s http://127.0.0.1:8000/health
```

**Note**: Direct backend access bypasses authentication and is only for testing!

## API Access

For programmatic access to the chatbot API, you need a valid Thruk session cookie:

```bash
# Step 1: Login to Thruk (complex - requires handling CGI redirects)
# This is difficult with curl - use a proper HTTP client library

# Step 2: Extract thruk_auth cookie from response

# Step 3: Use cookie in subsequent requests
curl -sk \
  -H "Cookie: thruk_auth=YOUR_SESSION_COOKIE" \
  https://localhost:8443/demo/chatbot/api/sessions
```

**Recommendation**: For API access, consider using:
- Python `requests` library with session management
- Browser automation tools (Selenium, Playwright)
- Thruk's REST API authentication mechanisms

## Troubleshooting

### "302 Redirect to login.cgi"

**This is normal!** It means:
- Thruk authentication is working correctly
- You need to login through the web interface
- Once logged in, you'll get a session cookie for future requests

### Cannot Access from Browser

Check:
1. Container is running: `podman ps | grep omd`
2. Port is mapped: Should see `0.0.0.0:8443->5000/tcp`
3. Service is running: `podman exec 9028c3a60a88 su - demo -c "omd status chatbot"`
4. Apache is running: `podman exec 9028c3a60a88 su - demo -c "omd status apache"`

### SSL Certificate Warnings

The OMD container uses a self-signed certificate. In your browser:
- Click "Advanced" or "Show Details"
- Click "Proceed to localhost (unsafe)" or "Accept the Risk and Continue"
- This is safe for local development

## Security Notes

### Why Cookie Authentication?

Thruk's cookie authentication provides:
- **Single Sign-On**: One login for all OMD services
- **Session Management**: Automatic timeout and renewal
- **Security**: CSRF protection, secure cookies
- **User Context**: Authenticated username propagated to all services

### Authentication Flow

1. **First Visit**: No session → Redirect to login
2. **Login**: Credentials validated → Session cookie created
3. **Subsequent Visits**: Cookie validated → User identified → Request proxied
4. **Session Timeout**: Cookie expires → Redirect to login

### Header Propagation

The Apache configuration sets `X-WEBAUTH-USER` from different sources:

```apache
# Priority 1: Thruk cookie auth (most common)
RequestHeader set X-WEBAUTH-USER "%{REMOTE_USER}e" env=!IS_BASIC_AUTH

# Priority 2: HTTP Basic Auth (fallback)
RequestHeader set X-WEBAUTH-USER "%{PROXY_USER}s" env=IS_HTTPS
RequestHeader set X-WEBAUTH-USER "%{PROXY_USER}e" env=!IS_HTTPS
```

This ensures the chatbot always receives the authenticated username.

## Testing the Integration

### Quick Test (Backend)

```bash
# SSH into container
podman exec -it 9028c3a60a88 bash

# Switch to site user
su - demo

# Test backend directly
curl http://127.0.0.1:8000/health

# Expected output:
# {"status":"healthy","active_sessions":0,"timestamp":"..."}
```

### Full Test (Browser)

1. Open: https://localhost:8443/demo/chatbot/
2. Login with: omdadmin / omd
3. Verify: Chatbot interface loads
4. Check: Username shown in session info
5. Test: Send a message and receive response

### Session Test

```bash
# From OMD site user
curl -s http://127.0.0.1:8000/api/sessions \
  -H 'X-WEBAUTH-USER: omdadmin' | jq

# Should show session for omdadmin user
```

## URLs Reference

### External Access (from your workstation)

- **Chatbot**: https://localhost:8443/demo/chatbot/
- **Thruk**: https://localhost:8443/demo/thruk/
- **Health Check**: https://localhost:8443/demo/chatbot/health
  - Note: Currently requires authentication (see OMD_INTEGRATION.md for how to make it public)

### Internal Access (from within container)

- **Chatbot Backend**: http://127.0.0.1:8000/
- **Chatbot Health**: http://127.0.0.1:8000/health
- **Apache Frontend**: https://127.0.0.1:5000/demo/chatbot/

### API Endpoints (authenticated)

- **List Sessions**: https://localhost:8443/demo/chatbot/api/sessions
- **Get Session**: https://localhost:8443/demo/chatbot/api/sessions/{session_id}
- **SSE Stream**: https://localhost:8443/demo/chatbot/api/chat

## Next Steps

1. **Access the chatbot** through your browser at https://localhost:8443/demo/chatbot/
2. **Login** with the credentials provided
3. **Test the chat interface** by sending messages
4. **Verify session management** works correctly
5. **Check logs** if you encounter any issues: `tail -f var/log/chatbot.log`

For detailed configuration and troubleshooting, see `OMD_INTEGRATION.md`.
