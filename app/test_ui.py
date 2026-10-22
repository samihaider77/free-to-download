"""End-to-end Tk queue test against a real local HTTP fixture."""
import tempfile
import time
import tkinter as tk
from pathlib import Path
from main import App
import test_downloader


def run():
    test_downloader.DownloadsTest.setUpClass()
    errors = []
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, Path(directory) / "data")
            app.register({"id": "a" * 32, "url": test_downloader.DownloadsTest.base + "/file", "destination": str(Path(directory) / "result.bin"), "connections": 8})
            app.tree.selection_set("a" * 32)
            deadline = time.monotonic() + 15

            def check():
                job = app.jobs["a" * 32]["job"]
                if job.status == "Complete":
                    try:
                        assert job.destination.read_bytes() == test_downloader.PAYLOAD
                        app.details()
                        assert app.progress["value"] == 100
                        assert "SHA-256" in app.detail.get()
                    except Exception as exc:
                        errors.append(exc)
                    app.close()
                elif job.status == "Error" or time.monotonic() > deadline:
                    errors.append(RuntimeError(job.error or "UI download timeout"))
                    app.close()
                else:
                    root.after(100, check)

            root.after(100, check)
            root.mainloop()
            assert (Path(directory) / "data" / "queue.json").exists()
            if errors:
                raise errors[0]
            print("PASS: GUI queue completed an 8-connection transfer, verified bytes, displayed progress and SHA-256, saved state, and closed.")
    finally:
        test_downloader.DownloadsTest.tearDownClass()


if __name__ == "__main__":
    run()
