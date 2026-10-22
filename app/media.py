"""Media extraction and unprotected HLS/DASH downloads using yt-dlp."""
from pathlib import Path
import re
import subprocess
import time
import sys
from downloader import Download, DownloadError, Paused, safe_filename


MEDIA_SUFFIXES = (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".ogg", ".ts")
QUALITIES = ("best", "2160", "1440", "1080", "720", "480", "360", "audio")


def format_for(quality):
    """yt-dlp format rule: the chosen height or the closest one below it; audio only; or the best there is."""
    if quality == "audio":
        return "ba/b"
    if quality.isdigit():
        return f"bv*[height<={quality}]+ba/b[height<={quality}]/bv*+ba/b"
    return "bv*+ba/b"


class AlreadyDownloaded(Exception):
    """The same video (same site title) is already saved; nothing is overwritten."""
    def __init__(self, path):
        super().__init__(str(path))
        self.path = path


def existing_copy(path, suffixes=MEDIA_SUFFIXES):
    return next((candidate for candidate in map(path.with_suffix, suffixes) if candidate.exists()), None)


def unused_path(path):
    """First "name (n)" that is free in every container the merged video may end up in."""
    number, candidate = 1, path
    while existing_copy(candidate):
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        number += 1
    return candidate


STREAM_EXTENSIONS = {"mp4", "m4v", "m4a", "webm", "weba", "mkv", "mov", "ts", "mp3", "aac", "ogg", "opus", "flv"}


def normalize_extensions(info):
    """Sites such as LinkedIn label DASH pieces video/iso.segment; yt-dlp turns that into an
    "iso.segment" file extension and refuses it. They are ordinary fMP4, so call them mp4/m4a."""
    for entry in [info, *(info.get("formats") or [])]:
        ext = entry.get("ext")
        streamed = "fragments" in entry or str(entry.get("protocol", "")).startswith(("http_dash", "m3u8"))
        if ext and ext not in STREAM_EXTENSIONS and streamed:
            entry["ext"] = "m4a" if entry.get("vcodec") == "none" else "mp4"


def has_media(ffmpeg, path):
    """True when the file holds audio or video samples, not just a stream header such as an fMP4 init segment."""
    result = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-t", "5", "-i", str(path), "-map", "0", "-c", "copy", "-f", "null", "-"],
                            capture_output=True, text=True, errors="replace", timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    sizes = re.search(r"video:(\d+)\S* audio:(\d+)", result.stderr)
    return bool(sizes) and int(sizes[1]) + int(sizes[2]) > 0


def release_partial_files(exc):
    """yt-dlp leaves its .part stream open when a hook aborts; close it so Windows can resume or delete it."""
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        tb = exc.__traceback__
        while tb:
            ctx = tb.tb_frame.f_locals.get("ctx")
            # HttpFD keeps ctx.stream; fragment (HLS/DASH) downloaders keep ctx["dest_stream"].
            for stream in (getattr(ctx, "stream", None), ctx.get("dest_stream") if isinstance(ctx, dict) else None):
                if stream is not None and getattr(stream, "name", "") not in ("-", "<stdout>"):
                    stream.close()
            tb = tb.tb_next
        exc = exc.__cause__ or exc.__context__


class MediaDownload(Download):
    def __init__(self, *args, referer="", quality="best", **kwargs):
        super().__init__(*args, **kwargs)
        self.referer = referer
        self.quality = quality if quality in QUALITIES else "best"
        self.already_exists = False
        self.fragment_index = self.fragment_count = 0
        self.reported_speed = 0

    def run(self):
        started = time.monotonic()
        self.status, self.error, self.already_exists = "Connecting", "", False
        self.fragment_index = self.fragment_count = self.reported_speed = 0
        try:
            import yt_dlp
            import imageio_ffmpeg
            self.check()
            self.workdir.mkdir(parents=True, exist_ok=True)
            self.mode = "Finding video and audio"
            def progress(info):
                self.check()
                self.status = "Downloading"
                self.mode = "Downloading media fragments · resumable"
                downloaded = info.get("downloaded_bytes", 0)
                self.transferred += max(0, downloaded - self.received)
                self.received = downloaded
                self.total = info.get("total_bytes") or info.get("total_bytes_estimate")
                self.fragment_index, self.fragment_count = info.get("fragment_index") or 0, info.get("fragment_count") or 0
                self.reported_speed = info.get("speed") or 0
            def processing(info):
                self.check()
                self.status = "Finishing"
                self.mode = "Converting to MP3" if self.quality == "audio" else "Combining video and audio"
            class Logger:
                def debug(self, msg): pass
                def warning(self, msg): pass
                def error(self, msg): pass
            audio_only = self.quality == "audio"
            # Only a copy of the same kind counts as "already downloaded": a saved video doesn't block its MP3.
            same_kind = (".mp3", ".m4a", ".ogg") if audio_only else (".mp4", ".mkv", ".webm", ".mov", ".ts")
            bundled = Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg.exe"
            ffmpeg = str(bundled) if bundled.is_file() else imageio_ffmpeg.get_ffmpeg_exe()
            options = {
                # Highest resolution first, then the codecs every Windows player opens (H.264 + AAC in MP4).
                "format": format_for(self.quality), "format_sort": ["res", "vcodec:h264", "acodec:aac"],
                "merge_output_format": "mp4/mkv",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
                                  if audio_only else [],
                "outtmpl": str(self.workdir / "media.%(ext)s"),
                "ffmpeg_location": ffmpeg, "noplaylist": True,
                "concurrent_fragment_downloads": self.connections,
                "continuedl": True, "retries": 5, "fragment_retries": 5,
                "skip_unavailable_fragments": False,
                "socket_timeout": self.timeout, "quiet": True, "no_warnings": True,
                "progress_hooks": [progress], "postprocessor_hooks": [processing],
                "logger": Logger(), "allow_unplayable_formats": False,
                "http_headers": {"Referer": self.referer} if self.referer else {},
                "ratelimit": self.limiter.rate or None,
            }
            with yt_dlp.YoutubeDL(options) as engine:
                info = engine.extract_info(self.url, download=False)
                self.check()
                if not info or info.get("_type") in ("playlist", "multi_video"):
                    raise DownloadError("Select one detected video, not a playlist of posts.")
                if info.get("is_live"):
                    raise DownloadError("Live recording is not supported; choose a finished video.")
                if info.get("has_drm"):
                    raise DownloadError("This video is DRM protected and cannot be downloaded.")
                # A site extractor (YouTube, LinkedIn…) knows the real title; the generic one only
                # sees a stream URL, so keep the page title the browser sent in that case.
                title = safe_filename(info.get("title") or "")[:120].rstrip(" .")
                titled = bool(title) and info.get("extractor_key") not in (None, "Generic")
                if titled:
                    # A chosen resolution is part of the name, so a 720p copy never clashes with a full-quality one.
                    label = f" ({self.quality}p)" if self.quality.isdigit() else ""
                    self.destination = self.destination.with_name(title + label + self.destination.suffix)
                    if existing_copy(self.destination, same_kind):
                        raise AlreadyDownloaded(existing_copy(self.destination, same_kind))
                normalize_extensions(info)
                engine.process_ie_result(info, download=True)
            self.check()
            candidates = [p for p in self.workdir.glob("media.*")
                          if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".ogg", ".ts")
                          and '.f' not in p.stem]
            if len(candidates) != 1 or not candidates[0].stat().st_size:
                raise DownloadError("Media conversion did not produce one complete playable file.")
            result = candidates[0]
            self.mode = "Checking the video"
            if not has_media(ffmpeg, result):
                raise DownloadError("That item was only a piece of a stream (a header or fragment), not the whole video. "
                                    "Pick the entry marked \"Full video\" in the video menu.")
            target = self.destination.with_suffix(result.suffix)
            if existing_copy(target):
                # Same real title: another job finished this video first. Generic name: a different video.
                if titled and existing_copy(target, same_kind):
                    raise AlreadyDownloaded(existing_copy(target, same_kind))
                target = unused_path(target)
            self.destination = target
            try:
                self.publish([result])
            except FileExistsError:
                raise AlreadyDownloaded(self.destination)
            self.received = self.total = self.destination.stat().st_size
            self.status = "Complete"
        except AlreadyDownloaded as exc:
            self.destination, self.already_exists = exc.path, True
            self.received = self.total = exc.path.stat().st_size
            self.status, self.mode = "Complete", "Already downloaded"
        except Exception as exc:
            if self.stop.is_set() or isinstance(exc, Paused):
                self.status = "Paused"
                release_partial_files(exc)
            else:
                self.status, self.error = "Error", re.sub(r"^(ERROR:\s*)+", "", str(exc))
        finally:
            self.elapsed = time.monotonic() - started
        return self.status
