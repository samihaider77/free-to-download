"""Let the browser extension start the app when it isn't running (Chrome native messaging).

The app registers itself as a native messaging host for Chrome, Edge and Brave every time it starts.
When the extension finds the app closed, the browser runs Free-to-Download.exe with the extension's
origin as its argument; in that mode it only starts the real app (minimized) and replies.
Only the extension IDs in version.EXTENSION_IDS may launch it.
"""
import json
from pathlib import Path
import socket
import struct
import subprocess
import sys

HOST_NAME = "com.free_to_download.launcher"
BROWSER_KEYS = (
    r"Software\Google\Chrome\NativeMessagingHosts",
    r"Software\Microsoft\Edge\NativeMessagingHosts",
    r"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
)


def is_host_launch(argv):
    """Browsers start a native host with the calling extension's origin as the first argument."""
    return len(argv) > 1 and argv[1].startswith("chrome-extension://")


def register(data, executable, extension_ids):
    """Write the host manifest and point each browser's per-user registry key at it. Best effort."""
    try:
        import winreg
        manifest = Path(data) / "native-host.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({
            "name": HOST_NAME,
            "description": "Starts Free-to-Download when the browser extension needs it",
            "path": str(Path(executable).resolve()),
            "type": "stdio",
            "allowed_origins": [f"chrome-extension://{extension_id}/" for extension_id in extension_ids],
        }, indent=2), encoding="utf-8")
        for parent in BROWSER_KEYS:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{parent}\{HOST_NAME}") as key:
                winreg.SetValue(key, "", winreg.REG_SZ, str(manifest.resolve()))
        register_link(executable)
        return True
    except (ImportError, OSError):
        return False


LINK_SCHEME = "free-to-download"


def register_link(executable):
    """Fallback launcher: a free-to-download:// link starts the app (the browser asks once, like Zoom links).
    The link's address is ignored, so a web page can only start the app, never pass it anything."""
    import winreg
    command = f'"{Path(executable).resolve()}" --minimized'
    base = rf"Software\Classes\{LINK_SCHEME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as key:
        winreg.SetValue(key, "", winreg.REG_SZ, "URL:Free-to-Download")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\shell\open\command") as key:
        winreg.SetValue(key, "", winreg.REG_SZ, command)


def app_running(port=17863):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def start_app(executable):
    """Start the app minimized, detached from the browser's process job so it outlives this helper."""
    detached, new_group, breakaway = 0x00000008, 0x00000200, 0x01000000
    command = [str(executable), "--minimized"]
    try:
        subprocess.Popen(command, creationflags=detached | new_group | breakaway, close_fds=True,
                         cwd=str(Path(executable).parent))
    except OSError:
        # Some job objects forbid breaking away; start normally instead.
        subprocess.Popen(command, creationflags=detached | new_group, close_fds=True, cwd=str(Path(executable).parent))


def serve(executable, port=17863):
    """Handle one native message: start the app if needed and reply with what happened."""
    source, sink = sys.stdin.buffer, sys.stdout.buffer
    header = source.read(4)
    if len(header) == 4:
        source.read(struct.unpack("<I", header)[0])  # the request content does not matter
    running = app_running(port)
    if not running:
        start_app(executable)
    reply = json.dumps({"started": not running, "running": running}).encode("utf-8")
    sink.write(struct.pack("<I", len(reply)) + reply)
    sink.flush()
