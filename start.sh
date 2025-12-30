#!/bin/bash
set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "========================================"
echo "🚀 Starting MiroFlow Service"
echo "========================================"

# Display proxy configuration if set
if [ -n "$HTTP_PROXY" ] || [ -n "$http_proxy" ] || [ -n "$HTTPS_PROXY" ] || [ -n "$https_proxy" ]; then
    echo ""
    echo "🌐 PROXY CONFIGURATION DETECTED:"
    echo "----------------------------------------"
    [ -n "$HTTP_PROXY" ] && echo "  ✓ HTTP_PROXY=$HTTP_PROXY"
    [ -n "$http_proxy" ] && echo "  ✓ http_proxy=$http_proxy"
    [ -n "$HTTPS_PROXY" ] && echo "  ✓ HTTPS_PROXY=$HTTPS_PROXY"
    [ -n "$https_proxy" ] && echo "  ✓ https_proxy=$https_proxy"
    [ -n "$NO_PROXY" ] && echo "  ✓ NO_PROXY=$NO_PROXY"
    [ -n "$no_proxy" ] && echo "  ✓ no_proxy=$no_proxy"
    echo "----------------------------------------"
    echo "✓ Service will use proxy for network access"
    echo ""
else
    echo ""
    echo "⚠️  NO PROXY CONFIGURED"
    echo "----------------------------------------"
    echo "  Service will use direct connection"
    echo "  If network access fails, set:"
    echo "    -e HTTPS_PROXY=http://your-proxy:port"
    echo "----------------------------------------"
    echo ""
fi

# Start the FastAPI service
echo "📡 Starting MiroFlow FastAPI service on port 8082..."
cd "$SCRIPT_DIR"
exec uvicorn miroflow_service_fastapi:app --host 0.0.0.0 --port 8082 --workers ${WORKERS:-4}
