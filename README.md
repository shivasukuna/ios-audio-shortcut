# iOS Audio Shortcut Backend

A lightweight, self-hosted media processing backend designed for Apple Shortcuts on iOS. Extract high-quality audio from supported YouTube and Instagram URLs directly into your iPhone's Files app.

---

## Architecture Overview

```text
[ iPhone Share Sheet ] ──> [ Apple Shortcut ]
                                  │
                                  ▼ (POST /api/v1/jobs)
                       [ Render FastAPI Backend ]
                                  │
                       (yt-dlp + FFmpeg extraction)
                                  │
                                  ▼ (GET /file?token=...)
                       [ Downloaded to iPhone Files ]
```

---

## 🚀 1-Click Deploy to Render

Deploy natively to Render without Docker:

1. Fork or push this repository to GitHub.
2. In [Render Dashboard](https://dashboard.render.com), click **New +** → **Blueprint**.
3. Select this repository (`render.yaml` will auto-configure everything).
4. Render will deploy the service and output your live URL (`https://<your-service>.onrender.com`).
5. Copy your **Service URL** and the auto-generated **`API_TOKEN`** from your Render Environment tab.

---

## 📱 iOS Shortcut Setup

1. Open the [**iOS Shortcut Build Guide**](docs/ios-shortcut.md).
2. Follow the step-by-step actions to build the **Audio Downloader** shortcut.
3. Paste your Render URL and `API_TOKEN` into the shortcut's `Config` dictionary.
4. Share any supported link from Safari, YouTube, or Instagram directly from the iOS Share Sheet.

Audio is saved automatically to:
```text
On My iPhone / Shortcuts / Audio Downloads /
```

---

## 💻 Local Development

```bash
# Clone and enter repo
git clone https://github.com/shivasukuna/ios-audio-shortcut.git
cd ios-audio-shortcut

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run server
uvicorn app.main:app --reload --port 8000
```

Run test suite:
```bash
pytest tests/ -v -m "not integration"
```

---

## 📚 Documentation

- [iOS Shortcut Build Guide](docs/ios-shortcut.md)
- [API Reference](docs/api.md)
- [System Architecture](docs/architecture.md)
- [Deployment & Operations](docs/deployment.md)
- [Health Monitoring](docs/monitoring.md)
- [Troubleshooting Guide](docs/troubleshooting.md)

---

## License

MIT
