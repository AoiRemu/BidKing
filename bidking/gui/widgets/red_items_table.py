"""红色物品逐件录入表格。

4 列:
  格数 (QSpinBox)
  价值 (QSpinBox 千分位显示)
  类别 (QComboBox)
  名字 (QLineEdit, 可选)

行管理:
  默认 1 个空行
  填完任一行的价值列回车 → 自动在表尾追加新空行
  每行最后一列右侧有 × 按钮删除该行
  保存时空行 (格数和价值都为 0/空) 自动忽略

emits items_changed: 任何编辑都会触发，主窗口用来 autosave。
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


CATEGORIES = ["", "家具", "医疗", "时尚", "武器", "珠宝", "古董", "数码", "交通", "食品", "书画"]

COL_GRIDS = 0
COL_VALUE = 1
COL_CATEGORY = 2
COL_NAME = 3
COL_DELETE = 4


class _IntSpinDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None, maximum: int = 100, group_sep: bool = False):
        super().__init__(parent)
        self._max = maximum
        self._group = group_sep

    def createEditor(self, parent, option, index):
        sb = QSpinBox(parent)
        sb.setRange(0, self._max)
        sb.setGroupSeparatorShown(self._group)
        sb.setAlignment(Qt.AlignmentFlag.AlignRight)
        return sb

    def setEditorData(self, editor, index):
        v = index.data(Qt.ItemDataRole.EditRole) or 0
        try:
            editor.setValue(int(v))
        except (TypeError, ValueError):
            editor.setValue(0)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)


class _CategoryDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(CATEGORIES)
        return cb

    def setEditorData(self, editor, index):
        v = index.data(Qt.ItemDataRole.EditRole) or ""
        i = CATEGORIES.index(v) if v in CATEGORIES else 0
        editor.setCurrentIndex(i)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class RedItemsTable(QWidget):
    items_changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._suspend_signals = False
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(["格数", "价值", "类别", "名字", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_GRIDS, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_VALUE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_CATEGORY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_DELETE, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setItemDelegateForColumn(COL_GRIDS, _IntSpinDelegate(self, maximum=99))
        self.table.setItemDelegateForColumn(
            COL_VALUE, _IntSpinDelegate(self, maximum=99_999_999, group_sep=True)
        )
        self.table.setItemDelegateForColumn(COL_CATEGORY, _CategoryDelegate(self))

        self.table.cellChanged.connect(self._on_cell_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

        add_btn = QPushButton("+ 添加红物品", self)
        add_btn.clicked.connect(lambda: self._append_empty_row(emit=True))
        layout.addWidget(add_btn)

        self._append_empty_row(emit=False)

    def _append_empty_row(self, emit: bool = True) -> int:
        row = self.table.rowCount()
        self._suspend_signals = True
        self.table.insertRow(row)

        grids_item = QTableWidgetItem()
        grids_item.setData(Qt.ItemDataRole.EditRole, 0)
        grids_item.setData(Qt.ItemDataRole.DisplayRole, "")
        self.table.setItem(row, COL_GRIDS, grids_item)

        value_item = QTableWidgetItem()
        value_item.setData(Qt.ItemDataRole.EditRole, 0)
        value_item.setData(Qt.ItemDataRole.DisplayRole, "")
        self.table.setItem(row, COL_VALUE, value_item)

        cat_item = QTableWidgetItem("")
        self.table.setItem(row, COL_CATEGORY, cat_item)

        name_item = QTableWidgetItem("")
        self.table.setItem(row, COL_NAME, name_item)

        delete_btn = QPushButton("×")
        delete_btn.setFixedWidth(28)
        delete_btn.setToolTip("删除该行")
        delete_btn.clicked.connect(lambda _=False, b=delete_btn: self._delete_button_clicked(b))
        self.table.setCellWidget(row, COL_DELETE, delete_btn)
        self._suspend_signals = False

        if emit:
            self.items_changed.emit()
        return row

    def _delete_button_clicked(self, btn: QPushButton) -> None:
        # 找到按钮所在行
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, COL_DELETE) is btn:
                self.table.removeRow(row)
                if self.table.rowCount() == 0:
                    self._append_empty_row(emit=False)
                self.items_changed.emit()
                return

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._suspend_signals:
            return
        # 更新 display role for int columns（保持千分位显示）
        if col in (COL_GRIDS, COL_VALUE):
            item = self.table.item(row, col)
            if item is not None:
                v = item.data(Qt.ItemDataRole.EditRole)
                try:
                    iv = int(v) if v not in (None, "") else 0
                except (TypeError, ValueError):
                    iv = 0
                self._suspend_signals = True
                if iv == 0:
                    item.setData(Qt.ItemDataRole.DisplayRole, "")
                else:
                    if col == COL_VALUE:
                        item.setData(Qt.ItemDataRole.DisplayRole, f"{iv:,}")
                    else:
                        item.setData(Qt.ItemDataRole.DisplayRole, str(iv))
                self._suspend_signals = False

        # 若改的是最后一行的"价值"且非空，追加新空行
        if col == COL_VALUE and row == self.table.rowCount() - 1:
            item = self.table.item(row, col)
            v = item.data(Qt.ItemDataRole.EditRole) if item is not None else 0
            try:
                iv = int(v) if v not in (None, "") else 0
            except (TypeError, ValueError):
                iv = 0
            if iv > 0:
                self._append_empty_row(emit=False)

        self.items_changed.emit()

    def items(self) -> list[dict[str, Any]]:
        """返回非空行列表（格数 > 0 或 价值 > 0 才算非空）"""
        result: list[dict[str, Any]] = []
        for row in range(self.table.rowCount()):
            grids = _int_of(self.table.item(row, COL_GRIDS))
            value = _int_of(self.table.item(row, COL_VALUE))
            if grids == 0 and value == 0:
                continue
            cat_item = self.table.item(row, COL_CATEGORY)
            name_item = self.table.item(row, COL_NAME)
            category = cat_item.text() if cat_item is not None else ""
            name = name_item.text() if name_item is not None else ""
            result.append(
                {
                    "grids": grids,
                    "value": value,
                    "category": category or None,
                    "name": name or None,
                }
            )
        return result

    def set_items(self, items: list[dict[str, Any]]) -> None:
        self._suspend_signals = True
        self.table.setRowCount(0)
        for item in items:
            row = self._append_empty_row(emit=False)
            self.table.item(row, COL_GRIDS).setData(Qt.ItemDataRole.EditRole, int(item.get("grids") or 0))
            self.table.item(row, COL_VALUE).setData(Qt.ItemDataRole.EditRole, int(item.get("value") or 0))
            self.table.item(row, COL_CATEGORY).setText(item.get("category") or "")
            self.table.item(row, COL_NAME).setText(item.get("name") or "")
        if self.table.rowCount() == 0:
            self._append_empty_row(emit=False)
        else:
            # 末尾留一个空行供继续录入
            last = self.table.rowCount() - 1
            if _int_of(self.table.item(last, COL_VALUE)) > 0:
                self._append_empty_row(emit=False)
        self._suspend_signals = False
        # 触发千分位重显示
        for row in range(self.table.rowCount()):
            self._on_cell_changed(row, COL_GRIDS)
            self._on_cell_changed(row, COL_VALUE)


def _int_of(item: QTableWidgetItem | None) -> int:
    if item is None:
        return 0
    v = item.data(Qt.ItemDataRole.EditRole)
    try:
        return int(v) if v not in (None, "") else 0
    except (TypeError, ValueError):
        return 0
