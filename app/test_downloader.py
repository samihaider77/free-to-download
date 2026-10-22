from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib
import json
import re
import tempfile
import threading
import time
import unittest

from downloader import Download, filename_for

PAYLOAD = bytes(range(256)) * (32 * 1024)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    active = 0
    peak = 0
    lock = threading.Lock()
    requests_seen = []
    version = '"v1"'
    client_ports = []


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = b"" if self.path == "/empty" else PAYLOAD
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
        ranged = bool(match and self.path != "/single")
        start, end = (int(match[1]), int(match[2])) if ranged else (0, len(payload) - 1)
        etag = self.server.version
        if self.path == "/changed" and self.headers.get("If-Match"):
            self.send_response(412)
            self.end_headers()
            return
        if ranged and start >= len(payload):
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{len(payload)}")
            self.end_headers()
            return
        self.server.requests_seen.append((self.path, self.headers.get("Range"), self.headers.get("If-Match")))
        self.server.client_ports.append(self.client_address[1])
        body = payload[start:end + 1]
        self.send_response(206 if ranged else 200)
        self.send_header("Content-Length", str(len(body)))
        if self.path == "/webpage":
            self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.path == "/playlist":
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        if self.path != "/noetag":
            self.send_header("ETag", etag)
        if ranged:
            wrong = 1 if self.path == "/bad" and end > 0 else 0
            self.send_header("Content-Range", f"bytes {start + wrong}-{end}/{len(payload)}")
        self.end_headers()
        with self.server.lock:
            self.server.active += 1
            self.server.peak = max(self.server.peak, self.server.active)
        try:
            for pos in range(0, len(body), 16384):
                self.wfile.write(body[pos:pos + 16384])
                self.wfile.flush()
                time.sleep(0.001)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        finally:
            with self.server.lock:
                self.server.active -= 1


class DownloadsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def job(self, endpoint="/file", connections=8, name="out"):
        return Download(self.base + endpoint, self.root / name, self.root / (name + "-parts"), connections)

    def assert_content(self, job, expected=PAYLOAD):
        self.assertEqual(job.status, "Complete", job.error)
        self.assertEqual(job.destination.read_bytes(), expected)
        self.assertEqual(job.sha256, hashlib.sha256(expected).hexdigest())

    def test_parallel_integrity_and_real_concurrency(self):
        self.server.peak = 0
        job = self.job()
        job.run()
        self.assert_content(job)

    def test_webpage_and_playlist_never_publish(self):
        for endpoint in ("/webpage", "/playlist"):
            with self.subTest(endpoint=endpoint):
                job = self.job(endpoint, name=endpoint[1:])
                job.run()
                self.assertEqual(job.status, "Error")
                self.assertFalse(job.destination.exists())

    def test_parallel_worker_concurrency(self):
        self.server.peak = 0
        job = self.job()
        job.run()
        self.assert_content(job)
        self.assertGreaterEqual(self.server.peak, 2)

    def test_workers_reuse_http_connections_across_chunks(self):
        self.server.client_ports.clear()
        job = self.job(connections=4)
        job.run()
        self.assert_content(job)
        # One connection performs the initial probe. Four persistent workers
        # should serve many adaptive chunks without opening one socket per chunk.
        self.assertGreater(len(self.server.client_ports), 5)
        self.assertLessEqual(len(set(self.server.client_ports)), 5)

    def test_pause_and_resume_in_new_instance(self):
        job = self.job(connections=2)
        thread = threading.Thread(target=job.run)
        thread.start()
        deadline = time.monotonic() + 5
        while job.received < 256 * 1024 and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.005)
        job.pause()
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(job.status, "Paused", job.error)
        partial = sum(p.stat().st_size for p in job.workdir.glob("part-*"))
        self.assertGreater(partial, 0)
        self.assertFalse(job.destination.exists())
        self.server.requests_seen.clear()
        resumed = self.job(connections=2)
        resumed.run()
        self.assert_content(resumed)
        starts = [int(re.match(r"bytes=(\d+)", r[1])[1]) for r in self.server.requests_seen if r[2]]
        self.assertTrue(any(start not in (0, len(PAYLOAD) // 2) for start in starts))

    def test_server_ignoring_ranges(self):
        job = self.job("/single")
        job.run()
        self.assert_content(job)
        self.assertIn("Single connection", job.mode)

    def test_without_validator_falls_back(self):
        job = self.job("/noetag")
        job.run()
        self.assert_content(job)
        self.assertIn("Single connection", job.mode)

    def test_invalid_range_never_publishes(self):
        job = self.job("/bad")
        job.run()
        self.assertEqual(job.status, "Error")
        self.assertFalse(job.destination.exists())

    def test_changed_resource_never_publishes(self):
        job = self.job("/changed")
        job.run()
        self.assertEqual(job.status, "Error")
        self.assertFalse(job.destination.exists())

    def test_existing_destination_preserved(self):
        job = self.job()
        job.destination.write_bytes(b"keep me")
        job.run()
        self.assertEqual(job.status, "Error")
        self.assertEqual(job.destination.read_bytes(), b"keep me")

    def test_expected_sha256_accepts_matching_file(self):
        expected = hashlib.sha256(PAYLOAD).hexdigest()
        job = Download(self.base + "/file", self.root / "verified", self.root / "verified-parts", 4,
                       expected_sha256=expected)
        job.run()
        self.assert_content(job)

    def test_expected_sha256_rejects_mismatch_without_publishing(self):
        job = Download(self.base + "/file", self.root / "rejected", self.root / "rejected-parts", 4,
                       expected_sha256="0" * 64)
        job.run()
        self.assertEqual(job.status, "Error")
        self.assertIn("SHA-256 verification failed", job.error)
        self.assertFalse(job.destination.exists())
        self.assertFalse(list(self.root.glob(".free-to-download-*.assembling")))

    def test_empty_download(self):
        job = self.job("/empty")
        job.run()
        self.assert_content(job, b"")

    def test_safe_filename(self):
        self.assertEqual(filename_for("https://example.test/%2E%2E%2FCON.exe"), "_CON.exe")
        self.assertEqual(filename_for("https://example.test/NUL"), "_NUL")


def benchmark(output):
    DownloadsTest.setUpClass()
    try:
        result = {"fixture": "8 MiB local HTTP server, 16 KiB writes delayed 1 ms each; artificial per-connection throttling", "results": []}
        with tempfile.TemporaryDirectory() as directory:
            for connections in (1, 8):
                job = Download(DownloadsTest.base + "/file", Path(directory) / f"out{connections}", Path(directory) / f"parts{connections}", connections)
                job.run()
                if job.status != "Complete" or job.destination.read_bytes() != PAYLOAD:
                    raise RuntimeError(job.error or "Content mismatch")
                result["results"].append({"connections": connections, "seconds": round(job.elapsed, 3), "MiB_per_second": round(8 / job.elapsed, 2), "sha256": job.sha256})
        result["caveat"] = "Demonstrates concurrency under an artificial server bottleneck. Not a real Internet speed claim."
        Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    finally:
        DownloadsTest.tearDownClass()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--benchmark":
        benchmark(sys.argv[2])
    else:
        unittest.main()
