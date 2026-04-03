from pathlib import Path

from app.downloader import download_video


def main() -> None:
    """CLI wrapper: download only, no transcoding."""
    video_url = input("Enter video URL: ").strip()
    if not video_url:
        print("URL is empty. Exiting.")
        return

    download_path = Path(__file__).resolve().parent / "downloads"

    try:
        result = download_video(video_url=video_url, download_dir=download_path)
        print("Download completed")
        print(f"File: {result['file_path']}")
    except Exception as exc:
        print(f"Download failed: {exc}")


if __name__ == "__main__":
    main()
