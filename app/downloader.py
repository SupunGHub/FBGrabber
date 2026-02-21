from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PySide6 import QtCore
from yt_dlp import YoutubeDL

from .models import FormatOption
from .utils import clean_facebook_title, ensure_unique_path, human_readable_bytes, human_readable_eta, sanitize_filename


class Downloader(QtCore.QObject):
    def __init__(self, cookies_file: Optional[Path] = None) -> None:
        super().__init__()
        self.cookies_file = cookies_file

    def set_cookies_file(self, path: Optional[Path]) -> None:
        self.cookies_file = path

    def fetch_formats(self, url: str) -> Tuple[str, List[FormatOption]]:
        opts: dict = {
            "quiet": True,
            "skip_download": True,
            "noplaylist": True,
        }
        if self.cookies_file:
            opts["cookiefile"] = str(self.cookies_file)

        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = clean_facebook_title(info.get("title") or "") or "Facebook Video"
        formats_raw = info.get("formats") or []
        formats: List[FormatOption] = []
        for f in formats_raw:
            if f.get("acodec") == "none" and f.get("vcodec") == "none":
                continue
            resolution = ""
            if f.get("height"):
                resolution = f"{f.get('height')}p"
            fps = f.get("fps")
            tbr = f.get("tbr")
            fmt = FormatOption(
                format_id=str(f.get("format_id")),
                ext=(f.get("ext") or ""),
                resolution=resolution,
                fps=int(fps) if fps else None,
                vcodec=f.get("vcodec"),
                acodec=f.get("acodec"),
                filesize=f.get("filesize") or f.get("filesize_approx"),
                format_note=f.get("format_note"),
                tbr=float(tbr) if tbr else None,
            )
            formats.append(fmt)

        # Prefer higher resolution first, then bitrate, then filesize
        def sort_key(x: FormatOption):
            try:
                height = int(x.resolution.replace("p", "")) if x.resolution else 0
            except Exception:
                height = 0
            return (height, x.fps or 0, x.tbr or 0, x.filesize or 0)

        formats.sort(key=sort_key, reverse=True)
        return title, formats

    def download(
        self,
        url: str,
        title: str,
        download_dir: Path,
        selected_format_id: Optional[str],
        progress_callback: Optional[Callable[[float, str, str, str], None]] = None,
    ) -> Path:
        safe_title = sanitize_filename(title)

        # We let yt-dlp choose extension; ensure unique destination after known ext is resolved
        outtmpl = str(download_dir / f"{safe_title}.%(ext)s")

        ydl_opts: dict = {
            "quiet": True,
            "noprogress": True,
            "retries": 3,
            "noplaylist": True,
            "outtmpl": outtmpl,
            "concurrent_fragment_downloads": 4,
        }
        if selected_format_id:
            ydl_opts["format"] = selected_format_id
        if self.cookies_file:
            ydl_opts["cookiefile"] = str(self.cookies_file)

        def hook(d: dict) -> None:
            if progress_callback is None:
                return
            status = d.get("status")
            if status == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed") or 0
                eta = d.get("eta") or 0
                percent = (downloaded / total * 100.0) if total else 0.0
                progress_callback(
                    percent,
                    human_readable_bytes(speed) + "/s" if speed else "",
                    human_readable_eta(eta),
                    d.get("_default_template") or "Downloading",
                )
            elif status == "finished":
                progress_callback(100.0, "", "", "Processing")

        ydl_opts["progress_hooks"] = [hook]

        download_dir.mkdir(parents=True, exist_ok=True)

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            final_path = Path(ydl.prepare_filename(info))
            # Ensure unique target name if already exists
            final_path = ensure_unique_path(final_path)
        return final_path

