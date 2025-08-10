#!/bin/bash
# RHEL-compatible provisioning script
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv"

echo "🔧 Starting RHEL-compatible blockchain development environment setup..."

# Check if running on RHEL/CentOS/Fedora
if ! command -v dnf &> /dev/null && ! command -v yum &> /dev/null; then
    echo "⚠️  Warning: This script is optimized for RHEL-based systems"
fi

# Update system packages
echo "📦 Updating system packages..."
if command -v dnf &> /dev/null; then
    sudo dnf update -y
    sudo dnf install -y git curl wget python3 python3-pip python3-venv nodejs npm gcc gcc-c++ make
elif command -v yum &> /dev/null; then
    sudo yum update -y
    sudo yum install -y git curl wget python3 python3-pip nodejs npm gcc gcc-c++ make
    # For older RHEL/CentOS, may need EPEL
    sudo yum install -y epel-release
fi

# Install Node.js LTS if not recent enough
NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' || echo "0.0.0")
REQUIRED_NODE="16.0.0"
if [ "$(printf '%s\n' "$REQUIRED_NODE" "$NODE_VERSION" | sort -V | head -n1)" != "$REQUIRED_NODE" ]; then
    echo "📦 Installing Node.js LTS..."
    curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
    if command -v dnf &> /dev/null; then
        sudo dnf install -y nodejs
    else
        sudo yum install -y nodejs
    fi
fi

# Install Ganache CLI globally
echo "🔗 Installing Ganache CLI..."
sudo npm install -g ganache-cli@latest

# Verify Ganache installation
if ! command -v ganache-cli &> /dev/null; then
    echo "❌ Ganache CLI installation failed"
    exit 1
fi
echo "✅ Ganache CLI installed: $(ganache-cli --version)"

# Install Solidity compiler
echo "🔨 Installing Solidity compiler..."
sudo npm install -g solc@latest

# Setup Python virtual environment
echo "🐍 Setting up Python virtual environment..."
python3 -m venv "$VENV_PATH"
source "$VENV_PATH/bin/activate"

# Upgrade pip and install requirements
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt

# Install systemd service for Ganache
echo "🔧 Installing systemd service for Ganache..."
sudo cp systemd/start-ganache.service /etc/systemd/system/
sudo systemctl daemon-reload

# Make scripts executable
chmod +x scripts/*.sh

echo "✅ Provisioning complete!"
echo "📋 Next steps:"
echo "   1. source venv/bin/activate"
echo "   2. sudo systemctl start start-ganache"
echo "   3. python deploy.py"
echo "   4. python simulator/run_simulation.py"

# Verification
echo "🔍 Verification checks:"
echo "   Node.js: $(node --version)"
echo "   npm: $(npm --version)"
echo "   Python: $(python3 --version)"
echo "   Ganache: $(ganache-cli --version)"
echo "   Solc: $(solc --version | head -1)"

exit 0