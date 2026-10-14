# iOS Shortcut Construction Guide: "Audio Downloader"

This guide describes how to construct the **Audio Downloader** Shortcut on iOS. It is designed to work seamlessly with Safari, social media Share Sheets, or standalone execution.

---

## 1. Prerequisites on iPhone

1. **Create Destination Folder**:
   - Open the **Files** app on your iPhone.
   - Tap **On My iPhone**.
   - Tap the `...` menu in the top right → **New Folder**.
   - Name it `Shortcuts`.
   - Open `Shortcuts`, tap `...` → **New Folder**, name it `Audio Downloads`.
   - Resulting path: `On My iPhone/Shortcuts/Audio Downloads/`.
2. **Obtain Backend Credentials**:
   - Your Render URL (e.g., `https://ios-audio-downloader.onrender.com`) without a trailing slash.
   - Your secret `API_TOKEN` configured in Render environment variables.

---

## 2. Shortcut Overview

```mermaid
graph TD
    A[Share Sheet or Direct Launch] --> B{Has Input?}
    B -->|Yes| C[Extract URL]
    B -->|No| D[Ask for URL via Prompt]
    C --> E[Validate Allowed Domains]
    D --> E
    E -->|Invalid| F[Show Error Alert & Stop]
    E -->|Valid| G[Prompt Quality Menu]
    G --> H[POST /api/v1/jobs]
    H --> I[Parse job_id]
    I --> J[Repeat Loop 60x with 3s Wait]
    J --> K[GET /api/v1/jobs/{job_id}]
    K --> L{Status?}
    L -->|completed| M[Exit Repeat]
    L -->|failed| N[Show Error Alert & Stop]
    L -->|processing/queued| J
    M --> O[GET /api/v1/jobs/{job_id}/file with Auth]
    O --> P[Parse download_url with Token]
    P --> Q[GET file bytes via token download_url]
    Q --> R[Set Name from metadata]
    R --> S[Save File to On My iPhone/Shortcuts/Audio Downloads]
    S --> T[Show Notification: Download Complete]
```

---

## 3. Step-by-Step Action Builder

Create a new Shortcut named **Audio Downloader** in the Shortcuts app:

### Step 1: Shortcut Details & Share Sheet Setup
1. Tap the shortcut name at the top → **Rename** → `Audio Downloader`.
2. Tap the `(i)` Details icon at the bottom:
   - Turn **ON** `Show in Share Sheet`.
   - Tap `Share Sheet Types` → select only **URLs** and **Safari web pages** (uncheck others).

---

### Step 2: Server Variables Configuration
Add a **Dictionary** action at the very top to hold your deployment credentials:
- **Action**: `Dictionary`
  - Key `baseURL` (Text): `https://ios-audio-downloader.onrender.com`
  - Key `apiToken` (Text): `YOUR_ACTUAL_API_TOKEN`
- **Action**: `Set Variable`
  - Variable Name: `Config`
  - Input: Result of Dictionary

---

### Step 3: Input Capture & URL Extraction
- **Action**: `If`
  - Input: `Shortcut Input`
  - Condition: `has any value`
- **Action**: `Get URLs from`
  - Input: `Shortcut Input`
- **Action**: `Set Variable`
  - Variable Name: `TargetURL`
  - Input: URLs from input
- **Action**: `Otherwise`
- **Action**: `Ask for Input`
  - Prompt: `Enter YouTube or Instagram URL:`
  - Input Type: `URL`
- **Action**: `Set Variable`
  - Variable Name: `TargetURL`
  - Input: Provided Input
- **Action**: `End If`

---

### Step 4: Client-side Domain Validation
- **Action**: `If`
  - Input: `TargetURL`
  - Condition: `does not contain`
  - Text: `youtu`
- **Action**: `If`
  - Input: `TargetURL`
  - Condition: `does not contain`
  - Text: `instagram.com`
- **Action**: `Show Alert`
  - Title: `Unsupported Link`
  - Message: `Please provide a valid YouTube or Instagram link.`
- **Action**: `Stop this shortcut`
- **Action**: `End If`
- **Action**: `End If`

---

### Step 5: Format & Quality Selection
- **Action**: `Choose from Menu`
  - Prompt: `Select Audio Quality:`
  - Options:
    1. `High (192 kbps MP3) [Recommended]`
    2. `Standard (128 kbps MP3)`
    3. `Best (320 kbps MP3)`
    4. `Original Audio (Lossless/Best)`
- **Menu Items**:
  - Under `High (192 kbps MP3)`:
    - **Action**: `Text`: `192k`
    - **Action**: `Set Variable`: `SelectedQuality`
  - Under `Standard (128 kbps MP3)`:
    - **Action**: `Text`: `128k`
    - **Action**: `Set Variable`: `SelectedQuality`
  - Under `Best (320 kbps MP3)`:
    - **Action**: `Text`: `320k`
    - **Action**: `Set Variable`: `SelectedQuality`
  - Under `Original Audio`:
    - **Action**: `Text`: `best`
    - **Action**: `Set Variable`: `SelectedQuality`
- **Action**: `End Menu`

---

### Step 6: Submit Job to API
- **Action**: `Dictionary` (Construct JSON request body)
  - Key `url` (Text): `TargetURL`
  - Key `format` (Text): `mp3`
  - Key `quality` (Text): `SelectedQuality`
- **Action**: `Get Contents of URL`
  - URL: `Config.baseURL/api/v1/jobs`
  - Method: `POST`
  - Headers:
    - `Authorization`: `Bearer Config.apiToken`
    - `Content-Type`: `application/json`
  - Request Body: `JSON` → (Pass previous Dictionary)
- **Action**: `Get Dictionary from Input`
  - Input: Contents of URL
- **Action**: `Get Dictionary Value`
  - Key: `job_id`
- **Action**: `Set Variable`
  - Variable Name: `JobID`

---

### Step 7: Polling Status Loop
- **Action**: `Repeat`
  - Count: `60` (60 iterations × 3s = 3 minutes timeout)
- **Action**: `Wait`
  - Time: `3 seconds`
- **Action**: `Get Contents of URL`
  - URL: `Config.baseURL/api/v1/jobs/JobID`
  - Method: `GET`
  - Headers:
    - `Authorization`: `Bearer Config.apiToken`
- **Action**: `Get Dictionary from Input`
- **Action**: `Get Dictionary Value`
  - Key: `status`
- **Action**: `If`
  - Condition: `is`
  - Text: `completed`
  - **Action**: `Get Dictionary Value` for key `output_filename` → `Set Variable`: `OutputFilename`
  - **Action**: `Exit Repeat`
- **Action**: `Otherwise`
- **Action**: `If`
  - Condition: `is`
  - Text: `failed`
  - **Action**: `Get Dictionary Value` for key `error_message`
  - **Action**: `Show Alert`: `Download Failed: Dictionary Value`
  - **Action**: `Stop this shortcut`
- **Action**: `End If`
- **Action**: `End If`
- **Action**: `End Repeat`

---

### Step 8: Fetch Download Token and Binary File
- **Action**: `Get Contents of URL`
  - URL: `Config.baseURL/api/v1/jobs/JobID/file`
  - Method: `GET`
  - Headers:
    - `Authorization`: `Bearer Config.apiToken`
- **Action**: `Get Dictionary from Input`
- **Action**: `Get Dictionary Value`
  - Key: `download_url`
- **Action**: `Set Variable`: `RelativeDownloadURL`
- **Action**: `Get Contents of URL`
  - URL: `Config.baseURLRelativeDownloadURL`
  - Method: `GET`
  - *(Note: No auth header required here; single-use token is embedded in the query string)*
- **Action**: `Set Name`
  - Name: `OutputFilename`
  - Dont Include Extension: `OFF`

---

### Step 9: Save File and Notify
- **Action**: `Save File`
  - Input: Renamed file
  - Ask Where to Save: `OFF`
  - Destination Path: `Shortcuts/Audio Downloads`
  - Overwrite If File Exists: `ON`
- **Action**: `Show Notification`
  - Title: `Audio Downloaded`
  - Body: `Saved OutputFilename to Shortcuts/Audio Downloads`
  - Play Sound: `ON`

---

## 4. First-Run Prompts and Permissions

On first execution, iOS will request permission for:
1. **Network Access**: Allow connection to your Render domain.
2. **Files App Access**: Allow Shortcuts to save files to `On My iPhone/Shortcuts/Audio Downloads`.
3. **Notifications**: Allow Shortcuts to display banners when complete.

Tap **Always Allow** for each to make future downloads seamless from the Share Sheet.
