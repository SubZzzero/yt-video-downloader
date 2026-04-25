from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from .downloader import download_video

_tasks: dict[str, dict[str, Any]] = {}
_lock = Lock()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def create_task(
    url: str,
    format_id: str | None = None,
    audio_only: bool = False,
    audio_bitrate_kbps: int | None = None,
) -> str:
    task_id = str(uuid4())
    with _lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "url": url,
            "format_id": format_id,
            "audio_only": audio_only,
            "audio_bitrate_kbps": audio_bitrate_kbps,
            "status": "queued",
            "error": None,
            "result": None,
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    return task_id


def _set_task(task_id: str, **updates: Any) -> None:
    with _lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = _utc_now()


def get_task(task_id: str) -> dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task else None


def start_download_task(
    task_id: str,
    url: str,
    download_dir: Path,
    format_id: str | None = None,
    audio_only: bool = False,
    audio_bitrate_kbps: int | None = None,
) -> None:
    def _worker() -> None:
        _set_task(task_id, status="downloading")
        try:
            result = download_video(
                video_url=url,
                download_dir=download_dir,
                format_id=format_id,
                audio_only=audio_only,
                audio_bitrate_kbps=audio_bitrate_kbps,
            )
            _set_task(task_id, status="completed", result=result, error=None)
        except Exception as exc:  # noqa: BLE001
            _set_task(task_id, status="failed", error=str(exc), result=None)

    Thread(target=_worker, daemon=True).start()
