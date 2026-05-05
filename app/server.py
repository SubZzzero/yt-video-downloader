from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .downloader import list_video_formats
from .task_manager import create_task, get_task, start_download_task, start_playlist_download_task

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DOWNLOADS_DIR = BASE_DIR / "downloads"


def _parse_audio_only(raw_value: object) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _parse_audio_bitrate(raw_value: object) -> int | None:
    if raw_value in (None, ""):
        return None
    try:
        return int(str(raw_value).strip())
    except (TypeError, ValueError):
        raise ValueError("audio_bitrate_kbps must be an integer (192 or 320)")


def _list_downloaded_files() -> list[dict[str, object]]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, object]] = []

    for file_path in sorted(DOWNLOADS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not file_path.is_file():
            continue
        stat = file_path.stat()
        items.append(
            {
                "name": file_path.name,
                "path": str(file_path.resolve()),
                "size_bytes": stat.st_size,
                "updated_at": stat.st_mtime,
            }
        )

    return items


def _validate_audio_bitrate(audio_only: bool, audio_bitrate_kbps: int | None) -> int | None:
    if audio_only and audio_bitrate_kbps not in (None, 192, 320):
        raise ValueError("audio_bitrate_kbps must be 192 or 320 for audio-only downloads")

    if not audio_only:
        return None

    return audio_bitrate_kbps


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="/web")

    @app.get("/")
    def index() -> object:
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/health")
    def health() -> object:
        return jsonify({"status": "ok"})

    @app.post("/api/download")
    def api_download() -> object:
        payload = request.get_json(silent=True) or {}
        url = str(payload.get("url", "")).strip()
        format_id_raw = str(payload.get("format_id", "")).strip()
        format_id = format_id_raw or None
        audio_only = _parse_audio_only(payload.get("audio_only"))

        try:
            audio_bitrate_kbps = _parse_audio_bitrate(payload.get("audio_bitrate_kbps"))
            audio_bitrate_kbps = _validate_audio_bitrate(audio_only=audio_only, audio_bitrate_kbps=audio_bitrate_kbps)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not url:
            return jsonify({"error": "The url field is required"}), 400

        task_id = create_task(
            url=url,
            format_id=format_id,
            audio_only=audio_only,
            audio_bitrate_kbps=audio_bitrate_kbps,
        )
        start_download_task(
            task_id=task_id,
            url=url,
            download_dir=DOWNLOADS_DIR,
            format_id=format_id,
            audio_only=audio_only,
            audio_bitrate_kbps=audio_bitrate_kbps,
        )

        return jsonify(
            {
                "task_id": task_id,
                "status": "queued",
                "format_id": format_id,
                "audio_only": audio_only,
                "audio_bitrate_kbps": audio_bitrate_kbps,
                "audio_processing": "mp3_extract" if audio_only else "premiere_safe_aac_48k_stereo",
            }
        ), 202

    @app.post("/api/playlist-download")
    def api_playlist_download() -> object:
        payload = request.get_json(silent=True) or {}
        url = str(payload.get("url", "")).strip()
        audio_only = _parse_audio_only(payload.get("audio_only"))

        try:
            audio_bitrate_kbps = _parse_audio_bitrate(payload.get("audio_bitrate_kbps"))
            audio_bitrate_kbps = _validate_audio_bitrate(audio_only=audio_only, audio_bitrate_kbps=audio_bitrate_kbps)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        if not url:
            return jsonify({"error": "The url field is required"}), 400

        task_id = create_task(
            url=url,
            audio_only=audio_only,
            audio_bitrate_kbps=audio_bitrate_kbps,
            task_kind="playlist",
        )
        start_playlist_download_task(
            task_id=task_id,
            url=url,
            download_dir=DOWNLOADS_DIR,
            audio_only=audio_only,
            audio_bitrate_kbps=audio_bitrate_kbps,
        )

        return jsonify(
            {
                "task_id": task_id,
                "task_kind": "playlist",
                "status": "queued",
                "audio_only": audio_only,
                "audio_bitrate_kbps": audio_bitrate_kbps,
                "message": "Playlist request accepted. Preparing download...",
            }
        ), 202

    @app.get("/api/formats")
    def api_formats() -> object:
        url = str(request.args.get("url", "")).strip()
        if not url:
            return jsonify({"error": "The url query parameter is required"}), 400

        try:
            formats_payload = list_video_formats(video_url=url)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"Failed to fetch formats: {exc}"}), 400

        return jsonify(formats_payload)

    @app.get("/api/status/<task_id>")
    def api_status(task_id: str) -> object:
        task = get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(task)

    @app.get("/api/files")
    def api_files() -> object:
        return jsonify({"files": _list_downloaded_files()})

    @app.get("/web/<path:asset_path>")
    def web_assets(asset_path: str) -> object:
        return send_from_directory(WEB_DIR, asset_path)

    return app
