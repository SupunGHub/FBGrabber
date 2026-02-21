from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional


class QueueStatus(str, Enum):
    PENDING = "Pending"
    READY = "Ready"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELED = "Canceled"


@dataclass
class FormatOption:
    format_id: str
    ext: str
    resolution: str
    fps: Optional[int]
    vcodec: Optional[str]
    acodec: Optional[str]
    filesize: Optional[int]
    format_note: Optional[str]
    tbr: Optional[float] = None

    @property
    def has_video(self) -> bool:
        return bool(self.vcodec and self.vcodec != "none")

    @property
    def has_audio(self) -> bool:
        return bool(self.acodec and self.acodec != "none")

    @property
    def stream_type(self) -> str:
        if self.has_video and self.has_audio:
            return "Video + Audio"
        if self.has_video:
            return "Video Only"
        if self.has_audio:
            return "Audio Only"
        return ""

    def display_text(self) -> str:
        parts: List[str] = []
        if self.resolution:
            parts.append(self.resolution)
        if self.fps:
            parts.append(f"{self.fps}fps")
        if self.tbr:
            parts.append(f"{self.tbr:.0f}kbps")
        if self.filesize:
            size_mb = self.filesize / (1024 * 1024)
            parts.append(f"{size_mb:.1f} MB")
        if self.ext:
            parts.append(self.ext)
        if self.format_note:
            parts.append(self.format_note)
        else:
            # Add stream type label when there's no format_note
            st = self.stream_type
            if st:
                parts.append(st)
        return " · ".join(parts)


@dataclass
class QueueItem:
    id: int
    url: str
    title: str
    selected_format_id: Optional[str] = None
    available_formats: List[FormatOption] = field(default_factory=list)
    output_path: Optional[Path] = None
    progress_percent: float = 0.0
    speed_text: str = ""
    eta_text: str = ""
    status: QueueStatus = QueueStatus.PENDING
    error_message: Optional[str] = None

