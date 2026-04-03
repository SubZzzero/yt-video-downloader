# ytdownloader

A local web tool to download videos by URL using `yt-dlp` with selectable quality and best available audio.

## MVP Features
- Web page with URL input and download button
- Dynamic quality selection by available resolutions (e.g. 360p, 720p, 1080p)
- Download of selected video quality with best available audio track
- API for starting downloads and checking status
- List of downloaded files from the `downloads/` folder
- Single local Flask process

## Quick Start
1. Clone the repository.
2. Install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Install ffmpeg (required for best quality video+audio merge):

   ```bash
   sudo apt update
   sudo apt install -y ffmpeg
   ```

4. Run the app:

   ```bash
   python3 run.py
   ```

5. Open in browser:

   ```
   http://127.0.0.1:5000
   ```

## Download Flow
1. Paste a video URL.
2. Click **Load qualities** to fetch available formats.
3. Select quality (`###p`) from the dropdown.
4. Click **Download** and track status.

## Legacy Script
`main.py` is kept as a CLI wrapper and now also performs download-only behavior (no transcoding).
