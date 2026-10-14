# Health Monitoring & Alerting Guide

The application implements three dedicated health levels for automated uptime probes, dependency checks, and internal queue diagnostics.

---

## 1. Probes Reference

| Endpoint | Probe Type | Authentication | Description |
|---|---|---|---|
| `GET /health/live` | Liveness | None | Checks if Uvicorn and FastAPI process is running. Used by Render health probes. |
| `GET /health/ready` | Readiness | None | Verifies database connectivity and worker thread pool availability. |
| `GET /health/deep` | Diagnostics | Bearer Token | In-depth component audit: FFmpeg/ffprobe, yt-dlp, disk space %, queue depth, oldest job age. |

---

## 2. Setting Up External Monitoring

To receive alerts when the server goes down or TLS expires:

### Render Built-In Monitoring
- Set **Health Check Path** in Render Settings to `/health/live`.
- Render automatically sends email notifications on deployment failures or unhealthy crashes.

### External Uptime Services (e.g., UptimeRobot, BetterStack, StatusCake)
1. Add an **HTTP(s) Monitor**:
   - URL: `https://<YOUR-RENDER-APP>.onrender.com/health/ready`
   - Monitoring Interval: `1 minute` or `5 minutes`
   - Expected Response Code: `200`
2. Add an **SSL Certificate Expiry Monitor**:
   - Check SSL expiration 14 days before expiry (Render renews certificates automatically, but this provides peace of mind).

---

## 3. Storage & Disk Pressure Thresholds

The API enforces the following automated thresholds:
- **80% Disk Usage**: Emits a `warning: true` flag in `/health/deep`.
- **90% Disk Usage**: Automatically rejects new jobs with `503 Service Unavailable` (`DISK_FULL`) to protect SQLite and the host OS.
- **TTL Pruning**: The background maintenance loop runs every 60 seconds and removes completed audio files older than `ARTIFACT_TTL_SECONDS` (default 1 hour).
