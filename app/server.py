from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from .downloader import list_video_formats
from .task_manager import create_task, get_task, start_download_task

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
DOWNLOADS_DIR = BASE_DIR / "downloads"


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

        if not url:
            return jsonify({"error": "The url field is required"}), 400

        task_id = create_task(url=url, format_id=format_id)
        start_download_task(task_id=task_id, url=url, download_dir=DOWNLOADS_DIR, format_id=format_id)

        return jsonify({"task_id": task_id, "status": "queued", "format_id": format_id}), 202

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
