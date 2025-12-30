#!/bin/bash
# Build script for MiroFlow Docker image

set -e

# Configuration
IMAGE_NAME="opencompass/miroflow-service"
IMAGE_TAG="v1.0.0"
FULL_IMAGE_NAME="${IMAGE_NAME}:${IMAGE_TAG}"

echo "========================================"
echo "🐳 Building MiroFlow Docker Image"
echo "========================================"
echo "Image: ${FULL_IMAGE_NAME}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Build the Docker image
echo "📦 Building Docker image..."
docker build -t "${FULL_IMAGE_NAME}" -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"

echo ""
echo "✅ Build completed successfully!"
echo ""
echo "Image: ${FULL_IMAGE_NAME}"
echo ""
echo "Next steps:"
echo "  1. Run with docker-compose:"
echo "     cd docker && docker-compose up -d"
echo ""
echo "  2. Or run directly:"
echo "     docker run -p 8082:8082 ${FULL_IMAGE_NAME}"
echo ""
