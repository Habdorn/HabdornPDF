from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AssetRecord:
    id: str
    internal_path: str
    original_path: str
    original_name: str
    extension: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: Optional[str] = None
