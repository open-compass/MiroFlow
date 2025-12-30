# Multi-stage Dockerfile for MiroFlow AgentCompass Service
# This image includes the FastAPI service for MiroFlow agent framework

FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    curl \
    git \
    # For audio processing
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Upgrade pip and install build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel uv

# Copy project files
COPY pyproject.toml /app/
COPY uv.lock /app/

# Install Python dependencies using uv for faster installation
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy the entire project
COPY . /app/

# Create .env from template if not exists
RUN if [ ! -f .env ]; then cp .env.template .env; fi

# Create necessary directories
RUN mkdir -p logs data

# Expose port
# 8082 for FastAPI service (MiroFlow default port)
EXPOSE 8082

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Set environment variables
ENV PYTHONPATH=/app
ENV LOGGER_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

# Run the startup script
CMD ["/app/start.sh"]
