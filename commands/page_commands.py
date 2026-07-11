from copy import deepcopy
from typing import TYPE_CHECKING, List, Tuple

from PySide6.QtGui import QUndoCommand

from models.page_model import PageModel

if TYPE_CHECKING:
    from app.main_window import MainWindow


class InsertPagesCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        models: List[PageModel],
        insert_at: int,
        text: str,
    ):
        super().__init__(text)
        self.window = window
        self.models = [deepcopy(model) for model in models]
        self.insert_at = insert_at

    def redo(self) -> None:
        self.window._insert_page_models_direct(self.models, self.insert_at)

    def undo(self) -> None:
        self.window._remove_page_ids_direct(
            [model.id for model in self.models],
            select_row=max(0, self.insert_at - 1),
        )


class DeletePagesCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        rows_and_models: List[Tuple[int, PageModel]],
    ):
        super().__init__("Eliminar página")
        self.window = window
        self.rows_and_models = [
            (row, deepcopy(model)) for row, model in rows_and_models
        ]

    def redo(self) -> None:
        self.window._remove_page_ids_direct(
            [model.id for _, model in self.rows_and_models]
        )

    def undo(self) -> None:
        for row, model in sorted(
            self.rows_and_models,
            key=lambda item: item[0],
        ):
            self.window._insert_page_models_direct([model], row)


class RotatePagesCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        page_ids: List[str],
        delta: int,
    ):
        super().__init__("Rotar página")
        self.window = window
        self.page_ids = list(page_ids)
        self.delta = delta

    def redo(self) -> None:
        self.window._rotate_pages_direct(self.page_ids, self.delta)

    def undo(self) -> None:
        self.window._rotate_pages_direct(self.page_ids, -self.delta)


class ReorderPagesCommand(QUndoCommand):
    def __init__(
        self,
        window: "MainWindow",
        old_order: List[str],
        new_order: List[str],
        skip_first_redo: bool = True,
    ):
        super().__init__("Reordenar páginas")
        self.window = window
        self.old_order = list(old_order)
        self.new_order = list(new_order)
        self.skip_first_redo = skip_first_redo

    def redo(self) -> None:
        if self.skip_first_redo:
            self.skip_first_redo = False
            return
        self.window._apply_page_order(self.new_order)

    def undo(self) -> None:
        self.window._apply_page_order(self.old_order)
