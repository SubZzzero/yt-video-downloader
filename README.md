# yt-dlp YouTube Video Downloader Web UI (Flask)

A simple YouTube video downloader web UI built with Flask using yt-dlp.  
Download YouTube videos in your browser by URL with selectable quality and best available audio — no transcoding required.

![Main page](img/main.png)

## Features
- Web page with a URL field and download button
- Dynamic quality selection by available resolutions (e.g. 360p, 720p, 1080p)
- Download of selected video quality with best available audio track
- Age-restricted video downloads via browser cookies when already logged in with an account that has access; tested only on Linux
- Playlist support: full videos or audio-only MP3 downloads
- Audio-only MP3 download with selectable bitrate `192` or `320 kbps`
- API for starting downloads and checking status
- List of downloaded files from the `downloads/` folder
- Single local Flask process

## Requirements
- Python 3.10+ is required (must be available in PATH)
- `pip` for installing dependencies
- `ffmpeg` for best quality video+audio merge
- Optional but recommended for YouTube challenge solving: Node.js, Deno, Bun, or QuickJS. Node.js is the most common option.

If you do not have these installed yet:

Linux (APT):

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git ffmpeg nodejs
```

macOS (Homebrew):

```bash
brew install python git ffmpeg node
```

Windows (PowerShell):

```powershell
winget install --id Python.Python.3.12 -e
winget install --id Git.Git -e
winget install --id Gyan.FFmpeg -e
winget install --id OpenJS.NodeJS.LTS -e
```

Make sure Python is added to `PATH` during installation.

## Quick Start

1. Clone the repository.

2. Create virtual environment and install dependencies.

Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If YouTube downloads start failing after previously working, update the pinned extractor dependency first:

```bash
python -m pip install -U -r requirements.txt
python -m yt_dlp --version
```

3. Install ffmpeg.

Linux (APT):

```bash
sudo apt update
sudo apt install -y ffmpeg
```

Windows (winget):

```powershell
winget install --id Gyan.FFmpeg -e
```

4. Run the app.

Linux/macOS:
```bash
python3 run.py
```

Windows PowerShell:
```powershell
py run.py
```

5. Open in browser:

```
http://127.0.0.1:5000
```

## Download Flow
1. Paste a video URL.
2. Click **Load qualities** to fetch available formats.
3. Select quality (`###p`) from the dropdown. The app auto-selects a recommended MP4-safe option when available; higher VP9/AV1/WebM qualities may save as MKV to avoid slow video transcoding.
4. Click **Download** and track status.

## YouTube 403 / Bot Check / PO Token

YouTube can require client challenges or PO Tokens for some requests. This depends on IP address, account, region, selected client, and YouTube rollout state, so a URL may work one day and fail later without an app change.

First steps:

```bash
python -m pip install -U -r requirements.txt
python -m yt_dlp --version
```

Keep a JavaScript runtime available for `yt-dlp` challenge solving. Node.js is the common choice, but Deno, Bun, or QuickJS can also work when installed.

If errors mention `403`, bot checks, `PO Token`, `gvs`, `nsig`, or signature failures after updating, follow the upstream `yt-dlp` PO Token guidance and consider installing the optional `bgutil-ytdlp-pot-provider`. This project does not install that provider by default because it adds an extra moving part outside the local MVP.

Cookies are only for content that requires an account, such as age-restricted or private videos. Cookies do not solve every 403/PO-token case, can rotate or be locked by the browser, and may increase account throttling risk when overused. Prefer an exported cookies file when browser-cookie auto-detection is unreliable.

## Age-Restricted Videos

The app does not bypass age checks. For videos that require login or age verification, it first tries the normal public download path. If YouTube asks for login or age verification, the backend automatically tries cookies from local browser profiles in this order: Firefox, Chrome, Chromium, Edge, Brave, Vivaldi, Opera.

This behavior has only been tested on Linux. Compatibility with macOS and Windows is currently unknown and depends on whether `yt-dlp` can read cookies from a browser where you are already logged in with an account that has access.

Normal startup does not change:

Linux/macOS:

```bash
python3 run.py
```

Windows PowerShell:

```powershell
py run.py
```

If auto-detection does not find the right browser profile, choose one manually before starting the app.

Linux/macOS:

```bash
export YTDLP_COOKIES_FROM_BROWSER=firefox
python3 run.py
```

Windows PowerShell:

```powershell
$env:YTDLP_COOKIES_FROM_BROWSER = "chrome"
py run.py
```

Option 1: exported cookies file in Netscape format:

Linux/macOS:

```bash
export YTDLP_COOKIES_FILE=/home/user/private/cookies.txt
python3 run.py
```

Windows PowerShell:

```powershell
$env:YTDLP_COOKIES_FILE = "C:\Users\User\private\cookies.txt"
py run.py
```

You can also include a browser profile name:

```bash
export YTDLP_COOKIES_FROM_BROWSER=firefox:default
python3 run.py
```

If both variables are set, `YTDLP_COOKIES_FILE` is used. Do not commit cookies files or share them; they provide access to your logged-in browser session.
