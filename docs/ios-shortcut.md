# iOS Shortcut Setup Guide (Easy Step-by-Step)

This guide shows you the **easiest and fastest way** to build the **Audio Downloader** shortcut on your iPhone. 

> [!TIP]
> **Why this is easy**: Thanks to the backend's direct download endpoint, you only need **5 simple actions** in the Shortcuts app! No complicated loops, no JSON dictionaries, no variable juggling. You can finish this in under 2 minutes.

---

## 📁 Step 0: Create the Destination Folder on your iPhone (One-time)

1. Open the **Files** app on your iPhone.
2. Tap the **Browse** tab at the bottom, then tap **On My iPhone**.
3. Tap the **`...`** (three dots) circle in the top-right corner → tap **New Folder**.
4. Type `Shortcuts` and tap **Done**.
5. Tap inside your new `Shortcuts` folder.
6. Tap the **`...`** in the top-right → tap **New Folder** again.
7. Type `Audio Downloads` and tap **Done**.

*(Resulting folder: `On My iPhone / Shortcuts / Audio Downloads`)*

---

## ⚡ Step 1: Create the Shortcut

1. Open the **Shortcuts** app on your iPhone.
2. Tap the **`+`** (plus) icon in the top right corner to create a new shortcut.
3. Tap the dropdown arrow at the top next to "New Shortcut" → tap **Rename** → type:
   ```text
   Audio Downloader
   ```
4. Tap the **`ⓘ` (Details)** button at the bottom of the screen:
   - Turn **ON** `Show in Share Sheet`.
   - Tap **Share Sheet Types** right below it.
   - Tap **Deselect All**, then turn **ON** only:
     - **URLs**
     - **Safari web pages**
   - Tap **Done** in the top right.

---

## 🛠️ Step 2: Add the 5 Actions

At the bottom of your screen, there is a search bar: **"Search for apps and actions"**. You will use this search bar to add each action one by one.

---

### Action 1: Handle Link from Share Sheet or Direct Tap
1. In the search bar at the bottom, type: **`If`**
2. Tap the action called **If** (under Scripting).
3. In the new box that appears:
   - Tap **Condition** → choose **has any value**.
4. Now in the search bar at the bottom, type: **`Get URLs from Input`**
5. Tap **Get URLs from Input**.
6. Tap and hold this action, then drag it directly between **If** and **Otherwise**.
7. In the search bar, type: **`Ask for Input`**
8. Tap **Ask for Input**.
9. In the box:
   - Tap **Prompt** → type: `Paste Instagram Link:`
   - Tap **Text** → change it to **URL**.
10. Drag this action directly between **Otherwise** and **End If**.

---

### Action 2: Wake up the Server (Render Free Tier)
Because Render free services sleep after 15 minutes of inactivity, pinging it wakes it up:
1. In the search bar, type: **`URL`**
2. Tap the action called **URL**.
3. In the box, paste this exact wake-up URL:
   ```text
   https://ios-audio-downloader.onrender.com/health/live
   ```
4. In the search bar, type: **`Get Contents of URL`**
5. Tap **Get Contents of URL**.

---

### Action 3: Build the Download Link
1. In the search bar, type: **`URL`**
2. Tap the action called **URL**.
3. In the text box, paste this exact text:
   ```text
   https://ios-audio-downloader.onrender.com/api/v1/download?token=cL9MNRKSyTCcwyv1QEdNK7O/PiMmZmuqxyhI6uyzHvA=&url=
   ```
4. Immediately after `url=`, tap the **Shortcut Input** (or tap **Select Variable** and tap the `If Result` at the top of your shortcut).
   *(Your URL will look like: `https://ios-audio-downloader.onrender.com/api/v1/download?token=...&url=[If Result]`)*

---

### Action 4: Download the Audio File
1. In the search bar, type: **`Get Contents of URL`**
2. Tap **Get Contents of URL**.
   *(It will automatically connect to the URL above).*

---

### Action 5: Save File to Audio Downloads
1. In the search bar, type: **`Save File`**
2. Tap the action called **Save File** (with the blue folder icon).
3. In the box that appears:
   - Tap the arrow **`>`** next to "Save File".
   - Turn **OFF** `Ask Where to Save`.
   - In **Shortcuts Path**, type:
     ```text
     Audio Downloads
     ```
   - (Or tap the folder name to pick `Shortcuts/Audio Downloads`).
4. In the search bar, type: **`Show Notification`**
5. Tap **Show Notification**.
   - Set message to: `Audio Saved to Files! 🎵`

Tap **Done** in the top-right corner. **Your shortcut is ready!**

---

## 📲 How to Use It from Instagram

1. Open **Instagram** on your iPhone.
2. Find any public Reel or video post.
3. Tap the **Share** button (the paper airplane icon).
4. Tap **Share via...** (or scroll to the right in the share menu and tap **More**).
5. Tap **Audio Downloader**.
6. Wait a few seconds — the audio extracts and saves directly to:
   ```text
   Files app → On My iPhone → Shortcuts → Audio Downloads
   ```
7. You will hear a chime and see the `Audio Saved to Files! 🎵` notification.
