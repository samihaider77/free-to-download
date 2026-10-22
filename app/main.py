"""Free-to-Download desktop UI, using Python's bundled Tk toolkit."""
from pathlib import Path
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from datetime import datetime
import uuid
import queue

from version import EXTENSION_IDS, NAME, VERSION
import native_host
from downloader import Download, RateLimiter, atomic_json, filename_for, safe_filename, validate_url
from media import MediaDownload
from progress_window import DownloadWindow, draw_cells, draw_segments
from bridge import Bridge
from state import InstanceLock

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def browser_path(executable="chrome.exe"):
    """Installed browser executable from Windows' App Paths registry, or None."""
    try:
        import winreg
    except ImportError:
        return None
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{executable}") as key:
                path = winreg.QueryValue(key, None)
            if path and Path(path).is_file():
                return path
        except OSError:
            continue
    return None


def show_running_instance():
    """Ask an already-running app (same data folder) to show its window. True if it answered."""
    import urllib.request
    try:
        token = json.loads((ROOT / "data" / "browser.json").read_text(encoding="utf-8"))["token"]
        request = urllib.request.Request("http://127.0.0.1:17863/show", data=b"{}",
                                         headers={"Content-Type": "application/json", "Authorization": "Bearer " + token})
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status == 200
    except (OSError, ValueError, KeyError):
        return False


def category_for(name):
    extension = Path(name).suffix.lower()
    for category, extensions in {
        "Archives": {".zip", ".rar", ".7z", ".gz", ".tar", ".bz2", ".xz"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".csv", ".pptx", ".epub"},
        "Music": {".mp3", ".flac", ".wav", ".aac", ".ogg", ".m4a"},
        "Video": {".mp4", ".mkv", ".webm", ".mov", ".avi"},
        "Programs": {".exe", ".msi", ".msix", ".dmg", ".deb", ".apk"},
    }.items():
        if extension in extensions:
            return category
    return "Other"


def size(value):
    if value is None:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024


class App:
    def __init__(self, root, data=None):
        self.root = root
        self.data = Path(data) if data else ROOT / "data"
        self.data.mkdir(parents=True, exist_ok=True)
        self.instance = InstanceLock(self.data)
        self.jobs = {}
        self.closing = False
        self.settings = {"folder": str(Path.home() / "Downloads" / "Free-to-Download"), "connections": 8,
                         "parallel": 2, "limit_kib": 0, "categories": True, "notify": True, "timeout": 15,
                         "progress_window": True, "complete_dialog": True}
        settings_path = self.data / "settings.json"
        if settings_path.exists():
            try:
                saved = json.loads(settings_path.read_text(encoding="utf-8"))
                self.settings.update({key: value for key, value in saved.items() if key in self.settings})
            except (OSError, ValueError, AttributeError):
                pass
        self.limiter = RateLimiter(max(0, int(self.settings["limit_kib"])) * 1024)
        self.bridge = Bridge(self.data) if data is None else None
        self.history = []
        self.windows = {}
        root.title("Free-to-Download — Download Manager")
        # Packaged builds carry the icon beside the code; source runs read it from packaging/.
        icon = Path(getattr(sys, "_MEIPASS", ROOT / "packaging")) / "icon.ico"
        if icon.is_file():
            root.iconbitmap(default=str(icon))  # default= also applies to every progress window
        root.geometry("1240x800")
        root.minsize(1080, 720)
        root.configure(bg="#101827")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#ffffff", foreground="#243047", fieldbackground="#ffffff", rowheight=38, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background="#eaf0f6", foreground="#475569", font=("Segoe UI", 10, "bold"), padding=10)
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#172554")])
        style.configure("TButton", padding=(14, 9), font=("Segoe UI", 10))
        style.configure("TEntry", padding=8)
        style.configure("TProgressbar", background="#0d9488", troughcolor="#e2e8f0")
        style.configure("Download.Horizontal.TProgressbar", background="#0d9488", troughcolor="#e5e7eb", thickness=18)
        style.configure("Dl.TButton", padding=(12, 3), font=("Segoe UI", 9))
        header = tk.Frame(root, bg="#101827", padx=28, pady=22)
        header.pack(fill="x")
        tk.Label(header, text="Free-to-Download", bg="#101827", fg="white", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        tk.Label(header, text="Your downloads. Organized, scheduled, and in motion.", bg="#101827", fg="#a8b8cc", font=("Segoe UI", 11)).pack(anchor="w", pady=(4, 0))
        body = tk.Frame(root, bg="#f4f7fb", padx=24, pady=20)
        body.pack(fill="both", expand=True)
        toolbar = tk.Frame(body, bg="#f4f7fb")
        toolbar.pack(fill="x", pady=(0, 14))
        for label, command in (("Batch URLs", self.batch), ("Start all", self.start_all), ("Pause all", self.pause_all),
                               ("Schedule", self.schedule), ("Settings", self.options), ("Browser", self.browser_options)):
            ttk.Button(toolbar, text=label, command=command).pack(side="left", padx=(0, 6))
        add = tk.Frame(body, bg="#f4f7fb")
        add.pack(fill="x")
        tk.Label(add, text="DOWNLOAD URL", bg="#f4f7fb", fg="#475569", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = tk.Frame(add, bg="#f4f7fb")
        row.pack(fill="x", pady=(6, 12))
        self.url = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.url, font=("Segoe UI", 11))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        entry.bind("<Return>", lambda _: self.add())
        ttk.Button(row, text="+ Add download", command=self.add).pack(side="right")
        ttk.Button(row, text="Download video", command=self.add_video).pack(side="right", padx=6)
        settings = tk.Frame(body, bg="#f4f7fb")
        settings.pack(fill="x", pady=(0, 18))
        self.connections = tk.IntVar(value=int(self.settings["connections"]))
        self.parallel = tk.IntVar(value=int(self.settings["parallel"]))
        tk.Label(settings, text="Connections per file", bg="#f4f7fb", fg="#475569").pack(side="left")
        ttk.Combobox(settings, textvariable=self.connections, values=(1, 2, 4, 8, 16), width=4, state="readonly").pack(side="left", padx=(8, 20))
        tk.Label(settings, text="Simultaneous files", bg="#f4f7fb", fg="#475569").pack(side="left")
        ttk.Combobox(settings, textvariable=self.parallel, values=(1, 2, 3, 4), width=4, state="readonly").pack(side="left", padx=8)
        self.summary = tk.Label(settings, text="Ready", bg="#f4f7fb", fg="#0f766e", font=("Segoe UI", 10, "bold"))
        self.summary.pack(side="right")
        content = tk.Frame(body, bg="#f4f7fb")
        content.pack(fill="both", expand=True)
        sidebar = tk.Frame(content, bg="#e9eef5", width=145)
        sidebar.pack(side="left", fill="y", padx=(0, 14))
        tk.Label(sidebar, text="LIBRARY", bg="#e9eef5", fg="#64748b", font=("Segoe UI", 9, "bold"), pady=10).pack(anchor="w", padx=12)
        self.filter = tk.StringVar(value="All downloads")
        for name in ("All downloads", "Downloading", "Queued", "Scheduled", "Paused", "Complete", "Error", "Documents", "Archives", "Music", "Video", "Programs", "Other"):
            tk.Radiobutton(sidebar, text=name, variable=self.filter, value=name, indicatoron=False,
                           bg="#e9eef5", fg="#334155", selectcolor="#c8dced", activebackground="#dbeafe", bd=0,
                           anchor="w", padx=14, pady=5, font=("Segoe UI", 10)).pack(fill="x")
        right = tk.Frame(content, bg="#f4f7fb")
        right.pack(side="left", fill="both", expand=True)
        self.search = tk.StringVar()
        search_row = tk.Frame(right, bg="#f4f7fb")
        search_row.pack(fill="x", pady=(0, 8))
        tk.Label(search_row, text="Search", bg="#f4f7fb", fg="#64748b").pack(side="left", padx=(0, 10))
        ttk.Entry(search_row, textvariable=self.search).pack(side="left", fill="x", expand=True)
        frame = tk.Frame(right, bg="white")
        frame.pack(fill="both", expand=True)
        columns = ("name", "status", "progress", "size", "speed", "eta")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        for col, title, width in zip(columns, ("File", "Status", "Progress", "Size", "Speed", "Time left"), (270, 110, 90, 100, 100, 90)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, minwidth=65, stretch=col == "name")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.details())
        self.tree.bind("<Button-3>", self.context_menu)
        self.tree.bind("<Double-1>", lambda event: self.tree.identify_row(event.y) and self.show_window(self.tree.identify_row(event.y)))
        # Pinned to the bottom before the list claims space, so on short screens the list shrinks
        # instead of pushing the progress bar and Pause/Resume buttons out of the window.
        footer = tk.Frame(body, bg="#f4f7fb")
        footer.pack(side="bottom", fill="x", before=content)
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(fill="x", pady=(16, 8))
        self.detail = tk.StringVar(value="Paste a direct file URL to get started. Existing files are never overwritten.")
        tk.Label(footer, textvariable=self.detail, bg="#f4f7fb", fg="#475569", anchor="w", justify="left", wraplength=1030, font=("Segoe UI", 10)).pack(fill="x")
        self.chunks = tk.Canvas(footer, height=22, bg="#f4f7fb", highlightthickness=0)
        self.chunks.pack(fill="x", pady=(6, 0))
        controls = tk.Frame(footer, bg="#f4f7fb")
        controls.pack(fill="x", pady=(16, 0))
        for label, command in (("Pause", self.pause), ("Resume / Retry", self.resume), ("Open folder", self.open_folder), ("Refresh URL", self.refresh_url), ("Remove", self.remove)):
            ttk.Button(controls, text=label, command=command).pack(side="left", padx=(0, 8))
        tk.Label(controls, text=f"v{VERSION}  ·  {NAME}", bg="#f4f7fb", fg="#64748b").pack(side="right")
        self.load()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(250, self.tick)

    def register(self, record):
        kind = MediaDownload if record.get("media") else Download
        extra = {"referer": record.get("referer", ""), "quality": record.get("quality", "best")} if record.get("media") else {}
        job = kind(record["url"], record["destination"], self.data / record["id"], record["connections"], **extra,
                       limiter=self.limiter, expected_sha256=record.get("expected_sha256", ""), timeout=int(self.settings["timeout"]))
        job.status = record.get("status", "Queued")
        if job.status not in ("Complete", "Queued", "Scheduled", "Error", "Paused"):
            job.status = "Paused"
        job.error = record.get("error", "")
        job.sha256 = record.get("sha256", "")
        if job.status == "Complete" and job.destination.exists():
            job.received = job.total = job.destination.stat().st_size
        self.jobs[record["id"]] = {"job": job, "thread": None, "sample": (time.monotonic(), 0), "speed": 0,
                                   "scheduled_at": float(record.get("scheduled_at", 0)),
                                   "category": record.get("category", category_for(job.destination.name))}
        if self.tree.exists(record["id"]):
            raise ValueError("Duplicate queue identifier")
        self.tree.insert("", "end", iid=record["id"], values=(job.destination.name, job.status, "—", "—", "—", "—"))

    def load(self):
        path = self.data / "queue.json"
        if not path.exists():
            return
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
            for record in records:
                if not isinstance(record["id"], str) or len(record["id"]) != 32 or any(c not in "0123456789abcdef" for c in record["id"]):
                    raise ValueError("Invalid queue identifier")
                # Restored work waits for an explicit resume.
                if record.get("status") not in ("Complete", "Scheduled"):
                    record["status"] = "Paused"
                self.register(record)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            messagebox.showwarning("Queue recovery", f"Could not restore every queue entry: {exc}")

    def save(self):
        records = [{"id": key, "url": item["job"].url, "destination": str(item["job"].destination),
                    "media": isinstance(item["job"], MediaDownload), "referer": getattr(item["job"], "referer", ""),
                    "quality": getattr(item["job"], "quality", "best"),
                    "connections": item["job"].connections, "status": item["job"].status,
                    "error": item["job"].error, "sha256": item["job"].sha256,
                    "expected_sha256": item["job"].expected_sha256, "scheduled_at": item["scheduled_at"],
                    "category": item["category"]} for key, item in self.jobs.items()]
        atomic_json(self.data / "queue.json", records)
        self.settings["connections"] = self.connections.get()
        self.settings["parallel"] = self.parallel.get()
        atomic_json(self.data / "settings.json", self.settings)

    def add_video(self):
        try:
            self.queue_urls([validate_url(self.url.get().strip())], media=True)
            self.url.set("")
        except ValueError as exc:
            messagebox.showerror("Video URL", str(exc))

    def add(self):
        url = self.url.get().strip()
        try:
            validate_url(url)
        except ValueError as exc:
            messagebox.showerror("Download URL", str(exc))
            return
        destination = filedialog.asksaveasfilename(title="Save download as", initialfile=filename_for(url), initialdir=self.settings["folder"])
        if not destination:
            return
        if Path(destination).exists() or any(item["job"].destination == Path(destination) for item in self.jobs.values()):
            messagebox.showerror("Choose another filename", "That destination already exists or is already in the queue.")
            return
        key = uuid.uuid4().hex
        self.register({"id": key, "url": url, "destination": destination, "connections": self.connections.get()})
        self.tree.selection_set(key)
        self.url.set("")
        self.save()

    def selected(self, key=None):
        if key:
            return key, self.jobs.get(key)
        selected = self.tree.selection()
        return (selected[0], self.jobs[selected[0]]) if selected else (None, None)

    def show_window(self, key):
        window = self.windows.get(key)
        if window and window.alive():
            window.win.deiconify()
            window.win.lift()
            return
        offset = 24 * (sum(w.alive() for w in self.windows.values()) % 6)
        self.windows[key] = DownloadWindow(self, key, offset)

    def pause(self, key=None):
        _, item = self.selected(key)
        if item and item["job"].status in ("Queued", "Scheduled", "Connecting", "Downloading", "Finishing"):
            item["job"].pause()
            if not item["thread"]:
                item["job"].status = "Paused"
            else:
                item["job"].status = "Pausing"
            self.save()

    def resume(self, key=None):
        _, item = self.selected(key)
        if item and item["job"].status in ("Paused", "Scheduled", "Error") and not item["thread"]:
            item["job"].stop.clear()
            item["job"].status = "Queued"
            item["job"].error = ""
            item["scheduled_at"] = 0
            self.save()

    def remove(self):
        key, item = self.selected()
        if not item:
            return
        if item["thread"]:
            messagebox.showinfo("Download running", "Pause this download and wait for it to stop before removing it.")
            return
        if not messagebox.askyesno("Remove download", "Remove this queue entry and its partial files? Completed files will be kept."):
            return
        import shutil
        target = item["job"].workdir.resolve()
        if target.parent != self.data.resolve():
            raise ValueError("Invalid partial-download directory")
        if target.exists():
            shutil.rmtree(target)
        del self.jobs[key]
        self.tree.delete(key)
        if key in self.windows:
            self.windows.pop(key).close()
        self.save()

    def open_folder(self):
        _, item = self.selected()
        if item:
            folder = item["job"].destination.parent
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))

    def details(self):
        _, item = self.selected()
        if item:
            job = item["job"]
            self.progress["value"] = job.received / job.total * 100 if job.total else 0
            scheduled = ""
            if job.status == "Scheduled":
                scheduled = "Starts " + datetime.fromtimestamp(item["scheduled_at"]).astimezone().strftime("%d %b %Y, %H:%M %Z")
            self.detail.set(job.error or scheduled or (f"Saved to {job.destination}\nSHA-256: {job.sha256}" if job.status == "Complete" else f"{job.mode}  ·  {job.active_connections} active  ·  {size(job.received)} received  ·  {job.retries} retries"))
            if isinstance(job, MediaDownload):
                draw_cells(self.chunks, job.fragment_index / job.fragment_count if job.fragment_count
                           else (job.received / job.total if job.total else 0))
            else:
                draw_segments(self.chunks, job)
        else:
            self.progress["value"] = 0
            self.chunks.delete("all")

    def context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        menu = tk.Menu(self.root, tearoff=False)
        for label, command in (("Show progress window", lambda: self.show_window(row)),
                               ("Resume / Retry", self.resume), ("Pause", self.pause), ("Schedule", self.schedule),
                               ("Move to front", self.prioritize), ("Verify SHA-256", self.checksum),
                               ("Refresh URL", self.refresh_url), ("Copy URL", self.copy_url), ("Open folder", self.open_folder), ("Remove", self.remove)):
            menu.add_command(label=label, command=command)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def copy_url(self):
        _, item = self.selected()
        if item:
            self.root.clipboard_clear()
            self.root.clipboard_append(item["job"].url)

    def prioritize(self):
        key, item = self.selected()
        if item:
            self.jobs = {key: item, **self.jobs}
            self.save()

    def checksum(self):
        _, item = self.selected()
        if not item:
            return
        expected = simpledialog.askstring("SHA-256", "Publisher's expected SHA-256 (64 hexadecimal characters):", initialvalue=item["job"].expected_sha256, parent=self.root)
        if expected is None:
            return
        import re
        expected = expected.strip().lower()
        if expected and not re.fullmatch(r"[0-9a-f]{64}", expected):
            messagebox.showerror("Invalid checksum", "Enter exactly 64 hexadecimal characters.")
            return
        job = item["job"]
        if item["thread"]:
            messagebox.showinfo("Pause first", "Pause this download before changing its expected checksum.")
            return
        if job.status == "Complete":
            messagebox.showinfo("Checksum result", "Matches the checksum recorded at download completion." if expected == job.sha256 else "Does not match the checksum recorded at download completion.")
            return
        job.expected_sha256 = expected
        self.save()

    def refresh_url(self):
        _, item = self.selected()
        if not item or item["thread"] or item["job"].status == "Complete":
            messagebox.showinfo("Refresh URL", "Select a stopped, unfinished download first.")
            return
        value = simpledialog.askstring("Refresh expired URL", "New direct URL. A changed URL restarts this file to avoid mixing different content.", initialvalue=item["job"].url, parent=self.root)
        if value:
            try:
                item["job"].url = validate_url(value.strip())
                item["job"].stop.clear()
                item["job"].status = "Queued"
                item["scheduled_at"] = 0
                self.save()
            except ValueError as exc:
                messagebox.showerror("Invalid URL", str(exc))

    def start_all(self):
        for item in self.jobs.values():
            if not item["thread"] and item["job"].status in ("Paused", "Scheduled", "Error", "Queued"):
                item["job"].stop.clear()
                item["job"].status = "Queued"
                item["scheduled_at"] = 0
        self.save()

    def pause_all(self):
        for item in self.jobs.values():
            if item["job"].status not in ("Complete", "Error", "Paused"):
                item["job"].pause()
                item["job"].status = "Pausing" if item["thread"] else "Paused"
        self.save()

    def schedule(self):
        _, item = self.selected()
        if not item or item["thread"] or item["job"].status == "Complete":
            messagebox.showinfo("Schedule", "Select a stopped, unfinished download first.")
            return
        minutes = simpledialog.askinteger("Schedule download", "Start this download in how many minutes?\nKeep Free-to-Download running until the scheduled time.", minvalue=1, maxvalue=10080, initialvalue=60, parent=self.root)
        if minutes is not None:
            item["scheduled_at"] = time.time() + minutes * 60
            item["job"].status = "Scheduled"
            item["job"].stop.clear()
            self.save()

    def queue_urls(self, urls, folder=None, delay=0, media=False, referer="", title="", quality="best"):
        parsed = [validate_url(url.strip()) for url in urls if url.strip()]
        reserved = {item["job"].destination for item in self.jobs.values()}
        count = 0
        for url in dict.fromkeys(parsed):
            name = filename_for(url)
            if media:
                # The extension sends the page title so saved videos get readable names.
                name = (safe_filename(title)[:120].rstrip(" .") or "video-" + uuid.uuid4().hex[:8]) + (".mp3" if quality == "audio" else ".mkv")
            category = category_for(name)
            directory = Path(folder or self.settings["folder"])
            if self.settings["categories"]:
                directory /= category
            destination = directory / name
            number = 1
            while destination.exists() or destination in reserved:
                destination = directory / f"{Path(name).stem} ({number}){Path(name).suffix}"
                number += 1
            reserved.add(destination)
            key = uuid.uuid4().hex
            self.register({"id": key, "url": url, "destination": str(destination), "connections": self.connections.get(),
                           "media": media, "referer": referer, "quality": quality,
                           "category": category, "status": "Scheduled" if delay else "Queued",
                           "scheduled_at": time.time() + delay * 60 if delay else 0})
            count += 1
        self.save()
        return count

    def batch(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Add multiple downloads")
        dialog.geometry("650x440")
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Paste one direct HTTP or HTTPS URL per line.").pack(anchor="w")
        text = tk.Text(frame, height=12, font=("Segoe UI", 10), wrap="word")
        text.pack(fill="both", expand=True, pady=10)
        delay = tk.IntVar(value=0)
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Start after (minutes, 0 = now)").pack(side="left")
        ttk.Spinbox(row, from_=0, to=10080, textvariable=delay, width=8).pack(side="left", padx=10)
        def import_file():
            path = filedialog.askopenfilename(filetypes=[("URL list", "*.txt"), ("All files", "*.*")])
            if path:
                try:
                    text.insert("end", Path(path).read_text(encoding="utf-8"))
                except OSError as exc:
                    messagebox.showerror("Import", str(exc))
        def submit():
            try:
                minutes = delay.get()
                if not 0 <= minutes <= 10080:
                    raise ValueError("Delay must be between 0 and 10080 minutes")
                count = self.queue_urls(text.get("1.0", "end").splitlines(), delay=minutes)
                dialog.destroy()
                self.detail.set(f"Added {count} download(s).")
            except (ValueError, tk.TclError) as exc:
                messagebox.showerror("Batch downloads", str(exc))
        ttk.Button(row, text="Import .txt", command=import_file).pack(side="right")
        ttk.Button(frame, text="Add to queue", command=submit).pack(anchor="e")

    def options(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Download settings")
        dialog.transient(self.root)
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        folder = tk.StringVar(value=self.settings["folder"])
        limit = tk.StringVar(value=str(self.settings["limit_kib"]))
        timeout = tk.StringVar(value=str(self.settings["timeout"]))
        categories = tk.BooleanVar(value=self.settings["categories"])
        notify = tk.BooleanVar(value=self.settings["notify"])
        progress_window = tk.BooleanVar(value=self.settings["progress_window"])
        complete_dialog = tk.BooleanVar(value=self.settings["complete_dialog"])
        for row, (label, variable) in enumerate((("Save batch / browser downloads to", folder), ("Total speed limit (KiB/s, 0 = unlimited)", limit), ("Network timeout (seconds)", timeout))):
            ttk.Label(frame, text=label).grid(row=row * 2, column=0, sticky="w", pady=(8, 3))
            ttk.Entry(frame, textvariable=variable, width=64).grid(row=row * 2 + 1, column=0, sticky="ew")
        def browse():
            value = filedialog.askdirectory(initialdir=folder.get())
            if value:
                folder.set(value)
        ttk.Button(frame, text="Browse", command=browse).grid(row=1, column=1, padx=8)
        ttk.Checkbutton(frame, text="Sort batch and browser downloads into category folders", variable=categories).grid(row=6, column=0, sticky="w", pady=10)
        ttk.Checkbutton(frame, text="Play a sound when a download finishes", variable=notify).grid(row=7, column=0, sticky="w")
        ttk.Checkbutton(frame, text="Show the download progress window when a download starts", variable=progress_window).grid(row=8, column=0, sticky="w", pady=(10, 0))
        ttk.Checkbutton(frame, text="Show the download complete dialog", variable=complete_dialog).grid(row=9, column=0, sticky="w", pady=(10, 0))
        def submit():
            try:
                cap = int(limit.get())
                seconds = int(timeout.get())
                if not 0 <= cap <= 1048576 or not 5 <= seconds <= 120 or not Path(folder.get()).is_absolute():
                    raise ValueError("Use an absolute folder, a nonnegative speed limit, and a timeout between 5 and 120 seconds.")
                self.settings.update(folder=folder.get(), limit_kib=cap, timeout=seconds, categories=categories.get(), notify=notify.get(),
                                     progress_window=progress_window.get(), complete_dialog=complete_dialog.get())
                self.limiter.set_rate(cap * 1024)
                self.save()
                dialog.destroy()
            except ValueError as exc:
                messagebox.showerror("Settings", str(exc))
        ttk.Button(frame, text="Save settings", command=submit).grid(row=10, column=0, sticky="e", pady=(20, 0))

    def browser_options(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Browser integration")
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.bind("<Escape>", lambda event: dialog.destroy())
        dialog.geometry("+80+80")
        frame = ttk.Frame(dialog, padding=22)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Browser button", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="The Free-to-Download extension connects to this app automatically. There is nothing to paste.\n\n"
                              "Not added to your browser yet? Open the extensions page, turn on Developer mode, click "
                              "Load unpacked and choose the extension folder.", wraplength=520, justify="left").pack(anchor="w", pady=(10, 14))
        folder = ROOT / "browser-extension"
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w")
        for label, executable, url in (("Open Chrome extensions", "chrome.exe", "chrome://extensions/"),
                                       ("Open Edge extensions", "msedge.exe", "edge://extensions/")):
            path = browser_path(executable)
            if path:
                ttk.Button(buttons, text=label, command=lambda path=path, url=url: subprocess.Popen([path, url])).pack(side="left", padx=(0, 8))
        if folder.is_dir():
            ttk.Button(buttons, text="Open extension folder", command=lambda: os.startfile(str(folder))).pack(side="left")
        if self.bridge:
            ttk.Label(frame, text=("Connection: " + self.bridge.error) if self.bridge.error
                      else f"Connection: listening on this computer only (port {self.bridge.port})").pack(anchor="w", pady=(16, 0))
            advanced = ttk.Frame(frame)
            def show_token():
                toggle.pack_forget()
                entry = ttk.Entry(advanced, width=60)
                entry.insert(0, self.bridge.token)
                entry.configure(state="readonly")
                entry.pack(side="left", fill="x", expand=True)
                def copy():
                    self.root.clipboard_clear()
                    self.root.clipboard_append(self.bridge.token)
                ttk.Button(advanced, text="Copy", command=copy).pack(side="left", padx=(8, 0))
            toggle = ttk.Button(frame, text="Manual pairing token…", command=show_token)
            toggle.pack(anchor="w", pady=(10, 0))
            advanced.pack(fill="x", pady=(6, 0))
        ttk.Label(frame, text="The extension reads page links only when you ask it to. It does not collect cookies or intercept other downloads.",
                  wraplength=520, foreground="#64748b").pack(anchor="w", pady=(16, 0))
        ttk.Button(frame, text="Close", command=dialog.destroy).pack(anchor="e", pady=(12, 0))

    def tick(self):
        dirty = False
        now = time.monotonic()
        active = 0
        total_speed = 0
        if self.bridge and self.bridge.show_requested:
            self.bridge.show_requested = False
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(500, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        if self.bridge and not self.closing:
            for _ in range(5):
                try:
                    request = self.bridge.inbox.get_nowait()
                except queue.Empty:
                    break
                try:
                    self.queue_urls(request["urls"], media=request.get("media", False), referer=request.get("referer", ""),
                                    title=request.get("title", ""), quality=request.get("quality", "best"))
                except (ValueError, OSError) as exc:
                    self.detail.set(f"Browser handoff failed: {exc}")
        for key, item in self.jobs.items():
            job = item["job"]
            if item["thread"] and not item["thread"].is_alive():
                item["thread"] = None
                dirty = True
                if job.status == "Complete" and self.settings["notify"] and not self.closing:
                    try:
                        import winsound
                        winsound.MessageBeep(winsound.MB_OK)
                    except (ImportError, RuntimeError):
                        pass
                if job.status == "Complete" and not self.closing:
                    if self.settings["complete_dialog"]:
                        self.show_window(key)
                    elif key in self.windows:
                        self.windows.pop(key).close()
            if job.status == "Scheduled" and item["scheduled_at"] <= time.time() and not self.closing:
                job.stop.clear()
                job.status = "Queued"
                dirty = True
            if item["thread"]:
                active += 1
            before, received = item["sample"]
            delta = max(0, job.transferred - received) / max(now - before, 0.001)
            item["speed"] = 0.65 * item["speed"] + 0.35 * delta if job.status == "Downloading" else 0
            if job.status == "Downloading" and getattr(job, "reported_speed", 0):
                # yt-dlp reports its own smoothed rate; ours collapses between its progress callbacks.
                item["speed"] = job.reported_speed
            item["sample"] = (now, job.transferred)
            rate = item["speed"]
            total_speed += rate
            eta = f"{max(0, int((job.total - job.received) / rate))} sec" if job.total and rate > 1 else "—"
            percent = f"{job.received / job.total * 100:.1f}%" if job.total else ("100%" if job.status == "Complete" else "—")
            self.tree.item(key, values=(job.destination.name, job.status, percent, size(job.total), size(rate) + "/s" if rate else "—", eta))
            chosen = self.filter.get()
            matches = chosen == "All downloads" or chosen == item["category"] or chosen == job.status or (chosen == "Downloading" and job.status in ("Connecting", "Finishing", "Pausing"))
            matches = matches and self.search.get().lower() in (job.destination.name + " " + job.url).lower()
            if matches:
                self.tree.move(key, "", "end")
            else:
                self.tree.detach(key)
        if not self.closing:
            for key, item in self.jobs.items():
                if active >= self.parallel.get():
                    break
                if item["job"].status == "Queued" and not item["thread"]:
                    item["sample"] = (now, item["job"].transferred)
                    item["thread"] = threading.Thread(target=item["job"].run, daemon=False)
                    item["thread"].start()
                    active += 1
                    if self.settings["progress_window"]:
                        self.show_window(key)
        for key, window in list(self.windows.items()):
            if not window.refresh():
                del self.windows[key]
        limit_text = f"  ·  limit {self.settings['limit_kib']} KiB/s" if self.settings["limit_kib"] else ""
        self.summary.config(text=f"{active} active  ·  {size(total_speed)}/s" + limit_text)
        self.details()
        if dirty:
            self.save()
        if self.closing and not active:
            self.save()
            if self.bridge:
                self.bridge.close()
            self.instance.close()
            self.root.destroy()
            return
        self.root.after(250, self.tick)

    def close(self):
        self.closing = True
        for item in self.jobs.values():
            item["job"].pause()
        self.detail.set("Saving partial downloads. Waiting for active requests to stop…")
        self.save()


if __name__ == "__main__":
    if native_host.is_host_launch(sys.argv):
        # Started by the browser because the extension found the app closed: launch it and exit.
        native_host.serve(sys.executable)
        raise SystemExit(0)
    if len(sys.argv) == 4 and sys.argv[1] == "--media-smoke":
        target = Path(sys.argv[3])
        target.mkdir(parents=True, exist_ok=True)
        job = MediaDownload(sys.argv[2], target / "video.mkv", target / "parts", 4)
        job.run()
        atomic_json(target / "result.json", {"status": job.status, "error": job.error, "destination": str(job.destination)})
        raise SystemExit(0 if job.status == "Complete" else 1)
    # Relative Tcl paths also work in Windows environments whose path normalizer
    # cannot resolve an ancestor directory. Bundled resources remain read-only.
    for variable in ("TCL_LIBRARY", "TK_LIBRARY"):
        if os.environ.get(variable) and Path(os.environ[variable]).exists():
            os.environ[variable] = Path(os.path.relpath(os.environ[variable])).as_posix()
    window = tk.Tk()
    try:
        app = App(window, sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--smoke-test" else None)
    except RuntimeError as exc:
        # Already running (often minimized since sign-in): bring that window forward instead of complaining.
        if not show_running_instance():
            messagebox.showerror("Free-to-Download", str(exc))
        window.destroy()
        raise SystemExit(0)
    if getattr(sys, "frozen", False) and "--smoke-test" not in sys.argv:
        # Refresh on every start so the browser can always launch this copy, even after moving or updating it.
        native_host.register(app.data, sys.executable, EXTENSION_IDS)
    if "--minimized" in sys.argv:
        window.iconify()
    if "--smoke-test" in sys.argv:
        window.after(600, app.close)
    window.mainloop()
