# Changelog

## 0.6.5

- Video menu: when a video's ID can't be matched to a stream (for example a LinkedIn post with a custom cover image),
  streams that arrived within a few seconds of that video starting are used — only when no other video started at the
  same time, so it never guesses between videos.
- **Copy diagnostic info** now appears whenever a video can't be matched, and includes stream timing.

## 0.6.4

- **LinkedIn feed: streams are matched to the exact video.** LinkedIn's video ID appears in both the video's cover image
  and its stream addresses, so the menu now offers only that video's streams (with the quality choices), even when the
  post itself can't be identified. If the video's own stream hasn't loaded yet, it asks you to play it instead of
  offering another video.
- **Copy diagnostic info** button when a video can't be identified, for bug reports.

## 0.6.3

- **LinkedIn: fixed downloading a different post's video from the feed.** The button now identifies the post that holds
  the video without looking into neighbouring posts, using the post's ID or its own permalink.
- If a post can't be identified, the menu says so and lists streams that loaded after this video started first.

## 0.6.2

- When the app is closed, the extension now waits up to a minute for it to start (the first start after installing or
  updating can be slow while Windows scans the new files) and shows **“Starting Free-to-Download…”** meanwhile.
- Clear, specific messages if the app can't be started, instead of a generic “not running”.
- A failed attempt no longer removes that quality from the video menu; you can retry straight away.

## 0.6.1

- **The browser starts the app for you.** If Free-to-Download is closed when you click a download, the extension asks
  the browser to launch it (minimized) through a registered native messaging launcher, waits for it, and sends the
  download — no more “Failed to fetch”. Works in Chrome, Edge and Brave; registered by the installer and refreshed on
  every app start, removed on uninstall.
- Clearer messages when the app can't be reached.

## 0.6.0

- **No more pairing token.** The browser extension now connects to the app automatically: it has a fixed ID, and the
  app hands its token only to requests the browser stamps with that ID. Reinstalling the app reconnects by itself.
- The extension's Settings page shows the connection status; manual token entry moved under *Advanced*.
- Installer: optional **Start when I sign in to Windows (minimized)**, and a final step that opens Chrome's extensions
  page and the extension folder.
- Opening the app while it already runs brings the existing window forward.
- Ready for the Chrome Web Store / Edge Add-ons: once a store ID is configured, the installer registers the extension so
  the browser offers to enable it. Store upload package and privacy policy included.

## 0.5.2 — first public release

### Video downloads
- **Download this video** button over web videos with a quality menu: Best, 1080p, 720p, 480p, 360p and Audio only (MP3).
- Page-link downloads for YouTube, LinkedIn posts, Vimeo, X and other sites supported by yt-dlp.
- HLS and DASH streams detected while a video plays, including from the browser cache.
- Videos are saved as H.264 + AAC MP4 when available, and named after the real video title.
- Already-downloaded videos are recognised instead of downloaded again; existing files are never overwritten.
- Stream headers and fragments are no longer offered as whole videos, and results with no audio or video data are rejected.

### Desktop app
- Progress window for each download: speed, time left, resume capability, per-connection or per-fragment progress.
- “Download complete” dialog with *Open* and *Open folder*.
- Visible activity (moving bar, running timer) while a video is being located or merged.
- Main-window controls stay visible on smaller screens.

### Downloads, queue and browser
- Multi-connection, resumable direct-file downloads with adaptive chunk scheduling.
- Queue with simultaneous-download limit, speed limiter, scheduling, batch import, categories, search and SHA-256 checks.
- Authenticated local bridge between the browser extension and the app.
