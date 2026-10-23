"""Per-download progress window that turns into a completion dialog when the file is ready."""
import os
import subprocess
import time
import tkinter as tk
from tkinter import ttk

from media import MediaDownload

BG = "#f0f2f5"
ACCENT = "#0d9488"
WIDTH = 500  # text width in pixels; the window never grows past it


def size(value):
    if value is None:
        return "Unknown"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def duration(seconds):
    seconds = int(seconds)
    if seconds >= 3600:
        return f"{seconds // 3600} hr {seconds % 3600 // 60:02d} min"
    if seconds >= 60:
        return f"{seconds // 60} min {seconds % 60:02d} sec"
    return f"{seconds} sec"


def draw_segments(canvas, job):
    canvas.delete("all")
    chunks = list(job.segment_progress.copy().items())
    if not chunks:
        return
    width = max(1, canvas.winfo_width())
    height = max(4, canvas.winfo_height() - 4)
    count = max(max(i for i, _ in chunks) + 1, 1)
    step = width / count
    for index, (done, total) in chunks:
        color = ACCENT if done == total else ("#60a5fa" if done else "#cbd5e1")
        canvas.create_rectangle(index * step, 2, (index + 1) * step - 1, height, fill=color, outline="")


def draw_cells(canvas, fraction, cells=40):
    """A row of cells filled left to right, matching the look of the connection view."""
    canvas.delete("all")
    width = max(1, canvas.winfo_width())
    height = max(4, canvas.winfo_height() - 4)
    step = width / cells
    filled = fraction * cells
    for index in range(cells):
        color = ACCENT if index + 1 <= filled else ("#60a5fa" if index < filled else "#cbd5e1")
        canvas.create_rectangle(index * step, 2, (index + 1) * step - 1, height, fill=color, outline="")


def open_file(path):
    os.startfile(str(path))


def show_in_folder(path):
    if path.exists():
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.startfile(str(path.parent))


class DownloadWindow:
    """Status window for one queue entry; closing it never stops the download."""

    def __init__(self, app, key, offset=0):
        self.app, self.key = app, key
        self.state = None
        self.phase, self.phase_started = None, time.monotonic()
        self.details_shown = True
        self.win = tk.Toplevel(app.root, bg=BG)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda _: self.close())
        x = app.root.winfo_screenwidth() // 2 - 280 + offset
        y = app.root.winfo_screenheight() // 3 - 160 + offset
        self.win.geometry(f"+{max(0, x)}+{max(0, y)}")
        # Pop up over the browser the way a download manager should, without staying pinned there.
        self.win.attributes("-topmost", True)
        self.win.after(4000, lambda: self.win.winfo_exists() and self.win.attributes("-topmost", False))
        self.body = tk.Frame(self.win, bg=BG)
        self.body.pack(fill="both", expand=True)
        self.refresh()

    @property
    def item(self):
        return self.app.jobs.get(self.key)

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def close(self):
        if self.alive():
            self.win.destroy()

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    # ---- downloading view -------------------------------------------------
    def build_progress(self):
        self.clear()
        job = self.item["job"]
        tabs = tk.Frame(self.body, bg=BG)
        tabs.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(tabs, text="Download status", bg="white", fg="#111827", font=("Segoe UI", 9), padx=12, pady=4,
                 relief="solid", bd=1).pack(side="left")
        panel = tk.Frame(self.body, bg="white", highlightthickness=1, highlightbackground="#b8c0cc", padx=14, pady=10)
        panel.pack(fill="both", padx=12)
        url = tk.Entry(panel, font=("Segoe UI", 9), relief="flat", readonlybackground="white", fg="#1d4ed8", width=72)
        url.insert(0, job.url)
        url.configure(state="readonly")
        url.pack(fill="x")
        # Long messages wrap so the window keeps its size.
        self.status_label = tk.Label(panel, text="", bg="white", fg="#111827", font=("Segoe UI", 9, "bold"), anchor="w",
                                     justify="left", wraplength=WIDTH)
        self.status_label.pack(fill="x", pady=(6, 6))
        grid = tk.Frame(panel, bg="white")
        grid.pack(fill="x")
        self.fields = {}
        for row, name in enumerate(("File size", "Downloaded", "Transfer rate", "Time left", "Resume capability")):
            tk.Label(grid, text=name, bg="white", fg="#4b5563", font=("Segoe UI", 9), anchor="w", width=17).grid(row=row, column=0, sticky="w", pady=1)
            value = tk.Label(grid, text="", bg="white", fg="#111827", font=("Segoe UI", 9), anchor="w")
            value.grid(row=row, column=1, sticky="w", pady=1)
            self.fields[name] = value
        self.bar = ttk.Progressbar(panel, mode="determinate", length=500, style="Download.Horizontal.TProgressbar")
        self.bar.pack(fill="x", pady=(10, 2))
        buttons = tk.Frame(self.body, bg=BG)
        buttons.pack(fill="x", padx=12, pady=10)
        self.toggle = ttk.Button(buttons, style="Dl.TButton", text="<< Hide details", command=self.toggle_details)
        self.toggle.pack(side="left")
        ttk.Button(buttons, style="Dl.TButton", text="Cancel", command=self.cancel).pack(side="right")
        self.pause_button = ttk.Button(buttons, style="Dl.TButton", text="Pause", command=self.pause_or_resume)
        self.pause_button.pack(side="right", padx=6)
        self.details = tk.Frame(self.body, bg=BG)
        media = isinstance(job, MediaDownload)
        tk.Label(self.details, text="Download progress by fragment" if media else "Download progress by connection",
                 bg=BG, fg="#4b5563", font=("Segoe UI", 9), anchor="w").pack(fill="x")
        self.segments = tk.Canvas(self.details, height=20, bg="white", highlightthickness=1, highlightbackground="#b8c0cc")
        self.segments.pack(fill="x", pady=(3, 4))
        self.connection_text = tk.Label(self.details, text="", bg=BG, fg="#4b5563", font=("Segoe UI", 9), anchor="w", justify="left",
                                        wraplength=WIDTH)
        self.connection_text.pack(fill="x")
        if self.details_shown:
            self.details.pack(fill="x", padx=12, pady=(0, 12))

    def toggle_details(self):
        self.details_shown = not self.details_shown
        if self.details_shown:
            self.details.pack(fill="x", padx=12, pady=(0, 12))
            self.toggle.configure(text="<< Hide details")
        else:
            self.details.pack_forget()
            self.toggle.configure(text="Show details >>")

    def pause_or_resume(self):
        if self.item["job"].status in ("Paused", "Error"):
            self.app.resume(self.key)
        else:
            self.app.pause(self.key)

    def cancel(self):
        if self.item and self.item["job"].status not in ("Complete", "Paused", "Error"):
            self.app.pause(self.key)
        self.close()

    def update_progress(self):
        item = self.item
        job, rate = item["job"], item["speed"]
        percent = job.received / job.total * 100 if job.total else 0
        self.win.title(f"{percent:.0f}% {job.destination.name}" if job.total else job.destination.name)
        # While nothing is measurable yet (finding the video, connecting, merging) keep the window visibly alive:
        # animated dots, a running seconds counter and a sweeping bar.
        if job.status != self.phase:
            self.phase, self.phase_started = job.status, time.monotonic()
        busy = job.status in ("Connecting", "Finishing") or (job.status == "Downloading" and not job.total)
        waited = int(time.monotonic() - self.phase_started)
        dots = "." * (int(time.monotonic() * 2) % 3 + 1)
        connecting = "Finding the video on the page" if isinstance(job, MediaDownload) else "Connecting to the server"
        text = {"Queued": "Waiting in queue…", "Scheduled": "Scheduled", "Connecting": connecting,
                "Downloading": "Receiving data",
                "Finishing": job.mode if isinstance(job, MediaDownload) else "Assembling and verifying file",
                "Pausing": "Pausing…", "Paused": "Paused", "Error": "Error: " + (job.error or "download failed")}
        status = text.get(job.status, job.status)
        if busy:
            status = f"{status}{dots:<3}  {waited} s"
        elif job.status == "Downloading":
            status += dots
        self.status_label.configure(text=status, fg="#b91c1c" if job.status == "Error" else "#111827")
        self.fields["File size"].configure(text=size(job.total))
        self.fields["Downloaded"].configure(text=f"{size(job.received)}" + (f" ( {percent:.2f} % )" if job.total else ""))
        waiting = "Waiting for the site" + dots if job.status == "Connecting" else "—"
        # The smoothed rate decays toward zero between progress reports; under 1 KB/s it says nothing useful.
        self.fields["Transfer rate"].configure(text=f"{size(rate)}/sec" if rate >= 1024 else waiting)
        left = (job.total - job.received) / rate if job.total and rate > 1 else None
        self.fields["Time left"].configure(text=duration(left) if left is not None else "—")
        if isinstance(job, MediaDownload) or "resumable" in job.mode:
            resume = "Yes"
        elif "cannot" in job.mode:
            resume = "No"
        else:
            resume = "Checking…"
        self.fields["Resume capability"].configure(text=resume, fg="#047857" if resume == "Yes" else "#111827")
        if busy:
            if self.bar["mode"] != "indeterminate":
                self.bar.configure(mode="indeterminate")
                self.bar.start(12)
        else:
            if self.bar["mode"] != "determinate":
                self.bar.stop()
                self.bar.configure(mode="determinate")
            self.bar["value"] = percent
        self.pause_button.configure(text="Resume" if job.status in ("Paused", "Error") else "Pause",
                                    state="disabled" if job.status == "Pausing" or (job.status == "Error" and item["thread"]) else "normal")
        if self.details_shown:
            if isinstance(job, MediaDownload):
                # Videos arrive as a series of fragments (or one file), not parallel byte ranges.
                if job.fragment_count:
                    draw_cells(self.segments, job.fragment_index / job.fragment_count)
                    detail = f"Fragment {job.fragment_index} of {job.fragment_count}"
                else:
                    draw_cells(self.segments, job.received / job.total if job.total else 0)
                    detail = "Single file"
                self.connection_text.configure(text=f"{detail}  ·  {job.mode}")
            else:
                draw_segments(self.segments, job)
                self.connection_text.configure(text=f"{job.active_connections} active connection(s)  ·  {job.mode}  ·  {job.retries} retries")

    # ---- completion view --------------------------------------------------
    def build_complete(self):
        self.clear()
        job = self.item["job"]
        already = getattr(job, "already_exists", False)
        heading = "Already downloaded" if already else "Download complete"
        self.win.title(heading)
        top = tk.Frame(self.body, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(top, text="✓", bg="#2563eb" if already else ACCENT, fg="white", font=("Segoe UI", 18, "bold"), width=2).pack(side="left", padx=(0, 12))
        text = tk.Frame(top, bg=BG)
        text.pack(side="left")
        tk.Label(text, text=heading, bg=BG, fg="#111827", font=("Segoe UI", 13, "bold"), anchor="w").pack(anchor="w")
        if already:
            tk.Label(text, text="This video is already in your downloads, so it was not downloaded again.",
                     bg=BG, fg="#4b5563", font=("Segoe UI", 9), anchor="w").pack(anchor="w")
        panel = tk.Frame(self.body, bg="white", highlightthickness=1, highlightbackground="#b8c0cc", padx=14, pady=10)
        panel.pack(fill="x", padx=16)
        for row, (name, value) in enumerate((("Address", job.url), ("File", job.destination.name),
                                             ("Saved to", str(job.destination.parent)), ("Size", size(job.total)))):
            tk.Label(panel, text=name, bg="white", fg="#4b5563", font=("Segoe UI", 9), anchor="w", width=10).grid(row=row, column=0, sticky="nw", pady=2)
            entry = tk.Entry(panel, font=("Segoe UI", 9), relief="flat", readonlybackground="white", width=64,
                             fg="#1d4ed8" if name == "Address" else "#111827")
            entry.insert(0, value)
            entry.configure(state="readonly")
            entry.grid(row=row, column=1, sticky="w", pady=2)
        buttons = tk.Frame(self.body, bg=BG)
        buttons.pack(fill="x", padx=16, pady=12)
        opener = ttk.Button(buttons, style="Dl.TButton", text="Open", command=lambda: (open_file(job.destination), self.close()))
        opener.pack(side="left")
        ttk.Button(buttons, style="Dl.TButton", text="Open folder", command=lambda: (show_in_folder(job.destination), self.close())).pack(side="left", padx=6)
        ttk.Button(buttons, style="Dl.TButton", text="Close", command=self.close).pack(side="right")
        self.quiet = tk.BooleanVar(value=False)
        tk.Checkbutton(self.body, text="Don't show this dialog again", variable=self.quiet, bg=BG, activebackground=BG,
                       font=("Segoe UI", 9), command=self.toggle_quiet).pack(anchor="w", padx=14, pady=(0, 10))
        opener.focus_set()
        self.win.attributes("-topmost", True)
        self.win.after(4000, lambda: self.win.winfo_exists() and self.win.attributes("-topmost", False))

    def toggle_quiet(self):
        self.app.settings["complete_dialog"] = not self.quiet.get()
        self.app.save()

    def refresh(self):
        if not self.alive():
            return False
        item = self.item
        if not item:
            self.close()
            return False
        state = "complete" if item["job"].status == "Complete" else "progress"
        if state != self.state:
            self.state = state
            self.build_complete() if state == "complete" else self.build_progress()
        if state == "progress":
            self.update_progress()
        return True
