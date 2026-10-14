# Deployment & Operations Guide

This guide details how to deploy the **iOS Audio Downloader** natively to **Render** (no Docker required) as well as running locally for testing.

---

## 1. Render Deployment (Production)

Render provides native Python hosting with automatic HTTPS, zero server maintenance, and Git-based continuous deployment.

### Method A: One-Click Blueprint Deployment (Recommended)

1. Push your project files to a private or public GitHub/GitLab repository.
2. In the [Render Dashboard](https://dashboard.render.com), click **New** → **Blueprint**.
3. Connect your repository. Render will automatically detect `render.yaml`.
4. Review the configured service:
   - **Service Type**: Web Service
   - **Environment**: Python
   - **Build Command**: `bash build.sh`
   - **Start Command**: `bash start.sh`
   - **Plan**: Free
5. Render will automatically generate a secure `API_TOKEN` and deploy your application.
6. Copy the generated URL (`https://ios-audio-downloader.onrender.com`) and your `API_TOKEN` from **Environment Variables** into your iOS Shortcut configuration.

---

### Method B: Manual Web Service Setup

If you prefer configuring through the Render UI:

1. Click **New +** → **Web Service**.
2. Connect your Git repository.
3. Configure the following fields:
   - **Name**: `ios-audio-downloader`
   - **Region**: Choose closest to you (e.g. Oregon, Frankfurt, Singapore)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `bash build.sh`
   - **Start Command**: `bash start.sh`
   - **Instance Type**: Free
4. Add **Environment Variables**:
   | Variable | Value | Description |
   |---|---|---|
   | `API_TOKEN` | `<YOUR_SECRET_TOKEN>` | Generate via: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `PYTHON_VERSION` | `3.12.0` | Target Python version |
   | `OUTPUT_DIR` | `data/output` | Media output directory |
   | `TEMP_DIR` | `data/tmp` | Temporary scratch folder |
   | `DB_PATH` | `data/db/jobs.db` | SQLite database |
   | `LOG_LEVEL` | `INFO` | Application log level |
   | `MAX_FILE_SIZE_MB` | `100` | Max audio file size |
   | `MAX_DURATION_SECONDS`| `1800` | 30 minutes limit |
5. Click **Create Web Service**.

> [!NOTE]
> `build.sh` automatically fetches a static Linux x86_64 FFmpeg release if ffmpeg is not already present on the Render host, making media extraction work seamlessly without root privileges or Docker.

---

## 2. Local Development Setup (Native Python, No Docker)

### Prerequisites
- Python 3.12+
- `ffmpeg` and `ffprobe` installed on your machine and available in `PATH`.
  - Windows: `winget install Gyan.FFmpeg` or `choco install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

### Installation Steps
```bash
# 1. Clone/navigate to directory
cd "iOS audio/audio-downloader"

# 2. Create virtual environment
python -m venv .venv

# 3. Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env configuration
cp .env.example .env
# Edit .env to set API_TOKEN
```

### Running Locally
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## 3. Maintenance & Periodic Upgrades

### Upgrading yt-dlp on Render
Video platforms frequently alter their internal APIs and cipher signatures. To update yt-dlp to the latest release:

1. Update the pinned version in `requirements.txt` or change to `yt-dlp>=2024.12.0`.
2. Commit and push:
```bash
git commit -am "chore: upgrade yt-dlp to latest version"
git push
```
3. Render will automatically rebuild and deploy within 1–2 minutes.
