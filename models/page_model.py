from dataclasses import dataclass, field
from typing import List, Optional

from app.constants import A4_PORTRAIT
from models.overlay_model import OverlayModel


@dataclass
class PageModel:
    id: str
    kind: str  # pdf | image | blank
    source: Optional[str] = None
    page_index: Optional[int] = None
    width_pt: float = A4_PORTRAIT[0]
    height_pt: float = A4_PORTRAIT[1]
    rotation: int = 0
    label: str = "Página"
    overlays: List[OverlayModel] = field(default_factory=list)
    asset_id: Optional[str] = None
