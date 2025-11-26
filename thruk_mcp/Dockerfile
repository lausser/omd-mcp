# Dockerfile for Thruk MCP Server
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r thruk && \
    useradd -r -g thruk -u 1001 thruk && \
    chown -R thruk:thruk /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=thruk:thruk thruk_mcp.py /app/thruk_mcp.py

# Switch to non-root user
USER thruk

# Expose port
EXPOSE 8001

# Default command - run in HTTP mode on port 8001
CMD ["python", "-u", "thruk_mcp.py", "--listen", "8001"]
