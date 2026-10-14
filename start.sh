#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Render Native Start Script for iOS Audio Downloader
# ─────────────────────────────────────────────────────────────
set -o errexit

# Add ./bin to PATH so ffmpeg and ffprobe are immediately discoverable
export PATH="$PWD/bin:$PATH"

PORT="${PORT:-8000}"

echo "==> Starting Audio Downloader API on port $PORT..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1 --log-level info
