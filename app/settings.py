from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir, user_videos_dir


CONFIG_DIR_NAME = "FBGrabber"
CONFIG_FILE_NAME = "settings.json"


@dataclass
class AppSettings:
    download_dir: Path
    max_concurrent_downloads: int = 2
    cookies_file: Optional[Path] = None

    @staticmethod
    def default_download_dir() -> Path:
        base = Path(user_videos_dir() or Path.home() / "Videos")
        path = base / CONFIG_DIR_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def config_path() -> Path:
        cfg_dir = Path(user_config_dir(CONFIG_DIR_NAME))
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir / CONFIG_FILE_NAME

    @classmethod
    def load(cls) -> "AppSettings":
        cfg_path = cls.config_path()
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                download_dir = Path(data.get("download_dir", str(cls.default_download_dir())))
                cookies_raw = data.get("cookies_file")
                cookies_path = Path(cookies_raw) if cookies_raw else None
                max_concurrent = int(data.get("max_concurrent_downloads", 2))
                download_dir.mkdir(parents=True, exist_ok=True)
                return cls(download_dir=download_dir,
                           max_concurrent_downloads=max_concurrent,
                           cookies_file=cookies_path)
            except Exception:
                # Fallback to defaults on parse error
                pass
        return cls(download_dir=cls.default_download_dir())

    def save(self) -> None:
        data = asdict(self)
        # Convert Paths to strings
        data["download_dir"] = str(self.download_dir)
        data["cookies_file"] = str(self.cookies_file) if self.cookies_file else None
        self.config_path().write_text(json.dumps(data, indent=2), encoding="utf-8")

