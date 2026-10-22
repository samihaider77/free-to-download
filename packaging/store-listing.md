# Browser store submission kit

Everything needed to publish the extension on the **Chrome Web Store** (and Microsoft Edge Add-ons).
Once it is listed, the installer registers it so the browser shows **“New extension added → Enable”**
after installing the app — no folders, no Developer mode, no pairing.

## 1. Upload package

Each GitHub release run produces **`Free-to-Download-store-upload.zip`** as a workflow artifact
(Actions → the release run → *Artifacts* → `browser-store-upload`). It is the extension without the local
`key` field (stores assign their own ID) and **without the button on YouTube**, because the Chrome Web Store
does not allow extensions that download YouTube videos.

## 2. Listing text

**Name:** Free-to-Download

**Summary (132 characters max):**
Adds a “Download this video” button and sends links to the free Free-to-Download desktop app for fast, resumable downloads.

**Category:** Productivity (Tools)

**Description:**

Free-to-Download is a free, open-source download manager for Windows. This extension connects your browser to the Free-to-Download desktop app.

• A “Download this video” button over videos on web pages, with a choice of detected video streams and files
• “Download with Free-to-Download” on any link, image, audio or video (right-click)
• Fast multi-connection downloads with pause and resume, handled by the desktop app
• Connects automatically to the app on your own computer — nothing to configure

Requires the free Free-to-Download app for Windows: https://samihaider77.github.io/free-to-download/

Free-to-Download is for files and videos you own or have permission to download. It does not bypass DRM or other copy protection.
Open source (MIT): https://github.com/samihaider77/free-to-download

**Single purpose:** Send download links and videos from web pages to the user's Free-to-Download desktop app.

**Permission justifications:**
- *Host permissions (http/https):* show the download button over videos on visited pages and notice media streams as they load.
- *webRequest:* read the type and address of media responses (not their contents) so video streams can be offered for download.
- *contextMenus:* the “Download with Free-to-Download” right-click command.
- *storage:* keep the connection token for the local app and a temporary per-tab list of detected media.
- *activeTab / scripting:* list links on the current page when the user presses “Find page links”.
- *nativeMessaging:* start the user's own Free-to-Download app on this computer when it is closed and a download is requested.

**Data usage disclosures:** collects no user data; nothing is sold or transferred; data is used only for the single purpose above.

**Privacy policy URL:** https://samihaider77.github.io/free-to-download/privacy.html

**Images:** icon `browser-extension/icons/icon128.png`; screenshots 1280×800 from `docs/assets/`.

## 3. After approval

1. Copy the extension ID shown in the store dashboard.
2. Add it to `EXTENSION_IDS` in `app/version.py` (so the app trusts it for automatic connection).
3. In the GitHub repo: **Settings → Secrets and variables → Actions → Variables**, add `CHROME_STORE_ID`
   (and `EDGE_STORE_ID` for Edge Add-ons) with that ID.
4. Release a new version. From then on the installer adds the extension to the browser automatically.
