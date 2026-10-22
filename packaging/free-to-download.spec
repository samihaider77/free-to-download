# PyInstaller recipe for the Windows build.
#   python -m PyInstaller --noconfirm --distpath dist --workpath build packaging/free-to-download.spec
# Produces dist/Free-to-Download/ (Free-to-Download.exe beside its _internal folder).
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
ytdlp = collect_all("yt_dlp")
ffmpeg = collect_all("imageio_ffmpeg")  # ships the FFmpeg binary used to merge audio and video

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT / "app")],
    binaries=ytdlp[1] + ffmpeg[1],
    datas=ytdlp[0] + ffmpeg[0] + [(str(ROOT / "packaging" / "icon.ico"), ".")],
    hiddenimports=ytdlp[2] + ffmpeg[2],
    runtime_hooks=[str(ROOT / "app" / "runtime_tcl.py")],
    excludes=["test_bridge", "test_downloader", "test_media", "test_packaged_media", "test_ui"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Free-to-Download",
    icon=str(ROOT / "packaging" / "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="Free-to-Download")
