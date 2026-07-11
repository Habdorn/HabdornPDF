from typing import List

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QListWidget


class PageListWidget(QListWidget):
    native_drop_finished = Signal(list, list)

    def dropEvent(self, event) -> None:
        old_order = self._ordered_page_ids()
        super().dropEvent(event)
        QTimer.singleShot(
            0,
            lambda: self.native_drop_finished.emit(
                old_order,
                self._ordered_page_ids(),
            ),
        )

    def _ordered_page_ids(self) -> List[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.count())
        ]
