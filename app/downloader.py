from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError


ALLOWED_AUDIO_BITRATES = {192, 320}
AUTO_COOKIE_BROWSERS = ("firefox", "chrome", "chromium", "edge", "brave", "vivaldi", "opera")
DOWNLOAD_TEMPLATE = "%(title).150B [%(id)s].%(ext)s"
TEMP_DOWNLOAD_DIR_NAME = ".tmp"
STALE_ARTIFACT_MAX_AGE_SECONDS = 24 * 60 * 60
TEMP_FILE_SUFFIXES = {".part", ".ytdl", ".temp"}
JS_RUNTIME_COMMANDS = {
    "deno": "deno",
    "node": "node",
    "bun": "bun",
    "quickjs": "qjs",
}
AGE_OR_LOGIN_HINT = (
    "This video requires age verification or login. Sign in with an account that has access "
    "in Firefox, Chrome, Chromium, Edge, Brave, Vivaldi, or Opera, or configure "
    "YTDLP_COOKIES_FILE or YTDLP_COOKIES_FROM_BROWSER manually."
)
YOUTUBE_CLIENT_TROUBLESHOOTING_HINT = (
    "YouTube rejected this request, commonly due to 403/bot-check/PO-token enforcement. "
    "Update yt-dlp, keep Node.js/Deno available for challenge solving, and if it repeats install "
    "the optional bgutil-ytdlp-pot-provider and configure yt-dlp for the mweb client. Use cookies "
    "only for content that actually requires an account."
)


def cleanup_stale_download_artifacts(download_dir: Path, max_age_seconds: int = STALE_ARTIFACT_MAX_AGE_SECONDS) -> None:
    """Remove old hidden yt-dlp staging artifacts without touching finished user files."""
    download_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = download_dir / TEMP_DOWNLOAD_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - max_age_seconds

    for item in sorted(temp_dir.rglob("*"), reverse=True):
        try:
            stat = item.stat()
        except OSError:
            continue
        if stat.st_mtime >= cutoff:
            continue
        if item.is_dir():
            shutil.rmtree(item, ignore_errors=True)
        elif item.is_file():
            item.unlink(missing_ok=True)

    for item in download_dir.iterdir():
        try:
            stat = item.stat()
        except OSError:
            continue

        if stat.st_mtime >= cutoff:
            continue

        if item.is_dir() and (item.name.startswith(".playlist_") or item.name == TEMP_DOWNLOAD_DIR_NAME):
            shutil.rmtree(item, ignore_errors=True)
            if item.name == TEMP_DOWNLOAD_DIR_NAME:
                item.mkdir(parents=True, exist_ok=True)
            continue

        if item.is_file() and item.suffix.lower() in TEMP_FILE_SUFFIXES:
            item.unlink(missing_ok=True)


def build_yt_dlp_download_options(download_dir: Path, *, template: str = DOWNLOAD_TEMPLATE) -> dict[str, Any]:
    """Return shared yt-dlp download options with isolated temp storage."""
    temp_dir = download_dir / TEMP_DOWNLOAD_DIR_NAME
    temp_dir.mkdir(parents=True, exist_ok=True)
    return {
        "paths": {"home": str(download_dir), "temp": str(temp_dir)},
        "outtmpl": template,
        "retries": 10,
        "fragment_retries": 10,
        "socket_timeout": 30,
        "continuedl": True,
        "restrictfilenames": False,
    }


def build_yt_dlp_cookie_options() -> dict[str, Any]:
    """Return explicit yt-dlp cookie settings from local environment variables."""
    cookies_file = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
    if cookies_file:
        cookie_path = Path(cookies_file).expanduser()
        if not cookie_path.is_file() or not os.access(cookie_path, os.R_OK):
            raise RuntimeError("Configured YTDLP_COOKIES_FILE does not point to a readable cookies file.")
        return {"cookiefile": str(cookie_path)}

    browser_value = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if not browser_value:
        return {}

    browser_parts = [part.strip() for part in browser_value.split(":", 1)]
    browser = browser_parts[0]
    if not browser:
        raise RuntimeError("Configured YTDLP_COOKIES_FROM_BROWSER must include a browser name.")

    if len(browser_parts) == 2 and browser_parts[1]:
        return {"cookiesfrombrowser": (browser, browser_parts[1])}

    return {"cookiesfrombrowser": (browser,)}


def build_yt_dlp_runtime_options() -> dict[str, Any]:
    """Enable installed JavaScript runtimes so YouTube challenge solving can work."""
    runtimes = {name: {} for name, command in JS_RUNTIME_COMMANDS.items() if shutil.which(command)}
    if not runtimes:
        return {}

    return {
        "js_runtimes": runtimes,
        "remote_components": ["ejs:github"],
    }


def is_age_or_login_error(message: str) -> bool:
    """Return whether yt-dlp failed because authenticated access is required."""
    normalized = message.lower()
    age_or_login_markers = (
        "age-restricted",
        "age restricted",
        "age verification",
        "confirm your age",
        "sign in to confirm your age",
        "sign in to confirm",
        "login required",
        "please log in",
        "private video",
    )
    return any(marker in normalized for marker in age_or_login_markers)


def is_requested_format_error(message: str) -> bool:
    normalized = message.lower()
    return "requested format" in normalized and "not available" in normalized


def is_browser_cookie_error(message: str) -> bool:
    normalized = message.lower()
    cookie_error_markers = (
        "could not find",
        "cookies database",
        "cookie database",
        "secretstorage",
        "keyring",
        "browser profile",
        "profile directory",
        "permission denied",
        "unsupported browser",
    )
    return "cookie" in normalized or any(marker in normalized for marker in cookie_error_markers)


def is_youtube_client_error(message: str) -> bool:
    normalized = message.lower()
    markers = (
        "http error 403",
        "403 forbidden",
        "sign in to confirm you're not a bot",
        "not a bot",
        "po token",
        "pot token",
        "gvs",
        "nsig",
        "signature",
        "unable to download video data",
        "this content isn't available, try again later",
    )
    return any(marker in normalized for marker in markers)


def format_yt_dlp_error(message: str) -> str:
    """Convert common yt-dlp failures into concise user-facing messages."""
    normalized = message.lower()
    if is_age_or_login_error(message):
        return AGE_OR_LOGIN_HINT

    if is_youtube_client_error(message):
        return YOUTUBE_CLIENT_TROUBLESHOOTING_HINT

    if "cookies" in normalized and "browser" in normalized:
        return (
            f"{message}. Check YTDLP_COOKIES_FROM_BROWSER or use YTDLP_COOKIES_FILE instead. "
            "Browser cookies can rotate or be locked by a running browser; an exported cookies file is often more stable."
        )

    return message


def _safe_error_detail(error: Exception | str) -> str:
    """Return a short diagnostic line without exposing full local paths."""
    message = str(error).strip()
    if not message:
        return "no details"

    home = str(Path.home())
    if home and home in message:
        message = message.replace(home, "~")

    message = re.sub(r"\x1b\[[0-9;]*m", "", message)

    lines = [line.strip() for line in message.splitlines() if line.strip()]
    detail = lines[-1] if lines else message
    return detail[:220]


def _age_or_login_hint_with_attempts(attempt_errors: list[tuple[str, str]]) -> str:
    if not attempt_errors:
        return AGE_OR_LOGIN_HINT

    attempts = "; ".join(f"{browser}: {detail}" for browser, detail in attempt_errors)
    return (
        f"{AGE_OR_LOGIN_HINT} Automatic browser cookie attempts failed: {attempts}. "
        "If you are logged in, close the browser completely and retry, or set "
        "YTDLP_COOKIES_FROM_BROWSER to the exact browser/profile."
    )


def extract_info_with_cookie_fallback(
    video_url: str,
    ydl_opts: dict[str, Any],
    download: bool,
) -> tuple[dict[str, Any], str | None]:
    """Extract info, retrying age/login failures with local browser cookies."""
    ydl_opts = {**build_yt_dlp_runtime_options(), **ydl_opts}
    explicit_cookie_opts = build_yt_dlp_cookie_options()
    if explicit_cookie_opts:
        attempt_opts = {**ydl_opts, **explicit_cookie_opts}
        try:
            with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                info = ydl.extract_info(video_url, download=download)
                prepared_name = ydl.prepare_filename(info) if download else None
        except DownloadError as exc:
            message = str(exc)
            if "ffmpeg" in message.lower():
                raise
            raise RuntimeError(format_yt_dlp_error(message)) from exc
        return info, prepared_name

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=download)
            prepared_name = ydl.prepare_filename(info) if download else None
        return info, prepared_name
    except DownloadError as exc:
        first_error = str(exc)
        if "ffmpeg" in first_error.lower():
            raise
        if not is_age_or_login_error(first_error):
            raise RuntimeError(format_yt_dlp_error(first_error)) from exc

    attempt_errors: list[tuple[str, str]] = []
    for browser in AUTO_COOKIE_BROWSERS:
        attempt_opts = {**ydl_opts, "cookiesfrombrowser": (browser,)}
        try:
            with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                info = ydl.extract_info(video_url, download=download)
                prepared_name = ydl.prepare_filename(info) if download else None
            return info, prepared_name
        except DownloadError as exc:
            message = str(exc)
            if "ffmpeg" in message.lower():
                raise
            if is_age_or_login_error(message) or is_browser_cookie_error(message):
                attempt_errors.append((browser, _safe_error_detail(exc)))
                continue
            raise RuntimeError(format_yt_dlp_error(message)) from exc
        except (OSError, RuntimeError, ValueError) as exc:
            attempt_errors.append((browser, _safe_error_detail(exc)))
            continue

    raise RuntimeError(_age_or_login_hint_with_attempts(attempt_errors))


def list_video_formats(video_url: str) -> dict[str, Any]:
    """Return downloadable quality options grouped by resolution height."""
    ydl_opts: dict[str, Any] = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "simulate": "list_only",
        "skip_download": True,
    }
    info, _ = extract_info_with_cookie_fallback(video_url=video_url, ydl_opts=ydl_opts, download=False)

    raw_formats = info.get("formats") or []
    if not raw_formats:
        raise RuntimeError("No downloadable formats were returned for this video, even after authentication.")

    def is_mp4_safe_format(item: dict[str, Any], ext: str, vcodec: str, acodec: str) -> bool:
        return (
            ext == "mp4"
            and (vcodec.startswith("avc1") or vcodec.startswith("h264"))
            and (acodec == "none" or acodec.startswith("mp4a") or acodec.startswith("aac"))
        )

    def collect_candidates(video_only: bool) -> dict[int, tuple[tuple[float, float, float, float], dict[str, Any]]]:
        selected_by_height: dict[int, tuple[tuple[float, float, float, float], dict[str, Any]]] = {}

        for item in raw_formats:
            format_id = str(item.get("format_id") or "").strip()
            if not format_id:
                continue

            vcodec = str(item.get("vcodec") or "none").lower()
            acodec = str(item.get("acodec") or "none").lower()
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

            ext = str(item.get("ext") or "").strip().lower()
            container = str(item.get("container") or ext).strip().lower()
            mp4_safe = is_mp4_safe_format(item, ext=ext, vcodec=vcodec, acodec=acodec)
            has_audio = acodec != "none"
            normalized = {
                "format_id": format_id,
                "quality": f"{height}p",
                "height": height,
                "resolution": f"{height}p",
                "ext": ext,
                "fps": fps,
                "filesize": filesize_int,
                "note": note,
                "has_audio": has_audio,
                "vcodec": vcodec,
                "acodec": acodec,
                "container": container,
                "mp4_safe": mp4_safe,
                "needs_merge": not has_audio,
                "compatibility_note": "MP4-safe" if mp4_safe else "may save as MKV",
                "recommended": False,
            }

            rank = (
                1.0 if mp4_safe else 0.0,
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

    recommended = next((item for item in ranked_formats if item["mp4_safe"]), ranked_formats[0] if ranked_formats else None)
    if recommended:
        recommended["recommended"] = True

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "formats": ranked_formats,
    }


def _resolve_downloaded_file(info: dict[str, Any], prepared_name: str, download_dir: Path) -> Path:
    """Resolve the final downloaded file path produced by yt-dlp/ffmpeg."""
    direct_candidates = [
        info.get("_filename"),
        info.get("filepath"),
        prepared_name,
    ]

    for candidate in direct_candidates:
        if not candidate:
            continue
        candidate_path = Path(str(candidate))
        if candidate_path.exists():
            return candidate_path
        if not candidate_path.is_absolute():
            download_candidate = download_dir / candidate_path
            if download_candidate.exists():
                return download_candidate

    prepared_path = Path(prepared_name)
    ext = str(info.get("ext") or "").strip()
    if ext:
        with_info_ext = prepared_path.with_suffix(f".{ext}")
        if with_info_ext.exists():
            return with_info_ext

    files = [item for item in download_dir.iterdir() if item.is_file() and item.suffix.lower() not in TEMP_FILE_SUFFIXES]
    video_id = str(info.get("id") or "").strip()
    if video_id:
        by_id = [item for item in files if f"[{video_id}]" in item.name]
        if by_id:
            return sorted(by_id, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    raise RuntimeError("Downloaded file was not found after yt-dlp completed")


def _probe_video_codec(file_path: Path) -> str | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None
    codec = (result.stdout or "").splitlines()[0].strip().lower() if result.stdout else ""
    return codec or None


def _is_mp4_copy_compatible_file(file_path: Path) -> bool:
    codec = _probe_video_codec(file_path)
    return codec in {"h264"}


def _apply_premiere_safe_audio(file_path: Path) -> dict[str, Any]:
    """Normalize audio without transcoding video; use MP4 only when stream copy is safe."""
    mp4_compatible = _is_mp4_copy_compatible_file(file_path)
    final_suffix = ".mp4" if mp4_compatible else ".mkv"
    final_path = file_path.with_suffix(final_suffix)
    temp_path = final_path.with_name(f"{final_path.stem}.premiere_safe{final_suffix}")

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
    ]
    if mp4_compatible:
        ffmpeg_command.extend(["-movflags", "+faststart"])
    ffmpeg_command.append(str(temp_path))

    try:
        result = subprocess.run(
            ffmpeg_command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("FFmpeg is required for Premiere-compatible audio post-processing") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        details = stderr.splitlines()[-1] if stderr else "unknown ffmpeg error"
        raise RuntimeError(f"Failed to normalize audio for Premiere: {details}")

    if final_path.exists():
        final_path.unlink()
    temp_path.replace(final_path)

    if file_path.exists() and file_path != final_path:
        file_path.unlink()

    return {
        "file_path": str(final_path.resolve()),
        "file_name": final_path.name,
        "premiere_safe_audio": mp4_compatible,
        "audio_normalized": True,
        "audio_codec": "aac",
        "audio_profile": "aac_low",
        "audio_sample_rate": 48000,
        "audio_channels": 2,
    }


def _resolve_audio_track_file(info: dict[str, Any], fallback_path: Path, download_dir: Path) -> Path:
    """Resolve the final MP3 path for audio-only downloads."""
    if fallback_path.suffix.lower() == ".mp3" and fallback_path.exists():
        return fallback_path

    files = [item for item in download_dir.iterdir() if item.is_file() and item.suffix.lower() == ".mp3"]
    video_id = str(info.get("id") or "").strip()
    if video_id:
        by_id = [item for item in files if f"[{video_id}]" in item.name]
        if by_id:
            return sorted(by_id, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    if files:
        return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    raise RuntimeError("Audio track conversion completed, but MP3 file was not found")


def _normalize_audio_bitrate(audio_bitrate_kbps: int | None) -> int:
    if audio_bitrate_kbps is None:
        return 320

    bitrate = int(audio_bitrate_kbps)
    if bitrate not in ALLOWED_AUDIO_BITRATES:
        raise RuntimeError("Audio bitrate must be one of: 192 or 320 kbps")
    return bitrate


def _safe_video_format_selector() -> str:
    return "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/best[ext=mp4]/best"


def _build_selected_format_selector(video_url: str, format_id: str) -> str:
    """Avoid adding a second audio stream when the selected format is progressive."""
    ydl_opts: dict[str, Any] = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "simulate": "list_only",
        "skip_download": True,
    }
    info, _ = extract_info_with_cookie_fallback(video_url=video_url, ydl_opts=ydl_opts, download=False)
    for item in info.get("formats") or []:
        if str(item.get("format_id") or "").strip() != format_id:
            continue
        acodec = str(item.get("acodec") or "none").lower()
        if acodec != "none":
            return f"{format_id}/best"
        return f"{format_id}+bestaudio/best"

    return f"{format_id}+bestaudio/{format_id}/best"


def _download_audio_track(video_url: str, download_dir: Path, audio_bitrate_kbps: int | None) -> dict[str, Any]:
    """Download best available audio and convert to MP3."""
    bitrate = _normalize_audio_bitrate(audio_bitrate_kbps)

    ydl_opts: dict[str, Any] = {
        **build_yt_dlp_download_options(download_dir),
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": str(bitrate),
            }
        ],
    }
    try:
        info, prepared_name = extract_info_with_cookie_fallback(video_url=video_url, ydl_opts=ydl_opts, download=True)
    except DownloadError as exc:
        message = str(exc)
        if "ffmpeg" in message.lower():
            raise RuntimeError("FFmpeg is required for MP3 conversion. Install ffmpeg and retry.") from exc
        raise RuntimeError(format_yt_dlp_error(message)) from exc

    resolved_path = _resolve_downloaded_file(info=info, prepared_name=prepared_name, download_dir=download_dir)
    mp3_path = _resolve_audio_track_file(info=info, fallback_path=resolved_path, download_dir=download_dir)

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "file_path": str(mp3_path.resolve()),
        "file_name": mp3_path.name,
        "format_id": info.get("format_id"),
        "audio_only": True,
        "audio_format": "mp3",
        "audio_bitrate_kbps": bitrate,
    }


def download_video(
    video_url: str,
    download_dir: Path,
    format_id: str | None = None,
    audio_only: bool = False,
    audio_bitrate_kbps: int | None = None,
) -> dict[str, Any]:
    """Download a single video and prefer selected quality + best available audio."""
    download_dir.mkdir(parents=True, exist_ok=True)
    cleanup_stale_download_artifacts(download_dir)

    if audio_only:
        return _download_audio_track(
            video_url=video_url,
            download_dir=download_dir,
            audio_bitrate_kbps=audio_bitrate_kbps,
        )

    selected_format = _build_selected_format_selector(video_url, format_id) if format_id else _safe_video_format_selector()

    ydl_opts: dict[str, Any] = {
        **build_yt_dlp_download_options(download_dir),
        "format": selected_format,
        "merge_output_format": "mkv",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        info, prepared_name = extract_info_with_cookie_fallback(video_url=video_url, ydl_opts=ydl_opts, download=True)
    except DownloadError as exc:
        message = str(exc)
        if "ffmpeg" in message.lower():
            raise RuntimeError("FFmpeg is required for selected quality. Install ffmpeg and retry.") from exc
        raise RuntimeError(format_yt_dlp_error(message)) from exc
    except RuntimeError as exc:
        if not format_id or not is_requested_format_error(str(exc)):
            raise

        fallback_opts = {**ydl_opts, "format": _safe_video_format_selector()}
        info, prepared_name = extract_info_with_cookie_fallback(
            video_url=video_url,
            ydl_opts=fallback_opts,
            download=True,
        )

    file_path = _resolve_downloaded_file(info=info, prepared_name=prepared_name, download_dir=download_dir)
    try:
        normalized = _apply_premiere_safe_audio(file_path=file_path)
    except RuntimeError:
        if not format_id:
            raise
        fallback_opts = {**ydl_opts, "format": _safe_video_format_selector()}
        info, prepared_name = extract_info_with_cookie_fallback(video_url=video_url, ydl_opts=fallback_opts, download=True)
        file_path = _resolve_downloaded_file(info=info, prepared_name=prepared_name, download_dir=download_dir)
        normalized = _apply_premiere_safe_audio(file_path=file_path)

    return {
        "id": info.get("id"),
        "title": info.get("title"),
        "webpage_url": info.get("webpage_url") or video_url,
        "file_path": normalized["file_path"],
        "file_name": normalized["file_name"],
        "format_id": info.get("format_id") or format_id,
        "premiere_safe_audio": normalized["premiere_safe_audio"],
        "audio_normalized": normalized["audio_normalized"],
        "audio_codec": normalized["audio_codec"],
        "audio_profile": normalized["audio_profile"],
        "audio_sample_rate": normalized["audio_sample_rate"],
        "audio_channels": normalized["audio_channels"],
        "audio_only": False,
    }
