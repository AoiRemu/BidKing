"""历史记录窗口。

QTableView + 自定义 model + 过滤栏。
单击行回调主窗口的编辑入口。
右键菜单: 删除。
"""
from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..storage.records import RecordStore


COLUMNS = [
    ("时间", "timestamp"),
    ("Session", "session_id"),
    ("地图", "map_id"),
    ("英雄", "hero_id"),
    ("策略", "strategy"),
    ("status", "status"),
    ("出价", "bid"),
    ("预测", "predicted_value"),
    ("真实", "actual_value"),
    ("偏差%", "diff_pct"),
]


def _selected_predicted(rec: dict[str, Any]) -> float | None:
    pred = rec.get("predicted") or {}
    cands = pred.get("candidates") or []
    if not cands:
        return None
    idx = int(pred.get("selected_idx") or 0)
    if idx >= len(cands):
        idx = 0
    return cands[idx].get("estimated_value")


def _row_values(rec: dict[str, Any]) -> dict[str, Any]:
    pv = _selected_predicted(rec)
    actual = rec.get("actual") or {}
    av = actual.get("total_value")
    bid = rec.get("bid")
    diff = None
    if pv is not None and av:
        diff = (av - pv) / pv * 100.0
    return {
        "timestamp": rec.get("timestamp") or "",
        "session_id": rec.get("session_id") or "",
        "map_id": rec.get("map_id") or "",
        "hero_id": rec.get("hero_id") or "",
        "strategy": rec.get("strategy") or "",
        "status": rec.get("status") or "",
        "bid": _fmt_money(bid),
        "predicted_value": _fmt_money(pv),
        "actual_value": _fmt_money(av),
        "diff_pct": f"{diff:+.1f}%" if diff is not None else "—",
    }


def _fmt_money(v: Any) -> str:
    if v is None or v == "":
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return "—"


class RecordsModel(QAbstractTableModel):
    def __init__(self, store: RecordStore) -> None:
        super().__init__()
        self.store = store
        self._rows: list[dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        self.beginResetModel()
        recs = sorted(self.store.all(), key=lambda r: r.get("timestamp", ""), reverse=True)
        self._rows = recs
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        rec = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            key = COLUMNS[index.column()][1]
            return _row_values(rec).get(key, "")
        if role == Qt.ItemDataRole.UserRole:
            return rec.get("record_id")
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section][0]
        return section + 1

    def record_id_at(self, row: int) -> str | None:
        if 0 <= row < len(self._rows):
            return self._rows[row].get("record_id")
        return None

    def record_at(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class StatusFilterProxy(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self.allowed_statuses: set[str] = {"draft", "bid_placed", "completed"}
        self.allowed_session: str | None = None  # None = 全部

    def set_statuses(self, statuses: set[str]) -> None:
        self.allowed_statuses = statuses
        self.invalidateFilter()

    def set_session(self, session_id: str | None) -> None:
        self.allowed_session = session_id
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model: RecordsModel = self.sourceModel()  # type: ignore[assignment]
        rec = model.record_at(source_row)
        if rec is None:
            return False
        if rec.get("status") not in self.allowed_statuses:
            return False
        if self.allowed_session is not None and rec.get("session_id") != self.allowed_session:
            return False
        return True


class HistoryWindow(QMainWindow):
    def __init__(
        self,
        store: RecordStore,
        on_select: Callable[[str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.resize(1100, 600)
        self.store = store
        self.on_select = on_select

        self.model = RecordsModel(store)
        self.proxy = StatusFilterProxy()
        self.proxy.setSourceModel(self.model)

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)

        v.addLayout(self._build_filter_bar())

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.view.setSortingEnabled(True)
        self.view.doubleClicked.connect(self._on_double_click)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        v.addWidget(self.view)

    def _build_filter_bar(self) -> QHBoxLayout:
        h = QHBoxLayout()

        h.addWidget(QLabel("状态:"))
        self.cb_draft = QCheckBox("draft")
        self.cb_bid = QCheckBox("bid_placed")
        self.cb_completed = QCheckBox("completed")
        for cb in (self.cb_draft, self.cb_bid, self.cb_completed):
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_filter_changed)
            h.addWidget(cb)

        h.addSpacing(20)
        h.addWidget(QLabel("Session:"))
        self.session_combo = QComboBox()
        self.session_combo.addItem("(全部)", None)
        seen = []
        for rec in sorted(self.store.all(), key=lambda r: r.get("timestamp", ""), reverse=True):
            sid = rec.get("session_id")
            if sid and sid not in seen:
                seen.append(sid)
                self.session_combo.addItem(sid, sid)
        self.session_combo.currentIndexChanged.connect(self._on_filter_changed)
        h.addWidget(self.session_combo)

        h.addStretch()

        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self._reload)
        h.addWidget(btn_refresh)

        return h

    def _on_filter_changed(self) -> None:
        statuses: set[str] = set()
        if self.cb_draft.isChecked():
            statuses.add("draft")
        if self.cb_bid.isChecked():
            statuses.add("bid_placed")
        if self.cb_completed.isChecked():
            statuses.add("completed")
        self.proxy.set_statuses(statuses)
        sid = self.session_combo.currentData()
        self.proxy.set_session(sid)

    def _reload(self) -> None:
        self.model.reload()

    def _on_double_click(self, proxy_index) -> None:
        source_idx = self.proxy.mapToSource(proxy_index)
        rid = self.model.record_id_at(source_idx.row())
        if rid:
            self.on_select(rid)
            self.close()

    def _on_context_menu(self, pos) -> None:
        idx = self.view.indexAt(pos)
        if not idx.isValid():
            return
        source_idx = self.proxy.mapToSource(idx)
        rid = self.model.record_id_at(source_idx.row())
        if not rid:
            return
        menu = QMenu(self)
        act_open = QAction("打开编辑", self)
        act_delete = QAction("删除...", self)
        menu.addAction(act_open)
        menu.addAction(act_delete)
        chosen = menu.exec(self.view.viewport().mapToGlobal(pos))
        if chosen is act_open:
            self.on_select(rid)
            self.close()
        elif chosen is act_delete:
            ans = QMessageBox.question(
                self,
                "删除",
                f"删除记录 {rid[:8]}…？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ans == QMessageBox.StandardButton.Yes:
                self.store.delete(rid)
                self._reload()
