from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

import yt_dlp
from yt_dlp.utils import DownloadError


ALLOWED_AUDIO_BITRATES = {192, 320}
PLAYLIST_VIDEO_FORMAT = "bestvideo*[height<=1080]+bestaudio/best[height<=1080]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"
ProgressCallback = Callable[[dict[str, Any]], None]
VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv"}


def _normalize_audio_bitrate(audio_bitrate_kbps: int | None) -> int:
    if audio_bitrate_kbps is None:
        return 320

    bitrate = int(audio_bitrate_kbps)
    if bitrate not in ALLOWED_AUDIO_BITRATES:
        raise RuntimeError("Playlist audio bitrate must be 192 or 320 kbps")
    return bitrate


def _apply_premiere_safe_audio(file_path: Path) -> Path:
    final_path = file_path.with_suffix(".mp4")
    temp_path = final_path.with_name(f"{final_path.stem}.premiere_safe.mp4")

    ffmpeg_command = [
        "ffmpeg",
        "-y",
        "-i",
        str(file_path),
        "-map",
        "0:v:0?",
        "-map",
        "0:a:0?",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-profile:a",
        "aac_low",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(temp_path),
    ]

    try:
        result = subprocess.run(
            ffmpeg_command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is required for playlist video post-processing") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        details = stderr.splitlines()[-1] if stderr else "unknown ffmpeg error"
        raise RuntimeError(f"Failed to normalize playlist video audio: {details}")

    if final_path.exists() and final_path != file_path:
        final_path.unlink()
    temp_path.replace(final_path)

    if file_path.exists() and file_path != final_path:
        file_path.unlink()

    return final_path


def _collect_playlist_metadata(playlist_url: str) -> dict[str, Any]:
    ydl_opts: dict[str, Any] = {
        "extract_flat": "in_playlist",
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(playlist_url, download=False)

    entries = [entry for entry in (info.get("entries") or []) if entry]
    if info.get("_type") != "playlist" or not entries:
        raise RuntimeError("Playlist mode requires a playlist URL with at least one downloadable entry")

    return {
        "playlist_title": str(info.get("title") or "Untitled playlist").strip() or "Untitled playlist",
        "playlist_url": info.get("webpage_url") or playlist_url,
        "items_total": len(entries),
    }


def _resolve_unique_target(target_dir: Path, file_name: str) -> Path:
    candidate = target_dir / file_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        alternate = target_dir / f"{stem} ({counter}){suffix}"
        if not alternate.exists():
            return alternate
        counter += 1


def _emit_progress(progress_callback: ProgressCallback | None, **payload: Any) -> None:
    if progress_callback:
        progress_callback(payload)


def _is_final_playlist_file(file_path: Path, audio_only: bool) -> bool:
    suffix = file_path.suffix.lower()
    if suffix in {".part", ".ytdl", ".temp"}:
        return False
    if audio_only:
        return suffix == ".mp3"
    return suffix in VIDEO_SUFFIXES


def download_playlist(
    playlist_url: str,
    download_dir: Path,
    task_id: str,
    audio_only: bool = False,
    audio_bitrate_kbps: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    download_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = download_dir / f".playlist_{task_id}"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    try:
        metadata = _collect_playlist_metadata(playlist_url)
        bitrate = _normalize_audio_bitrate(audio_bitrate_kbps) if audio_only else None
        tracker = {
            "playlist_title": metadata["playlist_title"],
            "items_total": metadata["items_total"],
            "items_completed": 0,
            "completed_indices": set(),
        }

        _emit_progress(
            progress_callback,
            task_kind="playlist",
            status="downloading",
            audio_only=audio_only,
            playlist_title=metadata["playlist_title"],
            items_total=metadata["items_total"],
            items_completed=0,
            message=f"Preparing playlist download: {metadata['playlist_title']}",
        )

        def progress_hook(update: dict[str, Any]) -> None:
            info = update.get("info_dict") or {}
            playlist_index_raw = info.get("playlist_index")
            playlist_index = int(playlist_index_raw) if isinstance(playlist_index_raw, (int, float)) else None
            playlist_count_raw = info.get("n_entries") or info.get("playlist_count")
            items_total = int(playlist_count_raw) if isinstance(playlist_count_raw, (int, float)) else tracker["items_total"]
            item_title = str(info.get("title") or info.get("id") or "playlist entry").strip() or "playlist entry"
            status = str(update.get("status") or "").lower()

            if status == "finished" and playlist_index is not None and playlist_index not in tracker["completed_indices"]:
                tracker["completed_indices"].add(playlist_index)
                tracker["items_completed"] = len(tracker["completed_indices"])

            if status == "downloading":
                message = (
                    f"Downloading playlist item {playlist_index}/{items_total}: {item_title}"
                    if playlist_index is not None
                    else f"Downloading playlist item: {item_title}"
                )
            elif status == "finished":
                message = (
                    f"Processing playlist item {playlist_index}/{items_total}: {item_title}"
                    if playlist_index is not None
                    else f"Processing playlist item: {item_title}"
                )
            else:
                return

            _emit_progress(
                progress_callback,
                task_kind="playlist",
                status="downloading",
                audio_only=audio_only,
                playlist_title=tracker["playlist_title"],
                items_total=items_total,
                items_completed=tracker["items_completed"],
                current_item={
                    "index": playlist_index,
                    "title": item_title,
                },
                message=message,
            )

        ydl_opts: dict[str, Any] = {
            "outtmpl": str(staging_dir / "%(playlist_index,0>3)s - %(title).150B [%(id)s].%(ext)s"),
            "noplaylist": False,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "restrictfilenames": False,
            "progress_hooks": [progress_hook],
        }

        if audio_only:
            ydl_opts["format"] = "bestaudio/best"
            ydl_opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(bitrate),
                }
            ]
        else:
            # Prefer 1080p when available, otherwise fall back to the best lower quality.
            ydl_opts["format"] = PLAYLIST_VIDEO_FORMAT
            ydl_opts["merge_output_format"] = "mp4"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(playlist_url, download=True)
        except DownloadError as exc:
            message = str(exc)
            if "ffmpeg" in message.lower():
                if audio_only:
                    raise RuntimeError("FFmpeg is required for playlist MP3 conversion. Install ffmpeg and retry.") from exc
                raise RuntimeError("FFmpeg is required for playlist video merging. Install ffmpeg and retry.") from exc
            raise RuntimeError(f"Playlist download failed: {message}") from exc

        staged_files = sorted(
            path
            for path in staging_dir.rglob("*")
            if path.is_file() and _is_final_playlist_file(path, audio_only=audio_only)
        )
        finalized_files: list[dict[str, Any]] = []
        processing_errors: list[str] = []
        for staged_file in staged_files:
            try:
                processed_file = staged_file
                if not audio_only:
                    processed_file = _apply_premiere_safe_audio(staged_file)

                target_path = _resolve_unique_target(download_dir, processed_file.name)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(processed_file), str(target_path))
                finalized_files.append(
                    {
                        "file_name": target_path.name,
                        "file_path": str(target_path.resolve()),
                    }
                )
            except RuntimeError as exc:
                processing_errors.append(f"{staged_file.name}: {exc}")

        downloaded_count = len(finalized_files)
        failed_count = max(metadata["items_total"] - downloaded_count, 0)
        if downloaded_count == 0:
            if processing_errors:
                raise RuntimeError(f"Playlist download failed. {processing_errors[0]}")
            raise RuntimeError("Playlist download failed. No items were saved.")

        warnings: list[str] = []
        if failed_count > 0:
            warnings.append(f"{failed_count} playlist item(s) could not be downloaded.")
        warnings.extend(processing_errors)

        return {
            "task_kind": "playlist",
            "playlist_title": metadata["playlist_title"],
            "playlist_url": metadata["playlist_url"],
            "audio_only": audio_only,
            "audio_bitrate_kbps": bitrate,
            "downloaded_count": downloaded_count,
            "failed_count": failed_count,
            "items_total": metadata["items_total"],
            "files": finalized_files,
            "warnings": warnings,
            "message": (
                f"Saved {downloaded_count} playlist item(s) from {metadata['playlist_title']}."
                if failed_count == 0
                else f"Saved {downloaded_count} playlist item(s) from {metadata['playlist_title']} with {failed_count} failure(s)."
            ),
        }
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
