# Troubleshooting & Recovery Guide

This guide covers common errors encountered when using the iOS Shortcut or running the backend on Render.

---

## 1. Shortcut Issues

### "Unsupported Link" Alert
- **Cause**: The shared text did not match allowed host domains (`youtube.com`, `youtu.be`, `instagram.com`).
- **Fix**: Check that you are sharing from the official YouTube or Instagram app via the Share button, or sharing a clean URL from Safari.

### "Download Failed: Download token is invalid or expired"
- **Cause**: The client took more than 5 minutes (`DOWNLOAD_TOKEN_TTL_SECONDS`) between receiving the download URL and requesting the file.
- **Fix**: Ensure your iPhone has stable cellular/Wi-Fi reception. Re-run the shortcut.

### "Files app: Cannot save to folder"
- **Cause**: The destination directory `Shortcuts/Audio Downloads` was not manually created before the first save.
- **Fix**: Open the **Files** app on iPhone → Navigate to **On My iPhone** → Create folder `Shortcuts` → Inside it, create folder `Audio Downloads`.

---

## 2. Platform Extraction Failures

### YouTube: "Sign in to confirm you're not a bot"
- **Cause**: YouTube periodically flags data center IPs (such as AWS, GCP, or Render IPs) with bot verification challenges.
- **Remedy**:
  1. Trigger a redeploy to get a new container IP.
  2. Upgrade `yt-dlp` in `requirements.txt` to the latest release (`pip install -U yt-dlp`).
  3. Ensure playlist length is limited to 1 (`MAX_PLAYLIST_LENGTH=1`).

### Instagram: "Login required / Post unavailable"
- **Cause**: Instagram enforces login walls on private accounts, age-restricted posts, or certain carousels.
- **Status**: The MVP only supports publicly accessible Reels and videos without authentication.
- **Remedy**: The backend gracefully returns a user-friendly error `extraction_failed: Private or login-required media`.

---

## 3. Server Crash Recovery

If the Render host restarts or crashes mid-processing:
1. Upon restart, the database initialization runs `recover_stale_jobs()`.
2. Any job left in `processing` state is automatically transitioned to `failed` with error code `server_restart`.
3. The queue remains clean and does not block subsequent client submissions.
