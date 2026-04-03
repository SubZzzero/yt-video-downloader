# ytdownloader

A local web tool to download videos by URL using `yt-dlp` without transcoding.

## MVP Features
- Web page with URL input and download button
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

3. Run the app:

   ```bash
   python3 run.py
   ```

4. Open in browser:

   ```
   http://127.0.0.1:5000
   ```

## Legacy Script
`main.py` is kept as a CLI wrapper and now also performs download-only behavior (no transcoding).
