# Changelog

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
