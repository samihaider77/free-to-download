"""Segmented, resumable HTTP downloader built on the Python standard library."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import json
import hashlib
import http.client
import math
import os
import queue
import re
import ssl
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from version import NAME, VERSION

USER_AGENT = f"{NAME}/{VERSION}"


class Paused(Exception):
    pass


class DownloadError(Exception):
    pass


class RateLimiter:
    """A single adjustable bandwidth budget shared by all download workers."""
    def __init__(self, bytes_per_second=0):
        self.lock = threading.Lock()
        self.rate = max(0, bytes_per_second)
        self.next_slot = 0

    def set_rate(self, value):
        with self.lock:
            self.rate = max(0, value)
            self.next_slot = time.monotonic()

    def acquire(self, amount, stop):
        with self.lock:
            if not self.rate:
                return
            now = time.monotonic()
            start = max(now, self.next_slot)
            self.next_slot = start + amount / self.rate
            delay = self.next_slot - now
        if stop.wait(delay):
            raise Paused()


class Connection:
    """One persistent HTTP connection, owned by one worker thread."""
    def __init__(self, url, timeout):
        self.url = urllib.parse.urlsplit(url)
        self.timeout = timeout
        self.connection = None

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def request(self, headers):
        if self.connection is None:
            kind = http.client.HTTPSConnection if self.url.scheme == "https" else http.client.HTTPConnection
            options = {"timeout": self.timeout}
            if self.url.scheme == "https":
                options["context"] = ssl.create_default_context()
            self.connection = kind(self.url.hostname, self.url.port, **options)
        path = urllib.parse.urlunsplit(("", "", self.url.path or "/", self.url.query, ""))
        self.connection.request("GET", path, headers=headers)
        response = self.connection.getresponse()
        if response.status >= 400:
            error = urllib.error.HTTPError(self.url.geturl(), response.status, response.reason, response.headers, None)
            response.close()
            self.close()
            raise error
        return response


def validate_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Enter a complete http:// or https:// download URL.")
    if parsed.username or parsed.password:
        raise ValueError("URLs with embedded credentials are not supported.")
    return url


def filename_for(url):
    return safe_filename(urllib.parse.unquote(urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1])) or "download.bin"


def safe_filename(name):
    """Windows-safe file name, or "" when nothing usable remains."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")[:160].strip(" .")
    if not name:
        return ""
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        name = "_" + name
    return name


def atomic_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(temp, path)


@dataclass
class Probe:
    total: int | None
    etag: str | None
    ranged: bool


class Download:
    def __init__(self, url, destination, workdir, connections=8, limiter=None, expected_sha256="", timeout=15):
        self.url = validate_url(url)
        self.destination = Path(destination)
        self.workdir = Path(workdir)
        self.connections = max(1, min(16, int(connections)))
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.received = 0
        self.transferred = 0
        self.total = None
        self.active_connections = 0
        self.status = "Queued"
        self.error = ""
        self.mode = "Checking server"
        self.elapsed = 0.0
        self.sha256 = ""
        self.expected_sha256 = expected_sha256.lower().strip()
        if self.expected_sha256 and not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256):
            raise ValueError("Expected SHA-256 must contain exactly 64 hexadecimal characters.")
        self.limiter = limiter or RateLimiter()
        self.timeout = timeout
        self.effective_url = self.url
        self.segment_progress = {}
        self.retries = 0

    def pause(self):
        self.stop.set()

    def check(self):
        if self.stop.is_set():
            raise Paused()

    def request(self, headers=None):
        self.check()
        req = urllib.request.Request(self.url, headers={
            "User-Agent": USER_AGENT, "Accept-Encoding": "identity", **(headers or {})})
        return urllib.request.urlopen(req, timeout=self.timeout)

    def probe(self):
        try:
            with self.request({"Range": "bytes=0-0"}) as response:
                self.effective_url = validate_url(response.geturl())
                self.validate_content(response)
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise DownloadError("Server ignored identity encoding; cannot safely split this response.")
                etag = response.headers.get("ETag")
                strong = etag if etag and etag.startswith('"') and etag.endswith('"') else None
                if response.status == 206:
                    match = re.fullmatch(r"bytes 0-0/(\d+)", response.headers.get("Content-Range", ""))
                    if not match or int(match[1]) < 1 or len(response.read(2)) != 1:
                        raise DownloadError("Invalid byte-range probe from server.")
                    return Probe(int(match[1]), strong, bool(strong))
                if response.status != 200:
                    raise DownloadError(f"Unexpected HTTP status {response.status}.")
                length = response.headers.get("Content-Length")
                return Probe(int(length) if length is not None else None, strong, False)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and exc.headers.get("Content-Range") == "bytes */0":
                return Probe(0, None, False)
            if exc.code not in (400, 405, 416, 501):
                raise
            # Some servers reject Range entirely; try a normal GET in single mode.
            return Probe(None, None, False)

    def add_bytes(self, count, network=True):
        with self.lock:
            self.received += count
            if network:
                self.transferred += count

    def part(self, index, start, end, etag, connection):
        path = self.workdir / f"part-{index}"
        expected = end - start + 1
        existing = path.stat().st_size if path.exists() else 0
        if existing > expected:
            raise DownloadError("Partial file is larger than its expected range.")
        self.add_bytes(existing, network=False)
        self.segment_progress[index] = (existing, expected)
        for attempt in range(5):
            self.check()
            existing = path.stat().st_size if path.exists() else 0
            if existing == expected:
                return
            offset = start + existing
            try:
                with connection.request({"Range": f"bytes={offset}-{end}", "If-Match": etag,
                                         "Accept-Encoding": "identity", "User-Agent": USER_AGENT}) as response:
                    wanted = f"bytes {offset}-{end}/{self.total}"
                    if (response.status != 206 or response.headers.get("Content-Range") != wanted
                            or response.headers.get("ETag") != etag
                            or response.headers.get("Content-Encoding", "identity").lower() != "identity"):
                        raise DownloadError("Server changed the file or returned an invalid range. Start a new download.")
                    remaining = end - offset + 1
                    with self.lock:
                        self.active_connections += 1
                    try:
                        with path.open("ab") as output:
                            while remaining:
                                self.check()
                                chunk = response.read(min(64 * 1024, remaining))
                                if not chunk:
                                    raise OSError("Connection ended before the range was complete.")
                                output.write(chunk)
                                output.flush()
                                remaining -= len(chunk)
                                self.add_bytes(len(chunk))
                                self.segment_progress[index] = (expected - remaining, expected)
                                self.limiter.acquire(len(chunk), self.stop)
                            if response.read(1):
                                raise DownloadError("Server sent more bytes than requested.")
                    finally:
                        with self.lock:
                            self.active_connections -= 1
                return
            except urllib.error.HTTPError as exc:
                if exc.code < 500 and exc.code != 429:
                    raise DownloadError(f"HTTP {exc.code}; download stopped without combining mismatched data.") from exc
                if attempt == 4:
                    raise
            except (OSError, urllib.error.URLError, http.client.HTTPException):
                if attempt == 4:
                    raise
            connection.close()
            self.retries += 1
            if self.stop.wait(0.5 * (attempt + 1)):
                raise Paused()

    def validate_content(self, response):
        media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if media_type in ("text/html", "application/xhtml+xml"):
            raise DownloadError("This link returns a webpage, not a downloadable video or file. Use a direct file URL; copying the player page address will not download its video.")
        if media_type in ("application/vnd.apple.mpegurl", "application/x-mpegurl", "audio/mpegurl", "application/dash+xml"):
            raise DownloadError("This link is a streaming playlist. HLS/DASH downloads are not supported by this version.")

    def single(self, etag):
        self.mode = "Single connection · server cannot safely resume"
        self.received = 0
        headers = {"If-Match": etag} if etag else {}
        with self.request(headers) as response:
            self.validate_content(response)
            if response.status != 200:
                raise DownloadError(f"Expected a full response; got HTTP {response.status}.")
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise DownloadError("Unexpected content encoding.")
            if etag and response.headers.get("ETag") != etag:
                raise DownloadError("File changed before the download started.")
            size = response.headers.get("Content-Length")
            self.total = int(size) if size is not None else None
            self.active_connections = 1
            try:
                with (self.workdir / "single").open("wb") as output:
                    while True:
                        self.check()
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        self.add_bytes(len(chunk))
                        self.limiter.acquire(len(chunk), self.stop)
                        if self.total is not None and self.received > self.total:
                            raise DownloadError("Response exceeded its declared size.")
                if self.total is not None and self.received != self.total:
                    raise DownloadError("Connection ended before the file was complete; retry to restart.")
                self.total = self.received
            finally:
                self.active_connections = 0
        return [self.workdir / "single"]

    def publish(self, parts):
        self.status = "Finishing"
        self.destination.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        # Assemble beside the destination, then publish with an atomic no-clobber
        # operation. A crash cannot leave a half-written final filename.
        fd, temporary = tempfile.mkstemp(prefix=".free-to-download-", suffix=".assembling", dir=self.destination.parent)
        temporary = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as output:
                for path in parts:
                    with path.open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            self.check()
                            output.write(chunk)
                            digest.update(chunk)
                output.flush()
                os.fsync(output.fileno())
            result = digest.hexdigest()
            if self.expected_sha256 and result != self.expected_sha256:
                raise DownloadError("SHA-256 verification failed. The destination was not published.")
            self.check()
            if os.name == "nt":
                os.rename(temporary, self.destination)  # Windows refuses existing destinations.
            else:
                os.link(temporary, self.destination)
                temporary.unlink()
            self.sha256 = result
        finally:
            temporary.unlink(missing_ok=True)

    def run(self):
        started = time.monotonic()
        self.status = "Connecting"
        self.error = ""
        try:
            self.check()
            if self.destination.exists():
                raise DownloadError("Destination already exists. Choose a different filename.")
            self.workdir.mkdir(parents=True, exist_ok=True)
            probe = self.probe()
            self.total = probe.total
            self.status = "Downloading"
            if probe.ranged:
                manifest_path = self.workdir / "manifest.json"
                previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
                identity = {"url": self.url, "total": probe.total, "etag": probe.etag}
                if previous and all(previous.get(k) == v for k, v in identity.items()):
                    count = int(previous["count"])
                    if not 1 <= count <= 4096:
                        raise DownloadError("Invalid saved chunk count.")
                else:
                    chunk_size = max(256 * 1024, min(8 * 1024 * 1024, math.ceil(probe.total / (self.connections * 8))))
                    count = min(4096, max(1, math.ceil(probe.total / chunk_size)))
                    for path in self.workdir.glob("part-*"):
                        path.unlink()
                    atomic_json(manifest_path, {**identity, "count": count, "version": 2})
                self.received = 0
                self.segment_progress = {}
                workers = min(self.connections, count)
                self.mode = f"{workers} connections · {count} adaptive chunks · resumable"
                pending = queue.Queue()
                for index in range(count):
                    pending.put(index)

                def worker():
                    connection = Connection(self.effective_url, self.timeout)
                    try:
                        while True:
                            self.check()
                            try:
                                i = pending.get_nowait()
                            except queue.Empty:
                                return
                            self.part(i, probe.total * i // count, probe.total * (i + 1) // count - 1, probe.etag, connection)
                    except Exception:
                        self.stop.set()
                        raise
                    finally:
                        connection.close()

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = [pool.submit(worker) for _ in range(workers)]
                    failure = None
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            if failure is None or isinstance(failure, Paused):
                                failure = exc
                            self.stop.set()
                    if failure:
                        raise failure
                parts = [self.workdir / f"part-{i}" for i in range(count)]
            else:
                parts = self.single(probe.etag)
            self.check()
            self.publish(parts)
            self.status = "Complete"
            for path in self.workdir.iterdir():
                if path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        pass  # Cleanup cannot turn a successfully published download into a failure.
        except Paused:
            self.status = "Paused"
        except Exception as exc:
            self.status = "Error"
            self.error = str(exc)
        finally:
            self.elapsed = time.monotonic() - started
        return self.status
