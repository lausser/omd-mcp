# Dockerfile for MCP Chatbot
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r chatbot && \
    useradd -r -g chatbot -u 1000 chatbot && \
    chown -R chatbot:chatbot /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY --chown=chatbot:chatbot chatbot.py /app/chatbot.py
COPY --chown=chatbot:chatbot ../thruk_mcp/thruk_mcp.py /app/thruk_mcp.py

# Switch to non-root user
USER chatbot

# Expose port
EXPOSE 8080

# Default command
CMD ["python", "-u", "chatbot.py"]
