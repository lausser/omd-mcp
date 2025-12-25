"""
Thruk MCP Server - Placeholder Implementation

This is a minimal MCP server that provides a health endpoint.
Replace this with full Thruk API integration when ready.
"""

import os
import sys
import asyncio
import logging
from typing import Any
from dotenv import load_dotenv
from fastmcp import FastMCP

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("Thruk MCP Server")

# Thruk API configuration
THRUK_BASE_URL = os.getenv("THRUK_BASE_URL", "")
THRUK_API_KEY = os.getenv("THRUK_API_KEY", "")
THRUK_VERIFY_SSL = os.getenv("THRUK_VERIFY_SSL", "true").lower() == "true"


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
        "thruk_configured": bool(THRUK_BASE_URL and THRUK_API_KEY)
    }


@mcp.tool()
async def get_thruk_status(username: str) -> dict[str, Any]:
    """
    Placeholder tool for getting Thruk status.

    Args:
        username: User session username for authorization

    Returns:
        Placeholder response
    """
    logger.info(f"get_thruk_status called for user: {username}")
    return {
        "message": "Thruk MCP server is running",
        "username": username,
        "note": "This is a placeholder. Implement full Thruk API integration."
    }


def main():
    """Main entry point for the MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Thruk MCP Server")
    parser.add_argument(
        "--listen",
        type=int,
        default=int(os.getenv("PORT", "8001")),
        help="Port to listen on (default: 8001)"
    )
    parser.add_argument(
        "--host",
        default=os.getenv("HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    logger.info(f"Starting Thruk MCP server on {args.host}:{args.listen}")
    logger.info(f"Thruk Base URL: {THRUK_BASE_URL or 'NOT CONFIGURED'}")

    if not THRUK_BASE_URL or not THRUK_API_KEY:
        logger.warning("THRUK_BASE_URL or THRUK_API_KEY not configured")

    # Run the FastMCP server
    try:
        mcp.run(transport="sse", host=args.host, port=args.listen)
    except Exception as e:
        logger.error(f"Failed to start MCP server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
