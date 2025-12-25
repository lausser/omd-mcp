# Thruk MCP Tool Extensions for Session Management

**Feature**: 001-session-management
**Component**: Thruk MCP Server
**Changes**: Add `username` parameter to all existing MCP tools

## Overview

All Thruk MCP tools must accept an optional `username` parameter that is passed to the Thruk API for authorization enforcement. This enables per-user privilege enforcement based on Thruk's internal authorization rules.

## Parameter Specification

**Parameter Name**: `username`
**Type**: `string`
**Required**: No (defaults to "chatuser" if not provided)
**Description**: Authenticated username from the chatbot session, used by Thruk API to enforce per-user privileges

## Affected Tools

All existing Thruk MCP tools require this parameter addition:

### Listing Tools

#### thruk_list_hosts
```python
@mcp.tool()
async def thruk_list_hosts(username: str = "chatuser") -> List[Host]:
    """
    List all monitored hosts visible to the specified user.

    Args:
        username: Authenticated user (default: "chatuser")

    Returns:
        List of hosts the user is authorized to view
    """
    # Pass username to Thruk API for authorization
    response = await thruk_api.get(
        "/hosts",
        params={"username": username}
    )
    return response.json()
```

#### thruk_list_services
```python
@mcp.tool()
async def thruk_list_services(
    hostname: str,
    username: str = "chatuser"
) -> List[Service]:
    """
    List services for a specific host.

    Args:
        hostname: Target host name
        username: Authenticated user (default: "chatuser")

    Returns:
        List of services for the host that user can view
    """
    response = await thruk_api.get(
        f"/services/{hostname}",
        params={"username": username}
    )
    return response.json()
```

#### thruk_list_hostgroups
```python
@mcp.tool()
async def thruk_list_hostgroups(username: str = "chatuser") -> List[Hostgroup]:
    """List all hostgroups visible to the user."""
    response = await thruk_api.get(
        "/hostgroups",
        params={"username": username}
    )
    return response.json()
```

#### thruk_list_servicegroups
```python
@mcp.tool()
async def thruk_list_servicegroups(username: str = "chatuser") -> List[Servicegroup]:
    """List all servicegroups visible to the user."""
    response = await thruk_api.get(
        "/servicegroups",
        params={"username": username}
    )
    return response.json()
```

#### thruk_list_downtimes
```python
@mcp.tool()
async def thruk_list_downtimes(username: str = "chatuser") -> List[Downtime]:
    """
    List active downtimes with comments.

    Args:
        username: Authenticated user (default: "chatuser")

    Returns:
        List of downtimes the user is authorized to view
    """
    response = await thruk_api.get(
        "/downtimes",
        params={"username": username}
    )
    return response.json()
```

### Downtime Management Tools

#### thruk_schedule_host_downtime
```python
@mcp.tool()
async def thruk_schedule_host_downtime(
    hostname: str,
    duration_minutes: int,
    comment: str,
    include_services: bool = False,
    username: str = "chatuser"
) -> Dict[str, Any]:
    """
    Schedule downtime for a host (optionally including its services).

    Args:
        hostname: Target host
        duration_minutes: Downtime duration
        comment: Reason for downtime
        include_services: Also schedule downtime for host's services
        username: Authenticated user (default: "chatuser")

    Returns:
        Downtime creation result

    Raises:
        PermissionError: If user not authorized to schedule downtime for this host
    """
    response = await thruk_api.post(
        "/downtimes/host",
        json={
            "hostname": hostname,
            "duration": duration_minutes,
            "comment": comment,
            "include_services": include_services,
            "username": username  # Authorization enforcement
        }
    )
    return response.json()
```

#### thruk_schedule_service_downtime
```python
@mcp.tool()
async def thruk_schedule_service_downtime(
    hostname: str,
    service_description: str,
    duration_minutes: int,
    comment: str,
    username: str = "chatuser"
) -> Dict[str, Any]:
    """Schedule downtime for a specific service."""
    response = await thruk_api.post(
        "/downtimes/service",
        json={
            "hostname": hostname,
            "service_description": service_description,
            "duration": duration_minutes,
            "comment": comment,
            "username": username
        }
    )
    return response.json()
```

#### thruk_schedule_hostgroup_downtime
```python
@mcp.tool()
async def thruk_schedule_hostgroup_downtime(
    hostgroup: str,
    duration_minutes: int,
    comment: str,
    username: str = "chatuser"
) -> Dict[str, Any]:
    """
    Schedule downtime for all hosts in a hostgroup.

    Args:
        hostgroup: Target hostgroup name
        duration_minutes: Downtime duration
        comment: Reason for downtime
        username: Authenticated user (default: "chatuser")

    Returns:
        Bulk downtime creation result

    Raises:
        PermissionError: If user not authorized for any hosts in the group
    """
    response = await thruk_api.post(
        "/downtimes/hostgroup",
        json={
            "hostgroup": hostgroup,
            "duration": duration_minutes,
            "comment": comment,
            "username": username
        }
    )
    return response.json()
```

#### thruk_schedule_servicegroup_downtime
```python
@mcp.tool()
async def thruk_schedule_servicegroup_downtime(
    servicegroup: str,
    duration_minutes: int,
    comment: str,
    username: str = "chatuser"
) -> Dict[str, Any]:
    """Schedule downtime for all services in a servicegroup."""
    response = await thruk_api.post(
        "/downtimes/servicegroup",
        json={
            "servicegroup": servicegroup,
            "duration": duration_minutes,
            "comment": comment,
            "username": username
        }
    )
    return response.json()
```

## Backward Compatibility

The `username` parameter is **optional** with a default value of `"chatuser"`. This ensures:

1. **Existing MCP clients** without session management continue to work (using default username)
2. **New chatbot sessions** pass authenticated username for proper authorization
3. **No breaking changes** to MCP tool schemas

## Thruk API Authorization

The Thruk API is responsible for enforcing authorization based on the provided username:

1. Validate that `username` exists in Thruk's user database
2. Check user's contact permissions (which hosts/services they can view/manage)
3. Return 403 Forbidden if user lacks permissions for requested resource
4. Filter listing results to only show authorized resources

## Testing Strategy

**Unit Tests** (thruk_mcp service):
```python
def test_thruk_list_hosts_with_username():
    """Verify username is passed to Thruk API."""
    result = await thruk_list_hosts(username="alice")
    assert api_mock.last_request.params["username"] == "alice"

def test_thruk_schedule_downtime_authorization():
    """Verify authorization error if user lacks permissions."""
    with pytest.raises(PermissionError):
        await thruk_schedule_host_downtime(
            hostname="prod-db-01",
            duration_minutes=60,
            comment="Maintenance",
            username="unauthorized_user"
        )
```

**Integration Tests** (chatbot ↔ thruk_mcp):
```python
async def test_username_propagation_from_session():
    """Verify session username reaches Thruk MCP tools."""
    # Create session with username "bob"
    session = create_session("bob")

    # Send chat request that triggers MCP tool
    response = await client.post(
        "/api/chat",
        json={"message": "list all hosts"},
        cookies={"session_id": session.session_id}
    )

    # Verify MCP tool was called with correct username
    assert mcp_tool_calls[0].parameters["username"] == "bob"
```

## Implementation Notes

1. **FastMCP SDK**: Use FastMCP's parameter validation to ensure `username` is a non-empty string
2. **Logging**: Log username with each Thruk API call for audit trail
3. **Error Handling**: Translate Thruk API 403 errors to user-friendly messages
4. **Redaction**: Ensure API keys/tokens are redacted from logs, but username is safe to log
