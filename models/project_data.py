from dataclasses import dataclass
from typing import Dict, TYPE_CHECKING

from models.asset_record import AssetRecord
from models.page_model import PageModel

if TYPE_CHECKING:
    from services.asset_manager import AssetManager


@dataclass
class ProjectData:
    format_version: int
    project_id: str
    project_name: str
    created_at: str
    modified_at: str
    pages: Dict[str, PageModel]
    page_order: list[str]
    assets: Dict[str, AssetRecord]
    workspace_id: str
    source_project_path: str
    asset_manager: "AssetManager"
