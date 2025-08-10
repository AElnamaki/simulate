FROM registry.access.redhat.com/rhel8/rhel:latest

# Install subscription manager and register (requires valid subscription in real use)
# For development, use CentOS Stream or Fedora base images
FROM quay.io/centos/centos:stream8

RUN dnf update -y && \
    dnf install -y \
        git \
        curl \
        wget \
        python3 \
        python3-pip \
        python3-venv \
        gcc \
        gcc-c++ \
        make \
        nodejs \
        npm && \
    dnf clean all

# Install Node.js LTS
RUN curl -fsSL https://rpm.nodesource.com/setup_lts.x | bash - && \
    dnf install -y nodejs

# Install global npm packages
RUN npm install -g ganache-cli@latest solc@latest

# Create app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN python3 -m venv venv && \
    source venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application files
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.sh

# Expose Ganache default port
EXPOSE 8545

# Default command
CMD ["./scripts/start_ganache.sh"]