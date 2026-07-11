from copy import deepcopy
from typing import TYPE_CHECKING, List, Tuple

from PySide6.QtGui import QUndoCommand

from models.overlay_model import OverlayModel

if TYPE_CHECKING:
    from app.main_window import MainWindow


class InsertOverlayCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        page_id: str,
        overlay: OverlayModel,
    ):
        super().__init__("Insertar imagen")
        self.window = window
        self.page_id = page_id
        self.overlay = deepcopy(overlay)

    def redo(self) -> None:
        self.window._insert_overlay_direct(self.page_id, self.overlay)

    def undo(self) -> None:
        self.window._remove_overlay_ids_direct(
            self.page_id,
            [self.overlay.id],
        )


class DeleteOverlaysCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        page_id: str,
        overlays: List[Tuple[int, OverlayModel]],
    ):
        super().__init__("Eliminar imagen")
        self.window = window
        self.page_id = page_id
        self.overlays = [
            (index, deepcopy(overlay)) for index, overlay in overlays
        ]

    def redo(self) -> None:
        self.window._remove_overlay_ids_direct(
            self.page_id,
            [overlay.id for _, overlay in self.overlays],
        )

    def undo(self) -> None:
        self.window._insert_overlays_direct(self.page_id, self.overlays)


class UpdateOverlayCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        page_id: str,
        before: OverlayModel,
        after: OverlayModel,
        text: str,
    ):
        super().__init__(text)
        self.window = window
        self.page_id = page_id
        self.before = deepcopy(before)
        self.after = deepcopy(after)

    def redo(self) -> None:
        self.window._replace_overlay_direct(self.page_id, self.after)

    def undo(self) -> None:
        self.window._replace_overlay_direct(self.page_id, self.before)
