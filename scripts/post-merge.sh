#!/bin/bash
set -e

echo "[post-merge] ZeusDL post-merge setup starting..."

# Install/sync Python dependencies if pip is available
if command -v pip &> /dev/null; then
    echo "[post-merge] Installing Python dependencies..."
    pip install --quiet --upgrade pip
    if [ -f "zeusdl/zeusdl/pyproject.toml" ]; then
        pip install --quiet -e "zeusdl/zeusdl[default]" 2>/dev/null || true
    fi
fi

echo "[post-merge] Done."
