<p align="center">
  <img src="docs/assets/icon.png" width="96" alt="Free-to-Download icon">
</p>

<h1 align="center">Free-to-Download</h1>

<p align="center">
  A free, open-source download manager for Windows with a <b>“Download this video”</b> button in your browser.<br>
  Fast multi-connection downloads, resumable transfers, and video downloads in the quality you choose.
</p>

<p align="center">
  <a href="https://github.com/samihaider77/free-to-download/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/samihaider77/free-to-download?label=download&color=0d9488"></a>
  <a href="https://github.com/samihaider77/free-to-download/actions/workflows/tests.yml"><img alt="Tests" src="https://github.com/samihaider77/free-to-download/actions/workflows/tests.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <img alt="Windows 10/11" src="https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078d4">
</p>

<p align="center">
  <a href="https://github.com/samihaider77/free-to-download/releases/latest/download/Free-to-Download-Setup.exe"><b>⬇ Download for Windows</b></a>
  &nbsp;·&nbsp;
  <a href="https://samihaider77.github.io/free-to-download/">Website</a>
  &nbsp;·&nbsp;
  <a href="#install">Install guide</a>
</p>

<p align="center">
  <img src="docs/assets/video-menu.png" width="760" alt="The Download this video button and quality menu over a video">
</p>

## Features

- **Download this video button** over videos on web pages, with a quality menu: Best, 1080p, 720p, 480p, 360p or audio only (MP3).
- **Works with streaming sites**: YouTube, LinkedIn posts, Vimeo, X and [many more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md) via the page link, plus HLS (`.m3u8`) and DASH (`.mpd`) streams detected while the video plays.
- **Fast file downloads** with up to 16 parallel connections per file and adaptive chunk scheduling.
- **Pause and resume**, even after restarting the app, when the server supports it safely.
- **Progress window** for every download (speed, time left, per-connection or per-fragment progress) and a “Download complete” dialog with *Open* and *Open folder*.
- **Never overwrites your files.** Already-downloaded videos are recognised instead of downloaded twice.
- **Queue tools**: simultaneous-download limit, speed limiter, scheduled starts, batch URL import, categories, search and SHA-256 verification.
- **Private by design.** The browser extension talks only to the app on your own computer, over an authenticated local connection. No accounts, no tracking, no cookies collected.

<p align="center">
  <img src="docs/assets/progress-window.png" width="420" alt="Download progress window">
  &nbsp;
  <img src="docs/assets/complete-dialog.png" width="420" alt="Download complete dialog">
</p>

<p align="center">
  <img src="docs/assets/main-window.png" width="760" alt="Free-to-Download main window">
</p>

## Install

1. **Download** [`Free-to-Download-Setup.exe`](https://github.com/samihaider77/free-to-download/releases/latest/download/Free-to-Download-Setup.exe) and run it.
   No administrator rights needed. Prefer no installer? Use the **Portable ZIP** from the [latest release](https://github.com/samihaider77/free-to-download/releases/latest).
   > Windows may show **“Windows protected your PC”** because the app isn't code-signed yet. Click **More info → Run anyway**.
2. **Add the browser button** (Google Chrome; other Chromium browsers such as Edge and Brave use the same steps):
   1. Open `chrome://extensions` (or `edge://extensions`) and switch on **Developer mode**.
   2. Click **Load unpacked** and select the `browser-extension` folder.
      The installer adds a Start-menu shortcut to it: *Free-to-Download → Browser extension folder*.
   The installer's last page can open Chrome's extensions page and the folder for you.

That's it — the extension connects to the app by itself, with nothing to paste. Play a video, click
**Download this video**, and pick a quality. Tick *Start Free-to-Download when I sign in to Windows* in the
installer so the button always works.

> A Chrome Web Store listing is in progress. Once it is live, the installer adds the extension automatically
> and Chrome simply asks you to **Enable** it.

## How it works

```mermaid
flowchart LR
  A[Web page with a video] --> B[Browser extension<br/>button + quality menu]
  B -- "authenticated request<br/>127.0.0.1 only" --> C[Free-to-Download app]
  C --> D{What was sent?}
  D -- "page link or stream" --> E[yt-dlp<br/>finds and downloads the video]
  D -- "file link" --> F[Multi-connection<br/>HTTP engine]
  E --> G[FFmpeg merges<br/>video + audio]
  G --> H[(Your Downloads folder)]
  F --> H
```

- **Desktop app** — Python + Tkinter (`app/`). The direct-file engine (`downloader.py`) splits a file into byte ranges and downloads them over persistent parallel connections. It resumes only when the server proves the file hasn't changed (strong ETag, validated ranges), and publishes the finished file atomically without ever overwriting an existing one.
- **Video downloads** (`media.py`) use [yt-dlp](https://github.com/yt-dlp/yt-dlp) to find and fetch the right streams, and [FFmpeg](https://ffmpeg.org) to combine audio and video into an MP4 that plays everywhere. A final check rejects results that contain no audio or video data, such as a stream header saved by mistake.
- **Browser extension** — Chrome Manifest V3 (`browser-extension/`). It adds the on-video button, notices media streams while a video plays, and sends your choice to the app.
- **Local bridge** (`bridge.py`) — an HTTP server bound to `127.0.0.1`. The extension pairs automatically: the app hands its token only to requests that the browser stamps with the extension's own fixed ID (`Origin: chrome-extension://…`), which web pages and other extensions cannot forge. Every download request is then checked for the token, origin, host and size.

## Build from source

Requirements: Windows 10/11, Python 3.12, Node.js (for the extension tests only).

```powershell
git clone https://github.com/samihaider77/free-to-download.git
cd free-to-download
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-build.txt

# Run from source
python app\main.py

# Tests
python -m unittest discover -s app -p "test_*.py"
node test_extension.cjs

# Build the app (dist\Free-to-Download\Free-to-Download.exe)
python -m PyInstaller --noconfirm --distpath dist --workpath build packaging\free-to-download.spec
```

The installer is built with [Inno Setup](https://jrsoftware.org/isinfo.php): `iscc /DAppVersion=0.6.0 packaging\installer.iss`.
Store publishing steps are in [`packaging/store-listing.md`](packaging/store-listing.md).

**Releases are automated.** Pushing a tag such as `v0.6.0` runs [`release.yml`](.github/workflows/release.yml), which tests, builds, smoke-tests the packaged app with real downloads, and publishes the installer, portable ZIP and checksums. Keep `app/version.py` and `browser-extension/manifest.json` at the same version as the tag.

## Project structure

```
app/                 desktop app (UI, download engines, local bridge) and its tests
browser-extension/   Chrome/Edge extension (video button, stream detection, popup, pairing)
packaging/           PyInstaller spec, Inno Setup installer script, icon, release notes
docs/                project website (GitHub Pages) and screenshots
.github/workflows/   tests on every push; build and publish on version tags
```

## Responsible use

Free-to-Download is meant for videos and files you own or have permission to download, such as your own uploads, public-domain or Creative Commons media, and course or work material you're allowed to save. Respect each website's terms of service and copyright law. It does **not** bypass DRM or other copy protection, and it does not record live streams.

## Roadmap

- Chrome Web Store / Edge Add-ons listing (one-click extension install)
- Code-signed releases (no SmartScreen warning)
- In-app updates for the app and its yt-dlp engine
- Show real available qualities and file sizes in the video menu
- Browser-cookie support for videos that need a login

Ideas and bug reports are welcome in [Issues](https://github.com/samihaider77/free-to-download/issues).

## License

Free-to-Download is released under the [MIT License](LICENSE).
The Windows build bundles third-party software under its own licences, including FFmpeg (GPLv3), yt-dlp (Unlicense) and Python (PSF). See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
