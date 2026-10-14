# ─── Build stage ───
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy project files and install
COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# ─── Runtime stage ───
FROM python:3.12-slim-bookworm

LABEL maintainer="audio-downloader"
LABEL description="Self-hosted audio downloader backend"

# Install runtime dependencies: ffmpeg, ffprobe, curl (for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Create data directories with correct ownership
RUN mkdir -p /data/output /data/tmp /data/db && \
    chown -R appuser:appuser /data

# Set working directory
WORKDIR /app

# Copy application code
COPY app/ ./app/

# Switch to non-root user
USER appuser

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Run with uvicorn
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "warning"]
