#!/usr/bin/env bash
# Convenience script to process photos before pushing to GitHub
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "${SCRIPT_DIR}/scripts/process_photos.py" "$@"
