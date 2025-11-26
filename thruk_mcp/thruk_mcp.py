#!/usr/bin/env python3
"""
Thruk MCP Server - Model Context Protocol server for Thruk monitoring system.

This server enables LLMs to interact with Thruk monitoring systems to manage
downtimes, query hosts, services, and more. Built using FastMCP with comprehensive logging.

Enhanced Features:
- Comprehensive logging for all operations
- Startup and shutdown logging
- Tool execution tracking
- API request/response logging
- Error tracking
- Support for both stdio and HTTP transports
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, field_validator, ConfigDict
from mcp.server.fastmcp import FastMCP
import uvicorn

# =============================================================================
# Logging Configuration
# =============================================================================

# Configure logging to stderr only (stdout is reserved for MCP protocol)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr)
    ],
    force=True
)

# Force unbuffered stderr
sys.stderr.reconfigure(line_buffering=True)

# Create loggers for different components
logger = logging.getLogger("thruk_mcp")
startup_logger = logging.getLogger("thruk_mcp.startup")
shutdown_logger = logging.getLogger("thruk_mcp.shutdown")
api_logger = logging.getLogger("thruk_mcp.api")
tool_logger = logging.getLogger("thruk_mcp.tool")

# Log startup
startup_logger.info("=" * 70)
startup_logger.info("Thruk MCP Server Starting")
startup_logger.info("=" * 70)

# Initialize the MCP server
mcp = FastMCP("thruk_mcp")
startup_logger.info("FastMCP server initialized: thruk_mcp")

# Constants
DEFAULT_DOWNTIME_DURATION = 2  # hours
DEFAULT_START_TIME = "now"
DEFAULT_END_TIME = "+2h"

startup_logger.info(f"Default downtime duration: {DEFAULT_DOWNTIME_DURATION} hours")

# =============================================================================
# Configuration and Authentication
# =============================================================================

class ThrukConfig:
    """Configuration for Thruk API connection."""
    
    def __init__(self):
        startup_logger.info("Initializing Thruk configuration")
        
        self.base_url = os.getenv("THRUK_BASE_URL", "http://localhost/thruk")
        self.api_key = os.getenv("THRUK_API_KEY", "")
        self.auth_user = os.getenv("THRUK_AUTH_USER", "")
        self.verify_ssl = os.getenv("THRUK_VERIFY_SSL", "true").lower() == "true"
        
        startup_logger.info(f"Thruk base URL: {self.base_url}")
        startup_logger.info(f"Thruk auth user: {self.auth_user or '(none)'}")
        startup_logger.info(f"SSL verification: {self.verify_ssl}")
        
        if not self.api_key:
            startup_logger.error("THRUK_API_KEY environment variable not set!")
            raise ValueError(
                "THRUK_API_KEY environment variable must be set. "
                "You can generate an API key from the Thruk user profile page."
            )
        
        startup_logger.info("✓ Thruk API key configured")
    
    def get_headers(self) -> Dict[str, str]:
        """Get HTTP headers for API requests."""
        headers = {
            "X-Thruk-Auth-Key": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if self.auth_user:
            headers["X-Thruk-Auth-User"] = self.auth_user
        return headers

# Global config instance
_config: Optional[ThrukConfig] = None

def get_config() -> ThrukConfig:
    """Get or create Thruk configuration."""
    global _config
    if _config is None:
        _config = ThrukConfig()
    return _config

# =============================================================================
# Pydantic Models for Input Validation
# =============================================================================

class ResponseFormat(str, Enum):
    """Output format for tool responses."""
    MARKDOWN = "markdown"
    JSON = "json"

class DowntimeType(str, Enum):
    """Type of downtime to schedule."""
    HOST = "host"
    SERVICE = "service"
    HOSTGROUP = "hostgroup"
    SERVICEGROUP = "servicegroup"

class ChildOptions(int, Enum):
    """Options for handling child hosts during downtime."""
    NONE = 0
    TRIGGERED = 1
    NON_TRIGGERED = 2

class HostServiceOptions(int, Enum):
    """Options for handling services during host downtime."""
    NONE = 0
    SCHEDULE_ALL = 1

class ScheduleDowntimeInput(BaseModel):
    """Input model for scheduling downtime."""
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    host: str = Field(..., description="Host name")
    service: Optional[str] = Field(None, description="Service description (for service downtimes)")
    start_time: str = Field(DEFAULT_START_TIME, description="Start time (relative like '+30m' or absolute)")
    end_time: str = Field(DEFAULT_END_TIME, description="End time (relative like '+2h' or absolute)")
    comment: str = Field("requested via chatbot", description="Comment explaining WHY the downtime is needed (ask user if not provided)")
    duration: Optional[int] = Field(None, description="Duration in minutes (alternative to end_time)")
    fixed: bool = Field(True, description="Whether the downtime is fixed or flexible")
    trigger_id: Optional[int] = Field(None, description="ID of downtime to trigger from")
    child_options: ChildOptions = Field(ChildOptions.NONE, description="How to handle child hosts")
    
    @field_validator('start_time', 'end_time')
    def validate_time_format(cls, v):
        """Validate time format."""
        if not v:
            return v
        if v in ['now', 'next_check']:
            return v
        if v.startswith('+') or v.startswith('-'):
            return v
        try:
            datetime.fromisoformat(v)
            return v
        except (ValueError, TypeError):
            raise ValueError(f"Invalid time format: {v}. Use 'now', relative like '+2h', or ISO format.")

class ListHostsInput(BaseModel):
    """Input model for listing hosts."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    hostgroup: Optional[str] = Field(None, description="Filter by hostgroup name")
    state: Optional[str] = Field(None, description="Filter by state: up, down, unreachable, pending")
    limit: int = Field(50, ge=1, le=500, description="Maximum number of hosts to return")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class ListServicesInput(BaseModel):
    """Input model for listing services."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    host: Optional[str] = Field(None, description="Filter by host name")
    servicegroup: Optional[str] = Field(None, description="Filter by servicegroup name")
    state: Optional[str] = Field(None, description="Filter by state: ok, warning, critical, unknown, pending")
    limit: int = Field(50, ge=1, le=500, description="Maximum number of services to return")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class ListHostgroupsInput(BaseModel):
    """Input model for listing hostgroups."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    limit: int = Field(50, ge=1, le=500, description="Maximum number of hostgroups to return")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class ListServicegroupsInput(BaseModel):
    """Input model for listing servicegroups."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    limit: int = Field(50, ge=1, le=500, description="Maximum number of servicegroups to return")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class GetHostDetailsInput(BaseModel):
    """Input model for getting host details."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    host: str = Field(..., description="Host name")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class GetServiceDetailsInput(BaseModel):
    """Input model for getting service details."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    host: str = Field(..., description="Host name")
    service: str = Field(..., description="Service description")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

class ListDowntimesInput(BaseModel):
    """Input model for listing downtimes."""
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    
    host: Optional[str] = Field(None, description="Filter by host name")
    active_only: bool = Field(True, description="Only show active downtimes")
    limit: int = Field(50, ge=1, le=500, description="Maximum number of downtimes to return")
    response_format: ResponseFormat = Field(ResponseFormat.MARKDOWN, description="Output format")

# =============================================================================
# Helper Functions
# =============================================================================

def make_request(endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict[str, Any]:
    """Make an HTTP request to the Thruk API with logging."""
    config = get_config()
    url = f"{config.base_url}{endpoint}"

    api_logger.info(f"=" * 80)
    api_logger.info(f"API Request Details:")
    api_logger.info(f"  Method: {method}")
    api_logger.info(f"  URL: {url}")
    api_logger.info(f"  Endpoint: {endpoint}")
    if data:
        api_logger.info(f"  Data payload:")
        for key, value in data.items():
            api_logger.info(f"    {key}: {value}")
    api_logger.info(f"=" * 80)

    try:
        with httpx.Client(verify=config.verify_ssl, timeout=30.0) as client:
            if method == "GET":
                # For GET requests, send data as query parameters
                api_logger.info(f"Sending GET request with params: {data}")
                response = client.get(url, headers=config.get_headers(), params=data)
            elif method == "POST":
                # Thruk REST API expects parameters in POST body as form data
                api_logger.info(f"Sending POST request with form data: {data}")
                response = client.post(url, headers=config.get_headers(), data=data)
            else:
                api_logger.error(f"Unsupported HTTP method: {method}")
                raise ValueError(f"Unsupported method: {method}")


            api_logger.info(f"API Response Status: {response.status_code}")
            api_logger.info(f"Response Headers: {dict(response.headers)}")
            api_logger.info(f"Response Body: {response.text[:1000]}")
            response.raise_for_status()

            result = response.json()
            api_logger.info(f"Parsed Response: {json.dumps(result, indent=2)}")
            
            return result
            
    except httpx.HTTPStatusError as e:
        api_logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
        raise Exception(f"Thruk API error ({e.response.status_code}): {e.response.text}")
    except httpx.RequestError as e:
        api_logger.error(f"Request error: {str(e)}")
        raise Exception(f"Failed to connect to Thruk API: {str(e)}")
    except json.JSONDecodeError as e:
        api_logger.error(f"JSON decode error: {str(e)}")
        raise Exception(f"Invalid JSON response from Thruk API: {str(e)}")
    except Exception as e:
        api_logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise

def format_state(state: int, is_service: bool = False) -> str:
    """Format state number to human-readable string."""
    if is_service:
        states = {0: "OK", 1: "WARNING", 2: "CRITICAL", 3: "UNKNOWN"}
    else:
        states = {0: "UP", 1: "DOWN", 2: "UNREACHABLE"}
    return states.get(state, f"UNKNOWN({state})")

def format_timestamp(ts: Optional[int]) -> str:
    """Format Unix timestamp to human-readable string."""
    if not ts or ts == 0:
        return "N/A"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

# =============================================================================
# MCP Tools
# =============================================================================

@mcp.tool()
def thruk_schedule_downtime(
    host: str,
    service: Optional[str] = None,
    start_time: str = DEFAULT_START_TIME,
    end_time: str = DEFAULT_END_TIME,
    comment: str = "requested via chatbot",
    duration: Optional[int] = None,
    fixed: bool = True,
    trigger_id: Optional[int] = None,
    child_options: int = 0
) -> str:
    """
    Schedule a downtime for a host or service in Thruk.

    IMPORTANT: Before calling this tool, you MUST:
    1. Check if the user provided a reason/comment for the downtime in their request
    2. If NO comment is provided, ASK the user why they want to set this downtime
    3. If the user's response is empty or unusable, use the default comment "requested via chatbot"

    Args:
        host: Host name to schedule downtime for
        service: Service description (optional, for service downtimes)
        start_time: Start time - 'now', relative ('+30m'), or ISO format (default: 'now')
        end_time: End time - relative ('+2h'), or ISO format (default: '+2h')
        comment: Comment explaining WHY the downtime is needed (REQUIRED - must ask user if not provided)
        duration: Duration in minutes (alternative to end_time)
        fixed: Whether the downtime is fixed (true) or flexible (false) (default: true)
        trigger_id: ID of downtime to trigger from (optional)
        child_options: How to handle child hosts - 0=none, 1=triggered, 2=non-triggered (default: 0)
    
    Returns:
        Success message with downtime details or error message
    """
    tool_logger.info(f"Tool called: thruk_schedule_downtime(host={host}, service={service})")
    
    try:
        # Validate input using Pydantic model
        input_data = ScheduleDowntimeInput(
            host=host,
            service=service,
            start_time=start_time,
            end_time=end_time,
            comment=comment,
            duration=duration,
            fixed=fixed,
            trigger_id=trigger_id,
            child_options=ChildOptions(child_options)
        )
        
        tool_logger.info(f"Scheduling downtime: {input_data.host}" + (f"/{input_data.service}" if input_data.service else ""))
        
        # Build the API endpoint
        if input_data.service:
            endpoint = f"/r/services/{input_data.host}/{input_data.service}/cmd/schedule_svc_downtime"
            tool_logger.info(f"Downtime type: service")
        else:
            endpoint = f"/r/hosts/{input_data.host}/cmd/schedule_host_downtime"
            tool_logger.info(f"Downtime type: host")
        
        # Build request data - end_time and comment_data are REQUIRED
        # Calculate end_time based on duration if specified
        if input_data.duration:
            end_time_value = f"+{input_data.duration}m"
        else:
            end_time_value = input_data.end_time

        data = {
            "start_time": input_data.start_time,
            "end_time": end_time_value,
            "comment_data": input_data.comment,
            "comment_author": "chatbot",
            "fixed": "1" if input_data.fixed else "0"
        }

        if input_data.trigger_id:
            data["triggered_by"] = str(input_data.trigger_id)
        
        tool_logger.debug(f"Request data: {json.dumps(data)}")

        # Make the request - Thruk REST API uses POST with form data in body
        result = make_request(endpoint, method="POST", data=data)
        
        # Format response
        # Check for success: either rc == 0 or message contains success indicators
        message = result.get("message", "")
        is_success = (
            result.get("rc") == 0 or
            "successfully submitted" in message.lower() or
            "success" in message.lower()
        )

        if is_success:
            tool_logger.info(f"✓ Downtime scheduled successfully for {input_data.host}")

            response = f"✓ Downtime scheduled successfully\n\n"
            response += f"**Host:** {input_data.host}\n"
            if input_data.service:
                response += f"**Service:** {input_data.service}\n"
            response += f"**Start:** {input_data.start_time}\n"
            response += f"**End:** {input_data.end_time if not input_data.duration else f'+{input_data.duration}m'}\n"
            response += f"**Comment:** {input_data.comment}\n"
            response += f"**Type:** {'Fixed' if input_data.fixed else 'Flexible'}\n"
            if message:
                response += f"\n{message}"

            return response
        else:
            error_msg = result.get("message", "Unknown error occurred")
            tool_logger.error(f"Failed to schedule downtime: {error_msg}")
            return f"❌ Failed to schedule downtime: {error_msg}"
            
    except ValueError as e:
        tool_logger.error(f"Validation error: {str(e)}")
        return f"❌ Validation error: {str(e)}"
    except Exception as e:
        tool_logger.error(f"Error scheduling downtime: {str(e)}", exc_info=True)
        return f"❌ Error scheduling downtime: {str(e)}"

@mcp.tool()
def thruk_list_hosts(
    hostgroup: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    response_format: str = "markdown"
) -> str:
    """
    List hosts from Thruk monitoring system.
    
    Args:
        hostgroup: Filter by hostgroup name (optional)
        state: Filter by state - 'up', 'down', 'unreachable', 'pending' (optional)
        limit: Maximum number of hosts to return (default: 50, max: 500)
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        List of hosts in the specified format
    """
    tool_logger.info(f"Tool called: thruk_list_hosts(hostgroup={hostgroup}, state={state}, limit={limit})")
    
    try:
        # Validate input
        input_data = ListHostsInput(
            hostgroup=hostgroup,
            state=state,
            limit=limit,
            response_format=ResponseFormat(response_format)
        )
        
        # Build query
        endpoint = "/r/hosts"
        filters = []
        
        if input_data.hostgroup:
            filters.append(f"groups >= '{input_data.hostgroup}'")
            tool_logger.debug(f"Filter: hostgroup={input_data.hostgroup}")
        
        if input_data.state:
            state_map = {"up": 0, "down": 1, "unreachable": 2, "pending": None}
            state_num = state_map.get(input_data.state.lower())
            if state_num is not None:
                filters.append(f"state = {state_num}")
                tool_logger.debug(f"Filter: state={input_data.state}")
        
        if filters:
            filter_str = " and ".join(filters)
            endpoint += f"?q={filter_str}"
            endpoint += f"&limit={input_data.limit}"
        else:
            endpoint += f"?limit={input_data.limit}"
        
        # Make request
        result = make_request(endpoint)
        hosts = result if isinstance(result, list) else result.get("data", [])
        
        tool_logger.info(f"Retrieved {len(hosts)} hosts")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(hosts, indent=2)
        
        # Markdown format
        if not hosts:
            return "No hosts found matching the criteria."
        
        response = f"# Hosts ({len(hosts)} found)\n\n"
        
        for host in hosts:
            name = host.get("name", "Unknown")
            state = format_state(host.get("state", 0))
            output = host.get("plugin_output", "No output")
            address = host.get("address", "N/A")
            last_check = format_timestamp(host.get("last_check"))
            
            response += f"## {name}\n"
            response += f"- **State:** {state}\n"
            response += f"- **Address:** {address}\n"
            response += f"- **Output:** {output}\n"
            response += f"- **Last Check:** {last_check}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error listing hosts: {str(e)}", exc_info=True)
        return f"❌ Error listing hosts: {str(e)}"

@mcp.tool()
def thruk_list_services(
    host: Optional[str] = None,
    servicegroup: Optional[str] = None,
    state: Optional[str] = None,
    limit: int = 50,
    response_format: str = "markdown"
) -> str:
    """
    List services from Thruk monitoring system.
    
    Args:
        host: Filter by host name (optional)
        servicegroup: Filter by servicegroup name (optional)
        state: Filter by state - 'ok', 'warning', 'critical', 'unknown', 'pending' (optional)
        limit: Maximum number of services to return (default: 50, max: 500)
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        List of services in the specified format
    """
    tool_logger.info(f"Tool called: thruk_list_services(host={host}, servicegroup={servicegroup}, state={state})")
    
    try:
        # Validate input
        input_data = ListServicesInput(
            host=host,
            servicegroup=servicegroup,
            state=state,
            limit=limit,
            response_format=ResponseFormat(response_format)
        )
        
        # Build query
        endpoint = "/r/services"
        filters = []
        
        if input_data.host:
            filters.append(f"host_name = '{input_data.host}'")
            tool_logger.debug(f"Filter: host={input_data.host}")
        
        if input_data.servicegroup:
            filters.append(f"groups >= '{input_data.servicegroup}'")
            tool_logger.debug(f"Filter: servicegroup={input_data.servicegroup}")
        
        if input_data.state:
            state_map = {"ok": 0, "warning": 1, "critical": 2, "unknown": 3, "pending": None}
            state_num = state_map.get(input_data.state.lower())
            if state_num is not None:
                filters.append(f"state = {state_num}")
                tool_logger.debug(f"Filter: state={input_data.state}")
        
        if filters:
            filter_str = " and ".join(filters)
            endpoint += f"?q={filter_str}"
            endpoint += f"&limit={input_data.limit}"
        else:
            endpoint += f"?limit={input_data.limit}"
        
        # Make request
        result = make_request(endpoint)
        services = result if isinstance(result, list) else result.get("data", [])
        
        tool_logger.info(f"Retrieved {len(services)} services")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(services, indent=2)
        
        # Markdown format
        if not services:
            return "No services found matching the criteria."
        
        response = f"# Services ({len(services)} found)\n\n"
        
        for service in services:
            host_name = service.get("host_name", "Unknown")
            description = service.get("description", "Unknown")
            state = format_state(service.get("state", 0), is_service=True)
            output = service.get("plugin_output", "No output")
            last_check = format_timestamp(service.get("last_check"))
            
            response += f"## {host_name} / {description}\n"
            response += f"- **State:** {state}\n"
            response += f"- **Output:** {output}\n"
            response += f"- **Last Check:** {last_check}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error listing services: {str(e)}", exc_info=True)
        return f"❌ Error listing services: {str(e)}"

@mcp.tool()
def thruk_list_hostgroups(
    limit: int = 50,
    response_format: str = "markdown"
) -> str:
    """
    List all hostgroups from Thruk monitoring system.
    
    Args:
        limit: Maximum number of hostgroups to return (default: 50, max: 500)
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        List of hostgroups in the specified format
    """
    tool_logger.info(f"Tool called: thruk_list_hostgroups(limit={limit})")
    
    try:
        # Validate input
        input_data = ListHostgroupsInput(
            limit=limit,
            response_format=ResponseFormat(response_format)
        )
        
        # Make request
        endpoint = f"/r/hostgroups?limit={input_data.limit}"
        result = make_request(endpoint)
        hostgroups = result if isinstance(result, list) else result.get("data", [])
        
        tool_logger.info(f"Retrieved {len(hostgroups)} hostgroups")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(hostgroups, indent=2)
        
        # Markdown format
        if not hostgroups:
            return "No hostgroups found."
        
        response = f"# Hostgroups ({len(hostgroups)} found)\n\n"
        
        for hg in hostgroups:
            name = hg.get("name", "Unknown")
            alias = hg.get("alias", "")
            num_hosts = hg.get("num_hosts", 0)
            num_hosts_up = hg.get("num_hosts_up", 0)
            num_hosts_down = hg.get("num_hosts_down", 0)
            num_hosts_unreach = hg.get("num_hosts_unreach", 0)
            
            response += f"## {name}\n"
            if alias and alias != name:
                response += f"- **Alias:** {alias}\n"
            response += f"- **Total Hosts:** {num_hosts}\n"
            response += f"- **Up:** {num_hosts_up}, **Down:** {num_hosts_down}, **Unreachable:** {num_hosts_unreach}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error listing hostgroups: {str(e)}", exc_info=True)
        return f"❌ Error listing hostgroups: {str(e)}"

@mcp.tool()
def thruk_list_servicegroups(
    limit: int = 50,
    response_format: str = "markdown"
) -> str:
    """
    List all servicegroups from Thruk monitoring system.
    
    Args:
        limit: Maximum number of servicegroups to return (default: 50, max: 500)
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        List of servicegroups in the specified format
    """
    tool_logger.info(f"Tool called: thruk_list_servicegroups(limit={limit})")
    
    try:
        # Validate input
        input_data = ListServicegroupsInput(
            limit=limit,
            response_format=ResponseFormat(response_format)
        )
        
        # Make request
        endpoint = f"/r/servicegroups?limit={input_data.limit}"
        result = make_request(endpoint)
        servicegroups = result if isinstance(result, list) else result.get("data", [])
        
        tool_logger.info(f"Retrieved {len(servicegroups)} servicegroups")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(servicegroups, indent=2)
        
        # Markdown format
        if not servicegroups:
            return "No servicegroups found."
        
        response = f"# Servicegroups ({len(servicegroups)} found)\n\n"
        
        for sg in servicegroups:
            name = sg.get("name", "Unknown")
            alias = sg.get("alias", "")
            num_services = sg.get("num_services", 0)
            num_services_ok = sg.get("num_services_ok", 0)
            num_services_warn = sg.get("num_services_warn", 0)
            num_services_crit = sg.get("num_services_crit", 0)
            num_services_unknown = sg.get("num_services_unknown", 0)
            
            response += f"## {name}\n"
            if alias and alias != name:
                response += f"- **Alias:** {alias}\n"
            response += f"- **Total Services:** {num_services}\n"
            response += f"- **OK:** {num_services_ok}, **Warning:** {num_services_warn}, "
            response += f"**Critical:** {num_services_crit}, **Unknown:** {num_services_unknown}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error listing servicegroups: {str(e)}", exc_info=True)
        return f"❌ Error listing servicegroups: {str(e)}"

@mcp.tool()
def thruk_get_host_details(
    host: str,
    response_format: str = "markdown"
) -> str:
    """
    Get detailed information about a specific host.
    
    Args:
        host: Host name
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        Detailed host information in the specified format
    """
    tool_logger.info(f"Tool called: thruk_get_host_details(host={host})")
    
    try:
        # Validate input
        input_data = GetHostDetailsInput(
            host=host,
            response_format=ResponseFormat(response_format)
        )
        
        # Make request
        endpoint = f"/r/hosts/{input_data.host}"
        result = make_request(endpoint)
        
        tool_logger.info(f"Retrieved details for host: {input_data.host}")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        
        # Markdown format
        response = f"# Host Details: {input_data.host}\n\n"
        
        response += f"**State:** {format_state(result.get('state', 0))}\n"
        response += f"**Address:** {result.get('address', 'N/A')}\n"
        response += f"**Plugin Output:** {result.get('plugin_output', 'N/A')}\n"
        response += f"**Last Check:** {format_timestamp(result.get('last_check'))}\n"
        response += f"**Next Check:** {format_timestamp(result.get('next_check'))}\n"
        response += f"**Acknowledged:** {'Yes' if result.get('acknowledged') else 'No'}\n"
        response += f"**Scheduled Downtime:** {'Yes' if result.get('scheduled_downtime_depth', 0) > 0 else 'No'}\n"
        response += f"**Notifications Enabled:** {'Yes' if result.get('notifications_enabled') else 'No'}\n"
        
        groups = result.get('groups', [])
        if groups:
            response += f"**Hostgroups:** {', '.join(groups)}\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error getting host details: {str(e)}", exc_info=True)
        return f"❌ Error getting host details: {str(e)}"

@mcp.tool()
def thruk_get_service_details(
    host: str,
    service: str,
    response_format: str = "markdown"
) -> str:
    """
    Get detailed information about a specific service.
    
    Args:
        host: Host name
        service: Service description
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        Detailed service information in the specified format
    """
    tool_logger.info(f"Tool called: thruk_get_service_details(host={host}, service={service})")
    
    try:
        # Validate input
        input_data = GetServiceDetailsInput(
            host=host,
            service=service,
            response_format=ResponseFormat(response_format)
        )
        
        # Make request
        endpoint = f"/r/services/{input_data.host}/{input_data.service}"
        result = make_request(endpoint)
        
        tool_logger.info(f"Retrieved details for service: {input_data.host}/{input_data.service}")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(result, indent=2)
        
        # Markdown format
        response = f"# Service Details: {input_data.host} / {input_data.service}\n\n"
        
        response += f"**State:** {format_state(result.get('state', 0), is_service=True)}\n"
        response += f"**Plugin Output:** {result.get('plugin_output', 'N/A')}\n"
        response += f"**Last Check:** {format_timestamp(result.get('last_check'))}\n"
        response += f"**Next Check:** {format_timestamp(result.get('next_check'))}\n"
        response += f"**Acknowledged:** {'Yes' if result.get('acknowledged') else 'No'}\n"
        response += f"**Scheduled Downtime:** {'Yes' if result.get('scheduled_downtime_depth', 0) > 0 else 'No'}\n"
        response += f"**Notifications Enabled:** {'Yes' if result.get('notifications_enabled') else 'No'}\n"
        
        groups = result.get('groups', [])
        if groups:
            response += f"**Servicegroups:** {', '.join(groups)}\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error getting service details: {str(e)}", exc_info=True)
        return f"❌ Error getting service details: {str(e)}"

@mcp.tool()
def thruk_list_downtimes(
    host: Optional[str] = None,
    active_only: bool = True,
    limit: int = 50,
    response_format: str = "markdown"
) -> str:
    """
    List scheduled downtimes from Thruk.
    
    Args:
        host: Filter by host name (optional)
        active_only: Only show active downtimes (default: true)
        limit: Maximum number of downtimes to return (default: 50, max: 500)
        response_format: Output format - 'markdown' or 'json' (default: 'markdown')
    
    Returns:
        List of downtimes in the specified format
    """
    tool_logger.info(f"Tool called: thruk_list_downtimes(host={host}, active_only={active_only})")
    
    try:
        # Validate input
        input_data = ListDowntimesInput(
            host=host,
            active_only=active_only,
            limit=limit,
            response_format=ResponseFormat(response_format)
        )
        
        # Build query
        endpoint = "/r/downtimes"
        filters = []
        
        if input_data.host:
            filters.append(f"host_name = '{input_data.host}'")
            tool_logger.debug(f"Filter: host={input_data.host}")
        
        if input_data.active_only:
            now = int(datetime.now().timestamp())
            filters.append(f"start_time <= {now}")
            filters.append(f"end_time >= {now}")
            tool_logger.debug(f"Filter: active_only=true")
        
        if filters:
            filter_str = " and ".join(filters)
            endpoint += f"?q={filter_str}"
            endpoint += f"&limit={input_data.limit}"
        else:
            endpoint += f"?limit={input_data.limit}"
        
        # Make request
        result = make_request(endpoint)
        downtimes = result if isinstance(result, list) else result.get("data", [])
        
        tool_logger.info(f"Retrieved {len(downtimes)} downtimes")
        
        if input_data.response_format == ResponseFormat.JSON:
            return json.dumps(downtimes, indent=2)
        
        # Markdown format
        if not downtimes:
            return "No downtimes found matching the criteria."
        
        response = f"# Downtimes ({len(downtimes)} found)\n\n"
        
        for dt in downtimes:
            host_name = dt.get("host_name", "Unknown")
            service_desc = dt.get("service_description", "")
            author = dt.get("author", "Unknown")
            comment = dt.get("comment", "No comment")
            start = format_timestamp(dt.get("start_time"))
            end = format_timestamp(dt.get("end_time"))
            is_fixed = dt.get("fixed", True)
            
            response += f"## {host_name}"
            if service_desc:
                response += f" / {service_desc}"
            response += "\n"
            response += f"- **Start:** {start}\n"
            response += f"- **End:** {end}\n"
            response += f"- **Type:** {'Fixed' if is_fixed else 'Flexible'}\n"
            response += f"- **Author:** {author}\n"
            response += f"- **Comment:** {comment}\n"
            response += "\n"
        
        return response
        
    except Exception as e:
        tool_logger.error(f"Error listing downtimes: {str(e)}", exc_info=True)
        return f"❌ Error listing downtimes: {str(e)}"

# =============================================================================
# Server Lifecycle
# =============================================================================

# Note: FastMCP handles shutdown automatically
# Logging for shutdown is handled by the MCP framework

# Log that all tools are registered
startup_logger.info("✓ All tools registered")
startup_logger.info("=" * 70)
startup_logger.info("Thruk MCP Server Ready")
startup_logger.info("=" * 70)

# =============================================================================
# Main Entry Point
# =============================================================================

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Thruk MCP Server - Supports stdio and HTTP transports"
    )
    parser.add_argument(
        "--listen",
        type=int,
        metavar="PORT",
        help="Run as HTTP server on specified port (default: stdio mode)"
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_arguments()

    if args.listen:
        # HTTP transport mode - use streamable-http for JSON-RPC over HTTP
        startup_logger.info(f"Starting MCP server in HTTP mode on port {args.listen}")
        startup_logger.info(f"Server will be available at: http://0.0.0.0:{args.listen}")
        startup_logger.info(f"MCP endpoint: http://0.0.0.0:{args.listen}/mcp/v1")
        try:
            # Get the FastMCP streamable HTTP ASGI app and run it with uvicorn
            # This allows us to specify custom host and port
            uvicorn.run(
                mcp.streamable_http_app,
                host="0.0.0.0",
                port=args.listen,
                log_level="info"
            )
        except Exception as e:
            startup_logger.error(f"Failed to start HTTP server: {e}", exc_info=True)
            sys.exit(1)
    else:
        # Default stdio transport mode
        startup_logger.info("Starting MCP server in stdio mode")
        try:
            mcp.run()
        except Exception as e:
            startup_logger.error(f"Failed to start stdio server: {e}", exc_info=True)
            sys.exit(1)
