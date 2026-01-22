"""
Thruk MCP Server - Stdio-based MCP Server

This is a stdio-based MCP server that provides Thruk monitoring API access.
The chatbot spawns this as a subprocess and communicates via stdin/stdout.
"""

import os
import sys
import asyncio
import logging
import warnings
from typing import Any
from dotenv import load_dotenv
from fastmcp import FastMCP
import httpx

# Suppress deprecation warnings from third-party dependencies
# jsonpath_ng has invalid escape sequences that will be fixed in their next release
warnings.filterwarnings("ignore", category=DeprecationWarning, module="jsonpath_ng")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Thruk MCP Server")

# Thruk API configuration with OMD auto-configuration
OMD_ROOT = os.getenv("OMD_ROOT", "")
OMD_SITE = os.getenv("OMD_SITE", "")

# Auto-configure THRUK_BASE_URL if in OMD environment
THRUK_BASE_URL = os.getenv("THRUK_BASE_URL", "")
if not THRUK_BASE_URL and OMD_ROOT:
    # OMD environment: use local Thruk installation via HTTPS to avoid redirect issues
    # Note: SSL verification is disabled via THRUK_VERIFY_SSL=false for self-signed certs
    THRUK_BASE_URL = (
        f"https://127.0.0.1/{OMD_SITE}/thruk" if OMD_SITE else "https://127.0.0.1/thruk"
    )
    logger.info(f"Auto-configured THRUK_BASE_URL: {THRUK_BASE_URL}")

# THRUK_API_KEY can be either:
# - The secret.key from var/thruk/secret.key (allows auth as any user via X-Thruk-Auth-User)
# - An individual API key created via 'thruk apikey create' (user-specific)
# For chatbot use, secret.key is preferred to support multi-user sessions
THRUK_API_KEY = os.getenv("THRUK_API_KEY", "")

# Auto-load secret.key if in OMD environment and API key not set
if not THRUK_API_KEY and OMD_ROOT:
    secret_key_path = os.path.join(OMD_ROOT, "var", "thruk", "secret.key")
    if os.path.exists(secret_key_path):
        try:
            with open(secret_key_path, "r") as f:
                THRUK_API_KEY = f.read().strip()
            logger.info(f"Auto-loaded THRUK_API_KEY from {secret_key_path}")
        except Exception as e:
            logger.warning(f"Failed to auto-load secret.key: {e}")

THRUK_VERIFY_SSL = os.getenv("THRUK_VERIFY_SSL", "true").lower() == "true"

# Log configuration status at startup
logger.info(f"Thruk MCP Server starting...")
logger.info(f"  THRUK_BASE_URL: {THRUK_BASE_URL if THRUK_BASE_URL else 'NOT SET'}")
logger.info(f"  THRUK_API_KEY: {'SET' if THRUK_API_KEY else 'NOT SET'}")
logger.info(f"  THRUK_VERIFY_SSL: {THRUK_VERIFY_SSL}")
logger.info(
    f"  OMD_ROOT: {OMD_ROOT if OMD_ROOT else 'NOT SET (not in OMD environment)'}"
)


# =============================================================================
# Helper Functions
# =============================================================================


def filter_sensitive_data(data: Any) -> Any:
    """
    Recursively filter out sensitive information from API responses.

    Removes custom variables and fields containing passwords, secrets, or keys.

    Args:
        data: Data structure to filter (dict, list, or primitive)

    Returns:
        Filtered data with sensitive fields removed
    """
    if isinstance(data, dict):
        filtered = {}
        for key, value in data.items():
            # Skip custom variables starting with _ that might contain sensitive data
            key_lower = key.lower()
            if any(
                sensitive in key_lower
                for sensitive in [
                    "password",
                    "passwd",
                    "secret",
                    "key",
                    "token",
                    "credential",
                ]
            ):
                # Don't include sensitive fields
                continue
            else:
                # Recursively filter nested data
                filtered[key] = filter_sensitive_data(value)
        return filtered
    elif isinstance(data, list):
        return [filter_sensitive_data(item) for item in data]
    else:
        return data


@mcp.tool()
async def health_check() -> dict[str, Any]:
    """
    Health check endpoint for container orchestration.

    Returns:
        Status information about the MCP server
    """
    return {
        "status": "healthy",
        "service": "thruk-mcp",
        "version": "1.0.0",
        "thruk_configured": bool(THRUK_BASE_URL and THRUK_API_KEY),
    }


@mcp.tool()
async def get_thruk_status(username: str = "chatuser") -> dict[str, Any]:
    """
    Placeholder tool for getting Thruk status.

    Args:
        username: User session username for authorization (default: chatuser)

    Returns:
        Placeholder response
    """
    logger.info(
        "get_thruk_status called",
        extra={"username": username, "tool": "get_thruk_status"},
    )
    return {
        "message": "Thruk MCP server is running",
        "username": username,
        "note": "This is a placeholder. Implement full Thruk API integration.",
    }


async def _api_request(
    url: str,
    username: str,
    method: str = "GET",
    data: dict = None,
    headers: dict = None,
) -> dict[str, Any]:
    """
    Generic helper to make calls to Thruk API with centralized error handling.

    Args:
        url: The full Thruk API URL
        username: The user session username
        method: HTTP method (GET, POST, etc.)
        data: Request payload for POST/PUT requests
        headers: Additional request headers

    Returns:
        A dictionary containing either the API response or an error message
    """
    # Validate configuration
    if not THRUK_BASE_URL or not THRUK_API_KEY:
        logger.error(
            "Thruk API not configured (missing THRUK_BASE_URL or THRUK_API_KEY)"
        )
        return {
            "error": "Thruk API not configured",
            "message": "THRUK_BASE_URL and THRUK_API_KEY must be set",
            "username": username,
        }

    # Prepare default headers and merge with custom ones
    final_headers = {
        "X-Thruk-Auth-Key": THRUK_API_KEY,
        "X-Thruk-Auth-User": username,
        "Accept": "application/json",
    }
    if headers:
        final_headers.update(headers)

    logger.debug(f"Calling Thruk API: {method} {url}", extra={"username": username})

    try:
        async with httpx.AsyncClient(
            verify=THRUK_VERIFY_SSL, timeout=30.0, follow_redirects=True
        ) as client:
            # Select request method
            response = (
                await client.post(url, headers=final_headers, data=data)
                if method.upper() == "POST"
                else await client.get(url, headers=final_headers)
            )

            # Log response status
            logger.debug(
                f"Thruk API response: {response.status_code}",
                extra={"username": username, "status_code": response.status_code},
            )

            # Check for authentication/authorization errors
            if response.status_code == 401:
                logger.error("Thruk API authentication failed (401)")
                return {
                    "error": "authentication_failed",
                    "message": "Invalid API key or insufficient permissions",
                    "username": username,
                    "status_code": 401,
                }

            if response.status_code == 403:
                logger.error(
                    f"Thruk API authorization failed for user {username} (403)"
                )
                return {
                    "error": "authorization_failed",
                    "message": f"User {username} does not have permission for this resource",
                    "username": username,
                    "status_code": 403,
                }
            # Raise for other HTTP errors
            response.raise_for_status()

            # Parse JSON and return successful response
            response_data = response.json()
            return {"success": True, "data": filter_sensitive_data(response_data)}

    except httpx.TimeoutException as e:
        logger.error(f"Thruk API timeout: {e}", extra={"username": username})
        return {
            "error": "timeout",
            "message": "Request to Thruk API timed out",
            "username": username,
        }

    except httpx.ConnectError as e:
        error_str = str(e)
        if (
            "CERTIFICATE_VERIFY_FAILED" in error_str
            or "certificate verify failed" in error_str
        ):
            logger.error(
                f"Thruk API SSL certificate verification failed: {e}",
                extra={"username": username},
            )
            return {
                "error": "ssl_verification_failed",
                "message": (
                    f"SSL certificate verification failed for {THRUK_BASE_URL}. "
                    f"This is likely a self-signed certificate. "
                    f"Set THRUK_VERIFY_SSL=false to disable SSL verification."
                ),
                "username": username,
                "current_verify_ssl": THRUK_VERIFY_SSL,
            }
        else:
            logger.error(
                f"Thruk API connection error: {e}", extra={"username": username}
            )
            return {
                "error": "connection_failed",
                "message": f"Cannot connect to Thruk at {THRUK_BASE_URL}",
                "username": username,
            }

    except httpx.HTTPStatusError as e:
        # Try to get the error message from the response body
        try:
            error_body = (
                e.response.json()
                if e.response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else e.response.text
            )
        except Exception:
            error_body = e.response.text

        logger.error(
            f"Thruk API HTTP error: {e.response.status_code} - {error_body}",
            extra={
                "username": username,
                "status_code": e.response.status_code,
                "response_body": error_body,
            },
        )
        return {
            "error": "http_error",
            "message": f"Thruk API returned error: {e.response.status_code}",
            "details": error_body,
            "username": username,
            "status_code": e.response.status_code,
        }

    except Exception as e:
        logger.error(
            f"Unexpected error calling Thruk API: {e}",
            exc_info=True,
            extra={"username": username},
        )
        return {
            "error": "unexpected_error",
            "message": f"Unexpected error: {str(e)}",
            "username": username,
        }


# =============================================================================
# Host Monitoring Tools
# =============================================================================


@mcp.tool()
async def thruk_list_hosts(username: str = "chatuser") -> dict[str, Any]:
    """
    List all monitored hosts visible to the user.

    Args:
        username: User session username for authorization (default: chatuser)

    Returns:
        List of hosts with their status
    """
    logger.info(
        "thruk_list_hosts called",
        extra={"username": username, "tool": "thruk_list_hosts"},
    )

    # Prepare API request details
    url = f"{THRUK_BASE_URL}/r/hosts?columns=name,alias,address,state,plugin_output,last_check,acknowledged,scheduled_downtime_depth,groups"

    # Call the generic API request handler
    result = await _api_request(url=url, username=username)

    # Process successful response
    if not result.get("success"):
        return result

    hosts_data = result["data"]
    logger.info(
        f"Successfully fetched {len(hosts_data)} hosts from Thruk",
        extra={"username": username, "host_count": len(hosts_data)},
    )
    return {"hosts": hosts_data, "count": len(hosts_data), "username": username}


# =============================================================================
# Service Monitoring Tools
# =============================================================================


@mcp.tool()
async def thruk_list_services(
    hostname: str = "", username: str = "chatuser"
) -> dict[str, Any]:
    """
    List services for a specific host or all services.

    Args:
        hostname: Name of the host to query services for (empty string = all services)
        username: User session username for authorization (default: chatuser)

    Returns:
        List of services with their status
    """
    logger.info(
        "thruk_list_services called",
        extra={
            "username": username,
            "hostname": hostname if hostname else "all hosts",
            "tool": "thruk_list_services",
        },
    )

    # Prepare API request details
    if hostname:
        url = f"{THRUK_BASE_URL}/r/services?host_name={hostname}&columns=host_name,description,state,plugin_output,last_check,acknowledged,scheduled_downtime_depth"
    else:
        url = f"{THRUK_BASE_URL}/r/services?columns=host_name,description,state,plugin_output,last_check,acknowledged,scheduled_downtime_depth"

    # Call the generic API request handler
    result = await _api_request(url=url, username=username)

    # Process successful response
    if not result.get("success"):
        return result

    services_data = result["data"]
    logger.info(
        f"Successfully fetched {len(services_data)} services from Thruk",
        extra={"username": username, "service_count": len(services_data)},
    )
    return {
        "services": services_data,
        "count": len(services_data),
        "hostname": hostname if hostname else "all hosts",
        "username": username,
    }


# =============================================================================
# Group Management Tools
# =============================================================================


@mcp.tool()
async def thruk_list_hostgroups(username: str = "chatuser") -> dict[str, Any]:
    """
    List all host groups visible to the user.

    Args:
        username: User session username for authorization (default: chatuser)

    Returns:
        List of hostgroups with their details
    """
    logger.info(
        "thruk_list_hostgroups called",
        extra={"username": username, "tool": "thruk_list_hostgroups"},
    )

    url = f"{THRUK_BASE_URL}/r/hostgroups?columns=name,alias,num_hosts,num_services"
    result = await _api_request(url=url, username=username)

    if not result.get("success"):
        return result

    hostgroups_data = result["data"]
    logger.info(
        f"Successfully fetched {len(hostgroups_data)} hostgroups from Thruk",
        extra={"username": username, "hostgroup_count": len(hostgroups_data)},
    )
    return {"hostgroups": hostgroups_data, "count": len(hostgroups_data), "username": username}


@mcp.tool()
async def thruk_get_hostgroup(hostgroup: str, username: str = "chatuser") -> dict[str, Any]:
    """
    Get details for a specific hostgroup.

    Args:
        hostgroup: Name of the hostgroup to query
        username: User session username for authorization (default: chatuser)

    Returns:
        Hostgroup details including members, num_hosts, num_services
    """
    logger.info(
        "thruk_get_hostgroup called",
        extra={"username": username, "hostgroup": hostgroup, "tool": "thruk_get_hostgroup"},
    )

    from urllib.parse import quote

    hostgroup_encoded = quote(hostgroup, safe="")
    url = f"{THRUK_BASE_URL}/r/hostgroups/{hostgroup_encoded}?columns=name,alias,num_hosts,num_services,hostgroup_members,notes"
    result = await _api_request(url=url, username=username)

    if not result.get("success"):
        return result

    hostgroup_data = result["data"]
    logger.info(
        f"Successfully fetched hostgroup {hostgroup}",
        extra={"username": username, "hostgroup": hostgroup},
    )
    return {"hostgroup": hostgroup_data, "username": username}


@mcp.tool()
async def thruk_list_hostgroup_hosts(hostgroup: str, username: str = "chatuser") -> dict[str, Any]:
    """
    List all hosts that belong to a specific hostgroup.

    Args:
        hostgroup: Name of the hostgroup to query
        username: User session username for authorization (default: chatuser)

    Returns:
        List of hosts in the hostgroup with their status
    """
    logger.info(
        "thruk_list_hostgroup_hosts called",
        extra={"username": username, "hostgroup": hostgroup, "tool": "thruk_list_hostgroup_hosts"},
    )

    from urllib.parse import quote

    # Get hostgroup with members list
    hostgroup_encoded = quote(hostgroup, safe="")
    url = f"{THRUK_BASE_URL}/r/hostgroups/{hostgroup_encoded}?columns=name,alias,members"
    result = await _api_request(url=url, username=username)

    if not result.get("success"):
        return result

    # API returns a list for single hostgroup requests
    hostgroup_list = result["data"]
    if isinstance(hostgroup_list, list) and len(hostgroup_list) > 0:
        hostgroup_data = hostgroup_list[0]
    elif isinstance(hostgroup_list, dict):
        hostgroup_data = hostgroup_list
    else:
        return {"hostgroup": hostgroup, "hosts": [], "count": 0, "username": username}

    members = hostgroup_data.get("members", [])
    hostgroup_name = hostgroup_data.get("name", hostgroup)

    if not members:
        return {"hostgroup": hostgroup_name, "hosts": [], "count": 0, "username": username}

    # Fetch status for each member host
    hosts_data = []
    for member in members:
        host_url = f"{THRUK_BASE_URL}/r/hosts/{quote(member, safe='')}?columns=name,alias,address,state,plugin_output,last_check,acknowledged,scheduled_downtime_depth"
        host_result = await _api_request(url=host_url, username=username)
        if host_result.get("success") and host_result.get("data"):
            # host_result["data"] is a single host object, wrap in list
            host_data = host_result["data"]
            if isinstance(host_data, list) and len(host_data) > 0:
                hosts_data.append(host_data[0])
            elif isinstance(host_data, dict):
                hosts_data.append(host_data)

    logger.info(
        f"Successfully fetched {len(hosts_data)} hosts from hostgroup {hostgroup}",
        extra={"username": username, "hostgroup": hostgroup, "host_count": len(hosts_data)},
    )
    return {"hostgroup": hostgroup_name, "hosts": hosts_data, "count": len(hosts_data), "username": username}


@mcp.tool()
async def thruk_list_servicegroups(username: str = "chatuser") -> dict[str, Any]:
    """
    List all service groups visible to the user.
    """
    logger.info(
        "thruk_list_servicegroups called",
        extra={"username": username, "tool": "thruk_list_servicegroups"},
    )

    # TODO: Implement actual Thruk API call
    # url = f"{THRUK_BASE_URL}/r/servicegroups"
    # result = await _api_request(url=url, username=username)
    # if result.get("success"):
    #     return {"servicegroups": result["data"], "username": username}
    # return result

    return {
        "servicegroups": [],
        "username": username,
        "note": "Placeholder - implement Thruk /r/servicegroups API integration",
    }


# =============================================================================
# Downtime Management Tools
# =============================================================================


@mcp.tool()
async def thruk_list_downtimes(username: str = "chatuser") -> dict[str, Any]:
    """
    List all active downtimes visible to the user.

    Args:
        username: User session username for authorization (default: chatuser)

    Returns:
        List of active downtimes
    """
    logger.info(
        "thruk_list_downtimes called",
        extra={"username": username, "tool": "thruk_list_downtimes"},
    )

    # Prepare API request
    url = f"{THRUK_BASE_URL}/r/downtimes?columns=id,host_name,service_description,author,comment,start_time,end_time,duration,fixed"

    # Call the generic API request handler
    result = await _api_request(url=url, username=username)

    # Process successful response
    if not result.get("success"):
        return result

    downtimes_data = result["data"]
    logger.info(
        f"Successfully fetched {len(downtimes_data)} downtimes from Thruk",
        extra={"username": username, "downtime_count": len(downtimes_data)},
    )
    return {
        "downtimes": downtimes_data,
        "count": len(downtimes_data),
        "username": username,
    }


@mcp.tool()
async def thruk_list_comments(username: str = "chatuser") -> dict[str, Any]:
    """
    List all comments visible to the user.

    Args:
        username: User session username for authorization (default: chatuser)

    Returns:
        List of comments
    """
    logger.info(
        "thruk_list_comments called",
        extra={"username": username, "tool": "thruk_list_comments"},
    )

    # Prepare API request
    url = f"{THRUK_BASE_URL}/r/comments?columns=id,host_name,service_description,author,comment,entry_time,persistent"

    # Call the generic API request handler
    result = await _api_request(url=url, username=username)

    # Process successful response
    if not result.get("success"):
        return result

    comments_data = result["data"]
    logger.info(
        f"Successfully fetched {len(comments_data)} comments from Thruk",
        extra={"username": username, "comment_count": len(comments_data)},
    )
    return {
        "comments": comments_data,
        "count": len(comments_data),
        "username": username,
    }


@mcp.tool()
async def thruk_schedule_host_downtime(
    hostname: str, duration_minutes: int, comment: str, username: str = "chatuser"
) -> dict[str, Any]:
    """
    Schedule downtime for a specific host.

    Args:
        hostname: Name of the host to schedule downtime for
        duration_minutes: Duration of downtime in minutes
        comment: Reason for the downtime
        username: User session username for authorization (default: chatuser)

    Returns:
        Confirmation of scheduled downtime
    """
    logger.info(
        "thruk_schedule_host_downtime called",
        extra={
            "username": username,
            "hostname": hostname,
            "duration_minutes": duration_minutes,
            "tool": "thruk_schedule_host_downtime",
        },
    )

    # Prepare API request
    url = f"{THRUK_BASE_URL}/r/hosts/{hostname}/cmd/schedule_host_downtime"
    data = {
        "start_time": "now",
        "end_time": f"+{duration_minutes}m",
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "fixed": "1",  # Fixed downtime
    }

    # Call the generic API request handler
    result = await _api_request(url=url, username=username, method="POST", data=data)

    # Process successful response
    if not result.get("success"):
        return result

    logger.info(
        f"Successfully scheduled downtime for host {hostname}",
        extra={
            "username": username,
            "hostname": hostname,
            "duration_minutes": duration_minutes,
        },
    )
    return {
        "success": True,
        "hostname": hostname,
        "duration_minutes": duration_minutes,
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "result": result["data"],
        "username": username,
    }


@mcp.tool()
async def thruk_schedule_service_downtime(
    hostname: str,
    service_description: str,
    duration_minutes: int,
    comment: str,
    username: str = "chatuser",
) -> dict[str, Any]:
    """
    Schedule downtime for a specific service.

    Args:
        hostname: Name of the host
        service_description: Description of the service
        duration_minutes: Duration of downtime in minutes
        comment: Reason for the downtime
        username: User session username for authorization (default: chatuser)

    Returns:
        Confirmation of scheduled downtime
    """
    logger.info(
        "thruk_schedule_service_downtime called",
        extra={
            "username": username,
            "hostname": hostname,
            "service_description": service_description,
            "duration_minutes": duration_minutes,
            "tool": "thruk_schedule_service_downtime",
        },
    )

    # URL encode service description for URL path
    from urllib.parse import quote

    service_encoded = quote(service_description, safe="")

    # Prepare API request
    url = f"{THRUK_BASE_URL}/r/services/{hostname}/{service_encoded}/cmd/schedule_svc_downtime"
    data = {
        "start_time": "now",
        "end_time": f"+{duration_minutes}m",
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "fixed": "1",  # Fixed downtime
    }

    # Call the generic API request handler
    result = await _api_request(url=url, username=username, method="POST", data=data)

    # Process successful response
    if not result.get("success"):
        return result

    logger.info(
        f"Successfully scheduled downtime for service {hostname}/{service_description}",
        extra={
            "username": username,
            "hostname": hostname,
            "service": service_description,
        },
    )
    return {
        "success": True,
        "hostname": hostname,
        "service_description": service_description,
        "duration_minutes": duration_minutes,
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "result": result["data"],
        "username": username,
    }


@mcp.tool()
async def thruk_schedule_hostgroup_downtime(
    hostgroup: str, duration_minutes: int, comment: str, username: str = "chatuser"
) -> dict[str, Any]:
    """
    Schedule downtime for all hosts in a hostgroup.

    Args:
        hostgroup: Name of the hostgroup
        duration_minutes: Duration of downtime in minutes
        comment: Reason for the downtime
        username: User session username for authorization (default: chatuser)

    Returns:
        Confirmation of scheduled downtime for all hosts in the group
    """
    logger.info(
        "thruk_schedule_hostgroup_downtime called",
        extra={
            "username": username,
            "hostgroup": hostgroup,
            "duration_minutes": duration_minutes,
            "tool": "thruk_schedule_hostgroup_downtime",
        },
    )

    # Prepare API request
    url = f"{THRUK_BASE_URL}/r/hostgroups/{hostgroup}/cmd/schedule_hostgroup_host_downtime"
    data = {
        "start_time": "now",
        "end_time": f"+{duration_minutes}m",
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "fixed": "1",  # Fixed downtime
    }

    # Call the generic API request handler
    result = await _api_request(url=url, username=username, method="POST", data=data)

    # Process successful response
    if not result.get("success"):
        return result

    logger.info(
        f"Successfully scheduled downtime for hostgroup {hostgroup}",
        extra={
            "username": username,
            "hostgroup": hostgroup,
            "duration_minutes": duration_minutes,
        },
    )
    return {
        "success": True,
        "hostgroup": hostgroup,
        "duration_minutes": duration_minutes,
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "comment_author": username,  # Thruk expects 'comment_author', not 'author'
        "result": result["data"],
        "username": username,
    }


@mcp.tool()
async def thruk_schedule_servicegroup_downtime(
    servicegroup: str, duration_minutes: int, comment: str, username: str = "chatuser"
) -> dict[str, Any]:
    """
    Schedule downtime for all services in a servicegroup.
    """
    logger.info(
        "thruk_schedule_servicegroup_downtime called",
        extra={
            "username": username,
            "servicegroup": servicegroup,
            "duration_minutes": duration_minutes,
            "tool": "thruk_schedule_servicegroup_downtime",
        },
    )

    # Note: This is a placeholder for a future implementation.
    # The real implementation would use the _api_request helper like the other functions.
    # For example:
    #
    # url = f"{THRUK_BASE_URL}/r/servicegroups/{servicegroup}/cmd/schedule_servicegroup_svc_downtime"
    # data = {
    #     "start_time": "now",
    #     "end_time": f"+{duration_minutes}m",
    #     "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
    #     "comment_author": username,  # Thruk expects 'comment_author', not 'author'
    #     "fixed": "1"
    # }
    # result = await _api_request(url=url, username=username, method="POST", data=data)
    #
    # if result.get("success"):
    #     return {"success": True, "servicegroup": servicegroup, ...}
    # return result

    return {
        "servicegroup": servicegroup,
        "duration_minutes": duration_minutes,
        "comment_data": comment,  # Thruk expects 'comment_data', not 'comment'
        "username": username,
        "note": "Placeholder - implement Thruk schedule_servicegroup_downtime command",
    }


def main():
    """Main entry point for the MCP server (stdio transport)."""
    logger.info("Starting Thruk MCP server (stdio transport)")
    # Run the FastMCP server with stdio transport (spawned by chatbot)
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
