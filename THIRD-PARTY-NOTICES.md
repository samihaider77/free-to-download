# Third-party notices

Free-to-Download's own source code is licensed under the [MIT License](LICENSE).
The Windows builds (installer and portable ZIP) also contain the following third-party software, each under its own licence.
Full licence texts are in [`THIRD-PARTY-LICENSES/`](THIRD-PARTY-LICENSES) and are installed alongside the app.

| Component | Used for | Licence |
|---|---|---|
| [FFmpeg](https://ffmpeg.org) 7.1 ("essentials" build by [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), shipped via imageio-ffmpeg) | Combining video and audio, converting to MP3 | GNU GPL version 3 or later |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Finding and downloading videos and streams | The Unlicense (public domain) |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Packaging the FFmpeg binary | BSD 2-Clause |
| [Python](https://www.python.org) 3.12 runtime | Running the app | Python Software Foundation License |
| [Tcl/Tk](https://www.tcl-lang.org) | The desktop user interface (via tkinter) | Tcl/Tk licence (BSD-style) |
| [PyInstaller](https://pyinstaller.org) bootloader | Starting the packaged app | GPL 2.0 with a bootloader exception that permits distribution with any licence |

## FFmpeg source code

FFmpeg is distributed as an unmodified, separate executable (`ffmpeg-win-x86_64-v7.1.exe` inside the app's `_internal` folder) and is run as its own program.
Its complete corresponding source code is available from:

- FFmpeg 7.1 source release: https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz (git tag `n7.1`: https://github.com/FFmpeg/FFmpeg/tree/n7.1)
- Build configuration and the sources of the libraries included in the gyan.dev "essentials" build: https://www.gyan.dev/ffmpeg/builds/

If either link stops working, open an issue in this repository and the maintainers will provide the corresponding source for the FFmpeg binary included in any release, for at least three years after that release.
