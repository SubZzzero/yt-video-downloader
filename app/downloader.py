from __future__ import annotations

from pathlib import Path
from typing import Any

import yt_dlp


def download_video(video_url: str, download_dir: Path) -> dict[str, Any]:
    """Download a single video with yt-dlp without transcoding."""
    download_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict[str, Any] = {
        "outtmpl": str(download_dir / "%(title).150B [%(id)s].%(ext)s"),
        "format": "best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        prepared_name = ydl.prepare_filename(info)

    file_path = Path(prepared_name)

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "file_path": str(file_path.resolve()),
        "file_name": file_path.name,
    }
