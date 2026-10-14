# API Specification & Reference

Base URL format: `https://<YOUR-RENDER-DOMAIN>`

All API requests except `/health/live`, `/health/ready`, and binary downloads with `?token=` require authentication via Bearer header:
```http
Authorization: Bearer <API_TOKEN>
```

---

## 1. Health & Diagnostics

### `GET /health/live`
- **Auth**: None
- **Response**: `200 OK`
```json
{
  "status": "alive",
  "timestamp": 1728919000.123
}
```

### `GET /health/ready`
- **Auth**: None
- **Response**: `200 OK` or `503 Service Unavailable`
```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "worker_pool": true
  },
  "timestamp": 1728919000.456
}
```

### `GET /health/deep`
- **Auth**: Bearer Token required
- **Response**: `200 OK`
```json
{
  "status": "healthy",
  "components": {
    "database": {
      "healthy": true,
      "total_jobs": 14
    },
    "ffmpeg": {
      "healthy": true,
      "ffmpeg_version": "6.1.1",
      "ffprobe_available": true,
      "ffprobe_version": "6.1.1"
    },
    "yt_dlp": {
      "healthy": true,
      "version": "2024.12.23"
    },
    "worker": {
      "healthy": true,
      "active_jobs": 0,
      "heartbeat_age_seconds": 1.2
    },
    "disk": {
      "healthy": true,
      "used_percent": 18.4,
      "free_gb": 12.4,
      "total_gb": 15.0,
      "warning": false
    },
    "queue": {
      "healthy": true,
      "queued": 0,
      "processing": 0,
      "completed": 12,
      "failed": 2,
      "oldest_job_age_seconds": 0.0
    },
    "temp_storage": {
      "healthy": true,
      "writable": true,
      "orphaned_dirs": 0
    }
  },
  "timestamp": 1728919000.789
}
```

---

## 2. Limits

### `GET /api/v1/limits`
- **Auth**: Bearer Token required
- **Response**: `200 OK`
```json
{
  "max_file_size_mb": 100,
  "max_duration_seconds": 1800,
  "max_playlist_length": 1,
  "max_concurrent_jobs": 2,
  "max_queue_size": 10,
  "supported_formats": ["mp3", "aac", "opus", "m4a"],
  "supported_qualities": ["128k", "192k", "320k", "best"],
  "job_timeout_seconds": 600,
  "artifact_ttl_seconds": 3600,
  "rate_limit_requests": 30,
  "rate_limit_window_seconds": 60
}
```

---

## 3. Job Management

### `POST /api/v1/jobs`
Submit a new audio download task.

- **Auth**: Bearer Token required
- **Request Body**:
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "format": "mp3",
  "quality": "192k"
}
```
- **Response**: `202 Accepted`
```json
{
  "job_id": "4b684cb3-078a-44e2-9b24-b15392cf99a1",
  "status": "queued",
  "status_url": "/api/v1/jobs/4b684cb3-078a-44e2-9b24-b15392cf99a1",
  "created_at": "2026-10-14T16:00:00.000000+00:00"
}
```

---

### `GET /api/v1/jobs/{job_id}`
Poll status of a job.

- **Auth**: Bearer Token required
- **Response**: `200 OK`
```json
{
  "job_id": "4b684cb3-078a-44e2-9b24-b15392cf99a1",
  "status": "completed",
  "progress": 1.0,
  "output_filename": "Rick_Astley_Never_Gonna_Give_You_Up.mp3",
  "output_size": 3491204,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-10-14T16:00:00.000000+00:00",
  "updated_at": "2026-10-14T16:00:12.000000+00:00",
  "expires_at": "2026-10-14T17:00:00.000000+00:00"
}
```

---

### `GET /api/v1/jobs/{job_id}/file` (Mode 1: Generate Download Token)
Fetch temporary token for file retrieval.

- **Auth**: Bearer Token required
- **Response**: `200 OK`
```json
{
  "download_url": "/api/v1/jobs/4b684cb3-078a-44e2-9b24-b15392cf99a1/file?token=NGI2ODRjYjMt...IjoxNzI4OT",
  "expires_in": 300
}
```

---

### `GET /api/v1/jobs/{job_id}/file?token={token}` (Mode 2: Binary File Download)
Download binary audio bytes.

- **Auth**: None (Token validated from query string)
- **Response Headers**:
  - `Content-Type`: `audio/mpeg`
  - `Content-Disposition`: `attachment; filename="Rick_Astley_Never_Gonna_Give_You_Up.mp3"`
- **Response Body**: Binary audio stream.

---

### `DELETE /api/v1/jobs/{job_id}`
Cancel an in-progress job or purge completed media.

- **Auth**: Bearer Token required
- **Response**: `200 OK`
```json
{
  "job_id": "4b684cb3-078a-44e2-9b24-b15392cf99a1",
  "status": "cancelled",
  "detail": "Job cancelled and artifacts cleaned up"
}
```
