#!/bin/bash
set -euo pipefail

GANACHE_PID_FILE="/tmp/ganache.pid"
GANACHE_LOG_FILE="/tmp/ganache.log"

echo "🚀 Starting Ganache CLI..."

# Check if Ganache is already running
if [ -f "$GANACHE_PID_FILE" ]; then
    PID=$(cat "$GANACHE_PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  Ganache is already running with PID $PID"
        exit 1
    else
        rm -f "$GANACHE_PID_FILE"
    fi
fi

# Start Ganache in background
ganache-cli \
    --host 0.0.0.0 \
    --port 8545 \
    --deterministic \
    --mnemonic "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about" \
    --accounts 10 \
    --defaultBalanceEther 1000 \
    --gasLimit 10000000 \
    --gasPrice 20000000000 \
    --hardfork berlin \
    > "$GANACHE_LOG_FILE" 2>&1 &

GANACHE_PID=$!
echo $GANACHE_PID > "$GANACHE_PID_FILE"

# Wait for Ganache to be ready
echo "⏳ Waiting for Ganache to be ready..."
for i in {1..30}; do
    if curl -s -X POST \
        -H "Content-Type: application/json" \
        --data '{"jsonrpc":"2.0","method":"net_version","params":[],"id":1}' \
        http://localhost:8545 > /dev/null 2>&1; then
        echo "✅ Ganache is ready on http://localhost:8545"
        echo "📝 PID: $GANACHE_PID"
        echo "📝 Logs: $GANACHE_LOG_FILE"
        exit 0
    fi
    sleep 1
done

echo "❌ Ganache failed to start within 30 seconds"
kill $GANACHE_PID 2>/dev/null || true
rm -f "$GANACHE_PID_FILE"
exit 1