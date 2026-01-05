# Naemon Demo Configuration

This directory contains demo Naemon configuration files for testing the chatbot's Thruk MCP integration.

## What's Included

**File**: `naemon-demo-hosts.cfg`

Demo monitoring setup with:
- **7 hosts**: 5 Windows servers + 2 Linux servers
- **Multiple services**: CPU, Memory, Disk, Database, Web, AD, Exchange
- **Host groups**: windows-servers, linux-servers, database-servers
- **Service groups**: database-services, web-services
- **Realistic states**:
  - 1 host DOWN (winsrv03)
  - 1 service CRITICAL (Database on winsrv03, linuxsrv02)
  - 2 services WARNING (Disk Space C:, Exchange queue)
  - Other services OK

## Installation

### On OMD Site

```bash
# As the site user
cd $OMD_ROOT

# Copy the demo config
cp /path/to/omd-mcp/omd/demo-config/naemon-demo-hosts.cfg etc/naemon/conf.d/

# Reload Naemon
omd reload naemon
```

### Quick Install Script

```bash
# From the omd-mcp repository
cat omd/demo-config/naemon-demo-hosts.cfg | \
  podman exec -i CONTAINER_ID su - SITE -c "cat > etc/naemon/conf.d/demo-hosts.cfg"

# Reload Naemon in container
podman exec CONTAINER_ID su - SITE -c "omd reload naemon"
```

## Testing with Chatbot

Once installed, you can ask the chatbot questions like:

1. **"Show me all hosts"**
   - Returns 7 hosts (5 Windows, 2 Linux)

2. **"Which hosts are down?"**
   - Should show winsrv03

3. **"What services are critical?"**
   - Should show Database Service on winsrv03 and linuxsrv02

4. **"Show me Windows servers"**
   - Returns all hosts in the windows-servers hostgroup

5. **"What's wrong with winsrv03?"**
   - Shows host DOWN + Database Service CRITICAL

6. **"Schedule downtime for winsrv03"**
   - Chatbot will use Thruk MCP to schedule downtime

7. **"Show database servers"**
   - Returns hosts in database-servers hostgroup

8. **"What services are in WARNING state?"**
   - Shows Disk Space C: and Exchange Services

## Customization

Edit `naemon-demo-hosts.cfg` to:
- Add more hosts/services
- Change states (OK=0, WARNING=1, CRITICAL=2, UNKNOWN=3)
- Modify check_dummy output messages
- Add more host/service groups

After changes:
```bash
omd reload naemon
```

## Realistic Demo Scenario

This configuration simulates a production environment:

**Infrastructure**:
- Domain Controller (winsrv01) - Active Directory
- File Server (winsrv02)
- Database Server (winsrv03) - **DOWN** with database issues
- Web Server (winsrv04)
- Exchange Server (winsrv05) - Mail queue warning
- Linux Web App (linuxsrv01)
- Linux Database (linuxsrv02) - Database connection issues

**Current Issues**:
1. winsrv03 host is DOWN
2. Database services failing on both DB servers
3. Disk space warning on all Windows servers (85% used)
4. Exchange mail queue building up (127 messages)

**Use Cases for Chatbot**:
- Query current problems
- Filter by severity/hostgroup
- Schedule maintenance windows
- Check specific server status
- List services by group
