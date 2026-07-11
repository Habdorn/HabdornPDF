from dataclasses import dataclass


@dataclass
class OverlayModel:
    id: str
    path: str
    x: float
    y: float
    w: float
    h: float
    rotation: float = 0.0
