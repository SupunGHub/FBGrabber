from __future__ import annotations

import math
import re
from pathlib import Path


INVALID_CHARS = r"[^\w\-\.\(\) \[\]]+"


def sanitize_filename(name: str, max_length: int = 180) -> str:
    name = name.strip()
    name = re.sub(INVALID_CHARS, "_", name)
    # Collapse multiple underscores/spaces
    name = re.sub(r"[ _]+", " ", name)
    return name[:max_length].rstrip(". ") or "video"


def human_readable_bytes(num_bytes: float) -> str:
    if num_bytes is None or num_bytes <= 0:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = min(int(math.log(num_bytes, 1024)), len(units) - 1)
    value = num_bytes / (1024 ** idx)
    return f"{value:.1f} {units[idx]}"


def human_readable_eta(seconds: float) -> str:
    if not seconds or seconds < 0:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}h {m:02d}m {s:02d}s"
    if m:
        return f"{m:d}m {s:02d}s"
    return f"{s:d}s"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    base = path.with_suffix("")
    suffix = path.suffix
    counter = 1
    while True:
        candidate = base.parent / f"{base.name} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1

