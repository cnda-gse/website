#!/usr/bin/env bash
set -euo pipefail

# Download and extract the Zola binary
ZOLA_VERSION=0.23.5
curl -sLJO "https://github.com/getzola/zola/releases/download/v${ZOLA_VERSION}/zola-v${ZOLA_VERSION}-x86_64-unknown-linux-gnu.tar.gz"
tar -xf zola-v${ZOLA_VERSION}-x86_64-unknown-linux-gnu.tar.gz

# Optional: Ensure any theme submodules are pulled in
git submodule update --init --recursive

# Execute the downloaded binary
./zola build
