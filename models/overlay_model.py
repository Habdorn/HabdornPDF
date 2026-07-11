from dataclasses import dataclass
from typing import Optional


@dataclass
class OverlayModel:
    id: str
    path: str
    x: float
    y: float
    w: float
    h: float
    rotation: float = 0.0
    asset_id: Optional[str] = None
