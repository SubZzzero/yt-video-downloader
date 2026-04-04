from __future__ import annotations

from pathlib import Path
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError


def list_video_formats(video_url: str) -> dict[str, Any]:
    """Return downloadable quality options grouped by resolution height."""
    ydl_opts: dict[str, Any] = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    raw_formats = info.get("formats") or []

    def collect_candidates(video_only: bool) -> dict[int, tuple[tuple[float, float, float], dict[str, Any]]]:
        selected_by_height: dict[int, tuple[tuple[float, float, float], dict[str, Any]]] = {}

        for item in raw_formats:
            format_id = str(item.get("format_id") or "").strip()
            if not format_id:
                continue

            vcodec = str(item.get("vcodec") or "none")
            acodec = str(item.get("acodec") or "none")
            if vcodec == "none":
                continue
            if video_only and acodec != "none":
                continue

            height_raw = item.get("height")
            if not isinstance(height_raw, (int, float)) or height_raw <= 0:
                continue
            height = int(height_raw)

            fps_raw = item.get("fps")
            fps = int(fps_raw) if isinstance(fps_raw, (int, float)) and fps_raw > 0 else None

            tbr_raw = item.get("tbr")
            tbr = float(tbr_raw) if isinstance(tbr_raw, (int, float)) else 0.0
            filesize = item.get("filesize") or item.get("filesize_approx")
            filesize_int = int(filesize) if isinstance(filesize, (int, float)) else None
            note = str(item.get("format_note") or item.get("format") or "").strip()

            normalized = {
                "format_id": format_id,
                "quality": f"{height}p",
                "height": height,
                "resolution": f"{height}p",
                "ext": str(item.get("ext") or "").strip(),
                "fps": fps,
                "filesize": filesize_int,
                "note": note,
                "has_audio": acodec != "none",
            }

            rank = (
                float(fps or 0),
                tbr,
                float(filesize_int or 0),
            )
            previous = selected_by_height.get(height)
            if not previous or rank > previous[0]:
                selected_by_height[height] = (rank, normalized)

        return selected_by_height

    selected_by_height = collect_candidates(video_only=True)
    if not selected_by_height:
        selected_by_height = collect_candidates(video_only=False)

    ranked_formats = [
        item[1]
        for _, item in sorted(
            selected_by_height.items(),
            key=lambda pair: pair[0],
            reverse=True,
        )
    ]

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "formats": ranked_formats,
    }


def download_video(video_url: str, download_dir: Path, format_id: str | None = None) -> dict[str, Any]:
    """Download a single video and prefer selected quality + best available audio."""
    download_dir.mkdir(parents=True, exist_ok=True)

    selected_format = (
        f"{format_id}+bestaudio/{format_id}/best"
        if format_id
        else "bestvideo+bestaudio/best"
    )

    ydl_opts: dict[str, Any] = {
        "outtmpl": str(download_dir / "%(title).150B [%(id)s].%(ext)s"),
        "format": selected_format,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            prepared_name = ydl.prepare_filename(info)
    except DownloadError as exc:
        message = str(exc)
        if "ffmpeg" in message.lower():
            raise RuntimeError("FFmpeg is required for selected quality. Install ffmpeg and retry.") from exc
        raise RuntimeError(message) from exc

    file_path = Path(prepared_name)

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "file_path": str(file_path.resolve()),
        "file_name": file_path.name,
        "format_id": info.get("format_id") or format_id,
    }
