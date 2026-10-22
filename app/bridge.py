"""Authenticated loopback handoff from the Free-to-Download browser extension."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import queue
import re
import secrets
import threading

from downloader import atomic_json, validate_url
from version import EXTENSION_IDS, NAME, VERSION
from media import QUALITIES


class Bridge:
    def __init__(self, data, port=17863, extension_ids=EXTENSION_IDS):
        # Browsers stamp every extension request with Origin: chrome-extension://<id>; web pages and other
        # extensions cannot forge it, so our own extension may fetch the token without a manual paste.
        self.trusted_origins = {f"chrome-extension://{extension_id}" for extension_id in extension_ids}
        path = Path(data) / "browser.json"
        if path.exists():
            self.token = json.loads(path.read_text(encoding="utf-8"))["token"]
        else:
            self.token = secrets.token_urlsafe(32)
            atomic_json(path, {"token": self.token})
        self.inbox = queue.Queue(maxsize=100)
        self.show_requested = False
        self.server = None
        self.thread = None
        self.error = ""
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def origin_allowed(self):
                origin = self.headers.get("Origin", "")
                return not origin or bool(re.fullmatch(r"chrome-extension://[a-p]{32}", origin))

            def reply(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                if self.origin_allowed() and self.headers.get("Origin"):
                    self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
                    self.send_header("Vary", "Origin")
                self.end_headers()
                self.wfile.write(body)

            def allowed(self):
                if self.headers.get("Host") != f"127.0.0.1:{bridge.port}" or not self.origin_allowed():
                    self.reply(403, {"error": "Origin or host not allowed"})
                    return False
                supplied = self.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode("utf-8"), ("Bearer " + bridge.token).encode("utf-8")):
                    self.reply(401, {"error": "Pair this extension with the desktop app first"})
                    return False
                return True

            def do_OPTIONS(self):
                if not self.origin_allowed() or self.headers.get("Host") != f"127.0.0.1:{bridge.port}":
                    self.reply(403, {"error": "Origin not allowed"})
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "null"))
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.end_headers()

            def do_GET(self):
                if self.allowed():
                    self.reply(200 if self.path == "/health" else 404,
                               {"app": NAME, "version": VERSION} if self.path == "/health" else {"error": "Unknown endpoint"})

            def do_POST(self):
                self.connection.settimeout(3)
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        raise ValueError()
                    body = self.rfile.read(length)
                except (ValueError, OSError):
                    self.reply(400, {"error": "Expected a request of at most 64 KiB"})
                    return
                if self.path == "/pair":
                    if (self.headers.get("Host") != f"127.0.0.1:{bridge.port}"
                            or self.headers.get("Origin", "") not in bridge.trusted_origins):
                        self.reply(403, {"error": "Only the Free-to-Download extension can pair automatically"})
                    else:
                        self.reply(200, {"token": bridge.token, "app": NAME, "version": VERSION})
                    return
                if not self.allowed():
                    return
                if self.path == "/show":
                    bridge.show_requested = True  # a second launch asks this window to come forward
                    self.reply(200, {"shown": True})
                    return
                if self.path != "/downloads":
                    self.reply(404, {"error": "Unknown endpoint"})
                    return
                try:
                    if self.headers.get("Content-Type") != "application/json":
                        raise ValueError("Expected a JSON request of at most 64 KiB")
                    payload = json.loads(body)
                    urls = payload.get("urls")
                    if not isinstance(urls, list) or not 1 <= len(urls) <= 50:
                        raise ValueError("Send between 1 and 50 URLs")
                    for url in urls:
                        if not isinstance(url, str) or len(url) > 8192:
                            raise ValueError("Invalid URL")
                        validate_url(url)
                    media = payload.get("media", False)
                    referer = payload.get("referer", "")
                    if not isinstance(media, bool) or not isinstance(referer, str) or len(referer) > 8192 or '\r' in referer or '\n' in referer:
                        raise ValueError("Invalid media metadata")
                    if referer:
                        validate_url(referer)
                    title = payload.get("title", "")
                    quality = payload.get("quality", "best")
                    if not isinstance(title, str) or len(title) > 300 or quality not in QUALITIES:
                        raise ValueError("Invalid media metadata")
                    request = {"urls": list(dict.fromkeys(urls))}
                    if media:
                        request.update(media=True, referer=referer, title=title, quality=quality)
                    bridge.inbox.put_nowait(request)
                    self.reply(202, {"accepted": len(set(urls))})
                except queue.Full:
                    self.reply(429, {"error": "Desktop handoff queue is full"})
                except (ValueError, TypeError, AttributeError, TimeoutError):
                    self.reply(400, {"error": "Invalid download request"})

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            self.port = self.server.server_port
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except OSError as exc:
            self.error = str(exc)
            self.port = port

    def close(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

