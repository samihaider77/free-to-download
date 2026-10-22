"""Native messaging launcher: protocol, start-only-when-closed, and browser argument detection."""
import io
import json
import struct
import sys
import unittest
from unittest import mock

import native_host


def message(payload):
    body = json.dumps(payload).encode()
    return struct.pack("<I", len(body)) + body


class NativeHostTest(unittest.TestCase):
    def run_host(self, running):
        stdin, stdout = io.TextIOWrapper(io.BytesIO(message({"action": "start"}))), io.TextIOWrapper(io.BytesIO())
        with mock.patch.object(sys, "stdin", stdin), mock.patch.object(sys, "stdout", stdout), \
                mock.patch.object(native_host, "app_running", return_value=running), \
                mock.patch.object(native_host, "start_app") as start:
            native_host.serve("C:/Apps/Free-to-Download.exe")
        raw = stdout.buffer.getvalue()
        length = struct.unpack("<I", raw[:4])[0]
        return json.loads(raw[4:4 + length]), start

    def test_starts_the_app_when_closed(self):
        reply, start = self.run_host(running=False)
        self.assertEqual(reply, {"started": True, "running": False})
        start.assert_called_once_with("C:/Apps/Free-to-Download.exe")

    def test_does_nothing_when_already_running(self):
        reply, start = self.run_host(running=True)
        self.assertEqual(reply, {"started": False, "running": True})
        start.assert_not_called()

    def test_recognises_browser_launch_arguments(self):
        self.assertTrue(native_host.is_host_launch(["app.exe", "chrome-extension://peokmobebldmdpbnlnbgolckefjcndkf/", "--parent-window=0"]))
        self.assertFalse(native_host.is_host_launch(["app.exe"]))
        self.assertFalse(native_host.is_host_launch(["app.exe", "--minimized"]))


if __name__ == "__main__":
    unittest.main()
