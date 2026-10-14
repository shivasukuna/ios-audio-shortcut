#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Render Native Build Script for iOS Audio Downloader
# ─────────────────────────────────────────────────────────────
set -o errexit

echo "==> Upgrading pip and installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "==> Ensuring local directories exist..."
mkdir -p data/output data/tmp data/db bin

# Install static FFmpeg + FFprobe on Linux x86_64 if not already available in PATH
if ! command -v ffmpeg &> /dev/null; then
    if [ ! -f "bin/ffmpeg" ]; then
        echo "==> Installing static FFmpeg & FFprobe binary for Linux..."
        FFMPEG_TAR_URL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        curl -fsSL "$FFMPEG_TAR_URL" -o ffmpeg.tar.xz
        tar -xf ffmpeg.tar.xz --strip-components=1 -C bin --wildcards "*/ffmpeg" "*/ffprobe"
        rm -f ffmpeg.tar.xz
        chmod +x bin/ffmpeg bin/ffprobe
        echo "==> FFmpeg and FFprobe installed successfully to ./bin"
    else
        echo "==> Cached ./bin/ffmpeg found"
    fi
else
    echo "==> System ffmpeg detected: $(ffmpeg -version | head -n1)"
fi

echo "==> Build finished successfully."
