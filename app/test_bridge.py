import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
import urllib.request

from bridge import Bridge
from state import InstanceLock


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.bridge = Bridge(self.path, port=0)
        self.base = f"http://127.0.0.1:{self.bridge.port}"

    def tearDown(self):
        self.bridge.close()
        self.directory.cleanup()

    def send(self, payload, token=None, origin=None):
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + (token if token is not None else self.bridge.token)}
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(self.base + "/downloads", data=json.dumps(payload).encode(), headers=headers)
        return urllib.request.urlopen(request, timeout=3)

    def test_authenticated_handoff(self):
        with self.send({"urls": ["https://example.com/file.zip"]}, origin="chrome-extension://" + "a" * 32) as response:
            self.assertEqual(response.status, 202)
        self.assertEqual(self.bridge.inbox.get_nowait()["urls"], ["https://example.com/file.zip"])

    def test_bad_token_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.send({"urls": ["https://example.com/file.zip"]}, token="incorrect")
        self.assertEqual(context.exception.code, 401)
        self.assertTrue(self.bridge.inbox.empty())

    def test_media_metadata_and_header_injection(self):
        with self.send({"urls": ["https://example.com/video.m3u8"], "media": True, "referer": "https://example.com/post", "title": "Team update"}) as response:
            self.assertEqual(response.status, 202)
        request = self.bridge.inbox.get_nowait()
        self.assertTrue(request["media"])
        self.assertEqual(request["title"], "Team update")
        self.assertEqual(request["quality"], "best")
        with self.send({"urls": ["https://example.com/watch"], "media": True, "quality": "720"}) as response:
            self.assertEqual(response.status, 202)
        self.assertEqual(self.bridge.inbox.get_nowait()["quality"], "720")
        with self.assertRaises(urllib.error.HTTPError):
            self.send({"urls": ["https://example.com/watch"], "media": True, "quality": "9999"})
        with self.assertRaises(urllib.error.HTTPError):
            self.send({"urls": ["https://example.com/video.m3u8"], "media": True, "title": "x" * 301})
        with self.assertRaises(urllib.error.HTTPError):
            self.send({"urls": ["https://example.com/video.m3u8"], "media": True, "referer": "https://example.com/\r\nX: bad"})

    def test_web_origin_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.send({"urls": ["https://example.com/file.zip"]}, origin="https://evil.example")
        self.assertEqual(context.exception.code, 403)

    def test_non_http_url_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.send({"urls": ["file:///C:/secret.txt"]})
        self.assertEqual(context.exception.code, 400)

    def test_queue_cannot_be_owned_twice(self):
        first = InstanceLock(self.path)
        try:
            with self.assertRaises(RuntimeError):
                InstanceLock(self.path)
        finally:
            first.close()
        second = InstanceLock(self.path)
        second.close()


if __name__ == "__main__":
    unittest.main()
