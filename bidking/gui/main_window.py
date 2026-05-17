"""主窗口。

布局: 单窗口分区 (草图见设计讨论)。
- 顶部: 策略 + session 状态 + 操作按钮
- 元数据: 地图 / 英雄
- 输入: T / B / WG / 紫均 / 紫数预估 / 4个单格价
- 输出: 候选 (a, b) 列表 + 总估值 (动态联动)
- 出价
- 真实数据: 白绿/蓝/紫/金 聚合 + 红逐件
- 注释 + 完成/删除按钮 + 状态栏

行为:
- autosave (任何编辑都立即落盘到当前 record_id)
- 启动: 自动加载最近一条 draft，没有则新建空白
- 错误展示: 字段标红 + 状态栏
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..storage.config import Config
from ..storage.records import (
    RecordStore,
    empty_record,
    new_session_id,
)
from ..strategies.grid_actuarial import GridActuarial
from ..strategies.base import StrategyBase
from .widgets.red_items_table import RedItemsTable


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
RECORDS_PATH = PROJECT_DIR / "records.jsonl"
CONFIG_PATH = PROJECT_DIR / "config.json"


def _load_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_int_spin(maximum: int = 99_999_999, group_sep: bool = True, width: int = 120) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(0, maximum)
    sb.setGroupSeparatorShown(group_sep)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
    sb.setMaximumWidth(width)
    return sb


def _make_money_spin(width: int = 160) -> QSpinBox:
    sb = _make_int_spin(maximum=999_999_999, group_sep=True, width=width)
    return sb


def _make_float_spin(decimals: int = 2, maximum: float = 999.99, width: int = 100) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setDecimals(decimals)
    sb.setRange(0.0, maximum)
    sb.setSingleStep(0.01)
    sb.setAlignment(Qt.AlignmentFlag.AlignRight)
    sb.setMaximumWidth(width)
    return sb


def _fmt_money(v: int | float | None) -> str:
    if v is None:
        return "—"
    try:
        return f"¥ {int(v):,}"
    except (TypeError, ValueError):
        return "—"


# 品质配色 (bg, fg/border)
QUALITY_COLORS: dict[str, tuple[str, str]] = {
    "wg":     ("#e8f5e9", "#2e7d32"),   # 白+绿
    "blue":   ("#e3f2fd", "#1565c0"),
    "purple": ("#f3e5f5", "#7b1fa2"),
    "gold":   ("#fff8e1", "#f57f17"),
    "red":    ("#ffebee", "#c62828"),
    "jr":     ("#ffe0b2", "#e65100"),   # 金红合并
}


def _tint_spin(sb: QWidget, key: str) -> None:
    bg, _ = QUALITY_COLORS[key]
    sb.setStyleSheet(f"QAbstractSpinBox {{ background-color: {bg}; }}")


def _tint_groupbox(box: QGroupBox, key: str) -> None:
    bg, fg = QUALITY_COLORS[key]
    box.setStyleSheet(
        f"""
        QGroupBox {{
            border: 1px solid {fg};
            border-radius: 4px;
            margin-top: 10px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            color: {fg};
            background-color: {bg};
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 8px;
            padding: 0 6px;
        }}
        """
    )


def _set_error(widget: QWidget, on: bool) -> None:
    """红框标记错误字段"""
    widget.setStyleSheet("border: 2px solid #e53935;" if on else "")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("BidKing — 竞拍之王估价")
        self.resize(1200, 900)

        self.config = Config(CONFIG_PATH)
        self.store = RecordStore(RECORDS_PATH)

        self.maps = _load_json(DATA_DIR / "maps.json")
        self.heroes = _load_json(DATA_DIR / "heroes.json")

        self.strategies: dict[str, StrategyBase] = {
            GridActuarial.name: GridActuarial(),
        }
        self.current_strategy: StrategyBase = self.strategies[GridActuarial.name]

        self.current_record: dict[str, Any] = {}
        self.current_session_id: str = ""

        # 防抖: input 改动后 50ms 内多次只触发一次 autosave
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(50)
        self._save_timer.timeout.connect(self._do_save)

        self._loading = False  # 加载记录时屏蔽 autosave

        self._build_ui()
        self._load_initial_record()

    # ---------- UI 构造 ----------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        outer_v = QVBoxLayout(central)
        outer_v.setContentsMargins(12, 12, 12, 12)
        outer_v.setSpacing(8)

        outer_v.addWidget(self._build_topbar())

        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_w = QWidget()
        left_v = QVBoxLayout(left_w)
        left_v.setContentsMargins(0, 0, 6, 0)
        left_v.setSpacing(8)
        left_title = QLabel("估价 (出价前)")
        left_title.setStyleSheet("font-weight: bold; font-size: 12pt; padding: 4px 0;")
        left_v.addWidget(left_title)
        left_v.addWidget(self._build_metadata_box(), alignment=Qt.AlignmentFlag.AlignLeft)
        left_v.addWidget(self._build_inputs_box(), alignment=Qt.AlignmentFlag.AlignLeft)
        left_v.addWidget(self._build_outputs_box())
        left_v.addWidget(self._build_bid_box(), alignment=Qt.AlignmentFlag.AlignLeft)
        left_v.addStretch()
        left_scroll.setWidget(left_w)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_w = QWidget()
        right_v = QVBoxLayout(right_w)
        right_v.setContentsMargins(6, 0, 0, 0)
        right_v.setSpacing(8)
        right_title = QLabel("事后录入 (拍卖结束后)")
        right_title.setStyleSheet("font-weight: bold; font-size: 12pt; padding: 4px 0;")
        right_v.addWidget(right_title)
        right_v.addWidget(self._build_actual_box())
        right_v.addWidget(self._build_note_box())
        right_v.addStretch()
        right_scroll.setWidget(right_w)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([750, 750])
        outer_v.addWidget(splitter, stretch=1)

        outer_v.addWidget(self._build_bottom_buttons())

        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

    def _build_topbar(self) -> QWidget:
        box = QGroupBox("当前游戏")
        h = QHBoxLayout(box)

        h.addWidget(QLabel("策略:"))
        self.strategy_combo = QComboBox()
        for name in self.strategies:
            self.strategy_combo.addItem(name)
        self.strategy_combo.currentTextChanged.connect(self._on_strategy_changed)
        h.addWidget(self.strategy_combo)

        h.addSpacing(20)

        self.session_label = QLabel("(未开始)")
        h.addWidget(self.session_label, stretch=1)

        self.btn_new_game = QPushButton("开始新游戏")
        self.btn_new_game.clicked.connect(self._on_new_game)
        h.addWidget(self.btn_new_game)

        self.btn_new_auction = QPushButton("新一局拍卖")
        self.btn_new_auction.clicked.connect(self._on_new_auction)
        h.addWidget(self.btn_new_auction)

        self.btn_history = QPushButton("历史记录")
        self.btn_history.clicked.connect(self._on_open_history)
        h.addWidget(self.btn_history)

        return box

    def _build_metadata_box(self) -> QWidget:
        box = QGroupBox("本场元数据")
        box.setMaximumWidth(380)
        form = QFormLayout(box)

        self.map_combo = QComboBox()
        self.map_combo.setEditable(True)
        for m in self.maps:
            self.map_combo.addItem(f"{m['id']} {m['name']} ({m['tier']})", m["id"])
        self.map_combo.setCurrentIndex(-1)
        self.map_combo.currentIndexChanged.connect(self._on_field_changed)
        self.map_combo.editTextChanged.connect(self._on_field_changed)
        form.addRow("地图:", self.map_combo)

        self.hero_combo = QComboBox()
        self.hero_combo.setEditable(True)
        for h in self.heroes:
            self.hero_combo.addItem(f"{h['id']} {h['name']} [{h['tier']}]", h["id"])
        self.hero_combo.setCurrentIndex(-1)
        self.hero_combo.currentIndexChanged.connect(self._on_field_changed)
        self.hero_combo.editTextChanged.connect(self._on_field_changed)
        form.addRow("英雄 (一局沿用):", self.hero_combo)

        return box

    def _build_inputs_box(self) -> QWidget:
        box = QGroupBox("输入 (数格子精算法)")
        box.setMaximumWidth(420)
        form = QFormLayout(box)

        self.in_T = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.in_B = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.in_WG = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.in_purple_avg = _make_float_spin(decimals=2, maximum=99.99, width=90)
        self.in_purple_count_est = _make_int_spin(maximum=999, group_sep=False, width=90)

        _tint_spin(self.in_B, "blue")
        _tint_spin(self.in_WG, "wg")
        _tint_spin(self.in_purple_avg, "purple")
        _tint_spin(self.in_purple_count_est, "purple")

        # 默认价格 (从 config 读取，没存过用策略 defaults)
        defaults = self.config.get_strategy_defaults(
            self.current_strategy.name, self.current_strategy.defaults
        )

        self.in_v_wg = _make_money_spin()
        self.in_v_b = _make_money_spin()
        self.in_v_p = _make_money_spin()
        self.in_v_jr = _make_money_spin()
        _tint_spin(self.in_v_wg, "wg")
        _tint_spin(self.in_v_b, "blue")
        _tint_spin(self.in_v_p, "purple")
        _tint_spin(self.in_v_jr, "jr")
        self.in_v_wg.setValue(int(defaults.get("v_wg", 0)))
        self.in_v_b.setValue(int(defaults.get("v_b", 0)))
        self.in_v_p.setValue(int(defaults.get("v_p", 0)))
        self.in_v_jr.setValue(int(defaults.get("v_jr", 0)))
        self.in_purple_count_est.setValue(int(defaults.get("purple_count_est", 0)))

        for w in (
            self.in_T, self.in_B, self.in_WG, self.in_purple_avg, self.in_purple_count_est,
            self.in_v_wg, self.in_v_b, self.in_v_p, self.in_v_jr,
        ):
            w.valueChanged.connect(self._on_field_changed)

        form.addRow("总格数 T:", self.in_T)
        form.addRow("蓝色总格数 B:", self.in_B)
        form.addRow("白绿总格数 WG:", self.in_WG)
        form.addRow("紫色平均格数 c (2位小数):", self.in_purple_avg)
        form.addRow("紫色物品数预估 b_est:", self.in_purple_count_est)

        price_box = QGroupBox("单格估价 (会作为默认值持久化)")
        price_form = QFormLayout(price_box)
        price_form.addRow("白绿 v_wg:", self.in_v_wg)
        price_form.addRow("蓝   v_b:", self.in_v_b)
        price_form.addRow("紫   v_p:", self.in_v_p)
        price_form.addRow("金红 v_jr:", self.in_v_jr)
        form.addRow(price_box)

        return box

    def _build_outputs_box(self) -> QWidget:
        box = QGroupBox("输出 (动态联动)")
        v = QVBoxLayout(box)

        hint = QLabel(
            "候选解释: 紫总格数 = 道具看到的紫色物品占据的总格子数; "
            "紫物品数 = 紫色物品个数。\n"
            "(同一个紫色平均值 c 可能对应多组 (紫总格数, 紫物品数), 这里列出最接近你预估的几个)"
        )
        hint.setStyleSheet("color: #555; font-size: 9pt;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        self.candidates_group = QButtonGroup(self)
        self.candidates_group.setExclusive(True)
        self.candidates_group.idToggled.connect(self._on_candidate_toggled)
        self.candidates_container = QVBoxLayout()
        self.candidates_container.setSpacing(4)
        v.addLayout(self.candidates_container)
        self._cached_candidates: list[dict[str, Any]] = []

        self.lbl_gold_red = QLabel("金红剩余格数: —")
        self.lbl_estimate = QLabel("预估仓库总价: —")
        self.lbl_estimate.setStyleSheet("font-weight: bold; font-size: 14pt;")
        v.addWidget(self.lbl_gold_red)
        v.addWidget(self.lbl_estimate)

        self.output_errors_label = QLabel("")
        self.output_errors_label.setStyleSheet("color: #e53935;")
        self.output_errors_label.setWordWrap(True)
        v.addWidget(self.output_errors_label)

        return box

    def _build_bid_box(self) -> QWidget:
        box = QGroupBox("我的出价")
        box.setMaximumWidth(260)
        h = QHBoxLayout(box)
        self.in_bid = _make_money_spin()
        self.in_bid.valueChanged.connect(self._on_field_changed)
        h.addWidget(self.in_bid)
        h.addStretch()
        return box

    def _build_actual_box(self) -> QWidget:
        box = QGroupBox("真实数据 (事后填写)")
        v = QVBoxLayout(box)

        # 白绿
        wg_box = QGroupBox("白+绿 (聚合)")
        _tint_groupbox(wg_box, "wg")
        wg_form = QFormLayout(wg_box)
        self.act_wg_count = _make_int_spin(maximum=999, group_sep=False, width=80)
        self.act_wg_grids = _make_int_spin(maximum=999, group_sep=False, width=90)
        _tint_spin(self.act_wg_count, "wg")
        _tint_spin(self.act_wg_grids, "wg")
        for w in (self.act_wg_count, self.act_wg_grids):
            w.valueChanged.connect(self._on_field_changed)
        wg_form.addRow("数量:", self.act_wg_count)
        wg_form.addRow("总格数:", self.act_wg_grids)
        v.addWidget(wg_box)

        # 蓝
        b_box = QGroupBox("蓝色 (聚合)")
        _tint_groupbox(b_box, "blue")
        b_form = QFormLayout(b_box)
        self.act_b_count = _make_int_spin(maximum=999, group_sep=False, width=80)
        self.act_b_grids = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.act_b_value = _make_money_spin()
        _tint_spin(self.act_b_count, "blue")
        _tint_spin(self.act_b_grids, "blue")
        _tint_spin(self.act_b_value, "blue")
        for w in (self.act_b_count, self.act_b_grids, self.act_b_value):
            w.valueChanged.connect(self._on_field_changed)
        b_form.addRow("数量:", self.act_b_count)
        b_form.addRow("总格数:", self.act_b_grids)
        b_form.addRow("总价值:", self.act_b_value)
        v.addWidget(b_box)

        # 紫
        p_box = QGroupBox("紫色 (聚合)")
        _tint_groupbox(p_box, "purple")
        p_form = QFormLayout(p_box)
        self.act_p_count = _make_int_spin(maximum=999, group_sep=False, width=80)
        self.act_p_grids = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.act_p_value = _make_money_spin()
        _tint_spin(self.act_p_count, "purple")
        _tint_spin(self.act_p_grids, "purple")
        _tint_spin(self.act_p_value, "purple")
        for w in (self.act_p_count, self.act_p_grids, self.act_p_value):
            w.valueChanged.connect(self._on_field_changed)
        p_form.addRow("数量:", self.act_p_count)
        p_form.addRow("总格数:", self.act_p_grids)
        p_form.addRow("总价值:", self.act_p_value)
        v.addWidget(p_box)

        # 金
        g_box = QGroupBox("金色 (聚合)")
        _tint_groupbox(g_box, "gold")
        g_form = QFormLayout(g_box)
        self.act_g_count = _make_int_spin(maximum=999, group_sep=False, width=80)
        self.act_g_grids = _make_int_spin(maximum=999, group_sep=False, width=90)
        self.act_g_value = _make_money_spin()
        _tint_spin(self.act_g_count, "gold")
        _tint_spin(self.act_g_grids, "gold")
        _tint_spin(self.act_g_value, "gold")
        for w in (self.act_g_count, self.act_g_grids, self.act_g_value):
            w.valueChanged.connect(self._on_field_changed)
        g_form.addRow("数量:", self.act_g_count)
        g_form.addRow("总格数:", self.act_g_grids)
        g_form.addRow("总价值:", self.act_g_value)
        v.addWidget(g_box)

        # 红
        r_box = QGroupBox("红色 (逐件)")
        _tint_groupbox(r_box, "red")
        r_v = QVBoxLayout(r_box)
        self.red_table = RedItemsTable()
        self.red_table.items_changed.connect(self._on_field_changed)
        r_v.addWidget(self.red_table)
        v.addWidget(r_box)

        # 总价 + 一致性检查
        total_box = QGroupBox("仓库总价")
        total_form = QFormLayout(total_box)
        self.act_total_value = _make_money_spin()
        self.act_total_value.valueChanged.connect(self._on_field_changed)
        total_form.addRow("真实仓库总价:", self.act_total_value)
        self.consistency_label = QLabel("")
        self.consistency_label.setWordWrap(True)
        total_form.addRow("", self.consistency_label)
        v.addWidget(total_box)

        return box

    def _build_note_box(self) -> QWidget:
        box = QGroupBox("注释")
        v = QVBoxLayout(box)
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("可记录对手出价、关键判断、复盘要点等")
        self.note_edit.setFixedHeight(80)
        self.note_edit.textChanged.connect(self._on_field_changed)
        v.addWidget(self.note_edit)
        return box

    def _build_bottom_buttons(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("status: draft")
        h.addWidget(self.status_label)
        h.addStretch()

        self.btn_complete = QPushButton("标记完成 (纳入数据集)")
        self.btn_complete.clicked.connect(self._on_mark_complete)
        h.addWidget(self.btn_complete)

        self.btn_revert = QPushButton("回滚到 draft")
        self.btn_revert.clicked.connect(self._on_revert_draft)
        h.addWidget(self.btn_revert)

        self.btn_delete = QPushButton("删除本条")
        self.btn_delete.clicked.connect(self._on_delete)
        h.addWidget(self.btn_delete)

        return w

    # ---------- 加载/切换记录 ----------

    def _load_initial_record(self) -> None:
        draft = self.store.latest_draft()
        if draft:
            self.current_record = draft
            self.current_session_id = draft.get("session_id") or new_session_id()
            self._load_record_into_ui(draft)
        else:
            self._start_fresh_record(new_session=True)

    def _start_fresh_record(self, new_session: bool) -> None:
        if new_session or not self.current_session_id:
            self.current_session_id = new_session_id()
        prev_hero = self.store.latest_hero_id(self.current_session_id) if not new_session else None
        rec = empty_record(self.current_strategy.name, self.current_session_id, hero_id=prev_hero)
        self.current_record = rec
        self._load_record_into_ui(rec)
        self._schedule_save()

    def _load_record_into_ui(self, rec: dict[str, Any]) -> None:
        self._loading = True
        try:
            inputs = rec.get("inputs", {})
            self.in_T.setValue(int(inputs.get("T") or 0))
            self.in_B.setValue(int(inputs.get("B") or 0))
            self.in_WG.setValue(int(inputs.get("WG") or 0))
            self.in_purple_avg.setValue(float(inputs.get("purple_avg") or 0.0))
            self.in_purple_count_est.setValue(int(inputs.get("purple_count_est") or 0))
            # 价格用记录里的，但记录没有时回退到 config 默认
            defaults = self.config.get_strategy_defaults(
                self.current_strategy.name, self.current_strategy.defaults
            )
            self.in_v_wg.setValue(int(inputs.get("v_wg") or defaults.get("v_wg") or 0))
            self.in_v_b.setValue(int(inputs.get("v_b") or defaults.get("v_b") or 0))
            self.in_v_p.setValue(int(inputs.get("v_p") or defaults.get("v_p") or 0))
            self.in_v_jr.setValue(int(inputs.get("v_jr") or defaults.get("v_jr") or 0))

            # 元数据
            map_id = rec.get("map_id")
            self._set_combo_by_id(self.map_combo, map_id)
            hero_id = rec.get("hero_id")
            self._set_combo_by_id(self.hero_combo, hero_id)

            # 出价
            self.in_bid.setValue(int(rec.get("bid") or 0))

            # 真实数据
            actual = rec.get("actual", {})
            wg = actual.get("wg", {})
            self.act_wg_count.setValue(int(wg.get("count") or 0))
            self.act_wg_grids.setValue(int(wg.get("total_grids") or 0))
            b = actual.get("blue", {})
            self.act_b_count.setValue(int(b.get("count") or 0))
            self.act_b_grids.setValue(int(b.get("total_grids") or 0))
            self.act_b_value.setValue(int(b.get("total_value") or 0))
            p = actual.get("purple", {})
            self.act_p_count.setValue(int(p.get("count") or 0))
            self.act_p_grids.setValue(int(p.get("total_grids") or 0))
            self.act_p_value.setValue(int(p.get("total_value") or 0))
            g = actual.get("gold", {})
            self.act_g_count.setValue(int(g.get("count") or 0))
            self.act_g_grids.setValue(int(g.get("total_grids") or 0))
            self.act_g_value.setValue(int(g.get("total_value") or 0))
            self.red_table.set_items(actual.get("red", []))
            self.act_total_value.setValue(int(actual.get("total_value") or 0))

            self.note_edit.setPlainText(rec.get("note") or "")
        finally:
            self._loading = False
        self._refresh_session_label()
        self._refresh_status_label()
        self._recompute_outputs()

    def _set_combo_by_id(self, combo: QComboBox, target_id: Any) -> None:
        with QSignalBlocker(combo):
            if target_id is None:
                combo.setCurrentIndex(-1)
                combo.setEditText("")
                return
            for i in range(combo.count()):
                if combo.itemData(i) == target_id:
                    combo.setCurrentIndex(i)
                    return
            combo.setEditText(str(target_id))

    def _refresh_session_label(self) -> None:
        sess = self.current_session_id or "(无)"
        same = [r for r in self.store.all() if r.get("session_id") == self.current_session_id]
        n = len(same)
        hero_id = self.current_record.get("hero_id")
        hero_name = self._hero_name_of(hero_id)
        self.session_label.setText(f"session {sess} | 英雄 {hero_name} | 已 {n} 场")

    def _refresh_status_label(self) -> None:
        s = self.current_record.get("status", "draft")
        self.status_label.setText(f"status: {s}")

    def _hero_name_of(self, hero_id: Any) -> str:
        if hero_id is None:
            return "—"
        for h in self.heroes:
            if h["id"] == hero_id:
                return f"{h['id']} {h['name']}"
        return str(hero_id)

    # ---------- 字段变化 → 重算 + 防抖保存 ----------

    def _on_field_changed(self, *args: Any) -> None:
        if self._loading:
            return
        self._recompute_outputs()
        self._save_timer.start()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    def _recompute_outputs(self) -> None:
        inputs = self._collect_inputs()
        result = self.current_strategy.compute(inputs)

        # 错误提示
        errors = result.get("errors", [])
        warnings = result.get("warnings", [])
        msg_parts = []
        if errors:
            msg_parts.append("⚠ " + " | ".join(errors))
        if warnings:
            msg_parts.append("注意: " + " | ".join(warnings))
        self.output_errors_label.setText("\n".join(msg_parts))

        hard_error = bool(errors)
        # 输入区高亮
        _set_error(self.in_T, hard_error and "总格数" in "".join(errors))
        _set_error(self.in_B, hard_error and "蓝" in "".join(errors))
        _set_error(self.in_WG, hard_error and "白绿" in "".join(errors))
        _set_error(self.in_purple_avg, any("紫色平均" in e for e in errors))

        # 渲染候选
        self._render_candidates(result.get("candidates", []))

        # 一致性检查
        self._check_consistency()

        # 状态栏
        if errors:
            self.status_bar.showMessage("⚠ " + " ; ".join(errors), 4000)
        else:
            self.status_bar.clearMessage()

    def _render_candidates(self, candidates: list[dict[str, Any]]) -> None:
        # 决定选中哪一个: 优先用当前按钮组的状态, 否则用 record 里的 selected_idx
        current_sel = self.candidates_group.checkedId()
        if current_sel < 0:
            current_sel = int(self.current_record.get("predicted", {}).get("selected_idx", 0) or 0)
        if not candidates:
            current_sel = -1
        elif current_sel < 0 or current_sel >= len(candidates):
            current_sel = 0

        # 候选列表内容没变 → 只更新汇总, 不重建按钮 (避免点击被冲掉)
        if self._candidates_equal(self._cached_candidates, candidates):
            self._update_summary(candidates, current_sel)
            return

        # 重建按钮
        # 先从 group 移除旧按钮, 再清空 layout
        for btn in self.candidates_group.buttons():
            self.candidates_group.removeButton(btn)
        for i in reversed(range(self.candidates_container.count())):
            item = self.candidates_container.takeAt(i)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        self._cached_candidates = [dict(c) for c in candidates]

        if not candidates:
            placeholder = QLabel("(填入输入后会显示紫色 (总格数, 物品数) 候选)")
            placeholder.setStyleSheet("color: #888;")
            self.candidates_container.addWidget(placeholder)
            self._update_summary([], -1)
            return

        for idx, cand in enumerate(candidates):
            a = cand["purple_total_grids"]
            b = cand["purple_count"]
            gr = cand["gold_red_grids"]
            ev = cand.get("estimated_value")
            err = cand.get("error")
            label = (
                f"紫总 {a:>3} 格 / 紫物品 {b:>3} 件   →   "
                f"金红剩余 {gr:>3} 格   →   估值 {_fmt_money(ev)}"
            )
            if err:
                label += f"   ❌ {err}"
            rb = QRadioButton(label)
            rb.setProperty("cand_idx", idx)
            if idx == current_sel:
                rb.setChecked(True)
            self.candidates_group.addButton(rb, idx)
            self.candidates_container.addWidget(rb)

        self._update_summary(candidates, current_sel)

    @staticmethod
    def _candidates_equal(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
        if len(a) != len(b):
            return False
        keys = ("purple_total_grids", "purple_count", "gold_red_grids", "estimated_value", "error")
        for x, y in zip(a, b):
            for k in keys:
                if x.get(k) != y.get(k):
                    return False
        return True

    def _update_summary(self, candidates: list[dict[str, Any]], sel_idx: int) -> None:
        if not candidates or sel_idx < 0 or sel_idx >= len(candidates):
            self.lbl_gold_red.setText("金红剩余格数: —")
            self.lbl_estimate.setText("预估仓库总价: —")
            return
        cand = candidates[sel_idx]
        self.lbl_gold_red.setText(
            f"金红剩余格数: {cand['gold_red_grids']}    "
            f"(紫总 {cand['purple_total_grids']} 格 / 紫物品 {cand['purple_count']} 件)"
        )
        self.lbl_estimate.setText(f"预估仓库总价: {_fmt_money(cand.get('estimated_value'))}")

    def _on_candidate_toggled(self, btn_id: int, checked: bool) -> None:
        # 只在 "成为选中" 时响应, 避免每次点击触发两遍 (取消+选中)
        if not checked:
            return
        self._update_summary(self._cached_candidates, btn_id)
        self.current_record.setdefault("predicted", {})["selected_idx"] = btn_id
        self._save_timer.start()

    def _check_consistency(self) -> None:
        # 各色总价 vs 仓库总价
        sum_parts = (
            (self.act_b_value.value() or 0)
            + (self.act_p_value.value() or 0)
            + (self.act_g_value.value() or 0)
            + sum(it["value"] for it in self.red_table.items())
        )
        total = self.act_total_value.value() or 0
        if total == 0 and sum_parts == 0:
            self.consistency_label.setText("")
            return
        if total == 0:
            self.consistency_label.setText(
                f"分项合计 ¥{sum_parts:,}，总价未填"
            )
            self.consistency_label.setStyleSheet("color: #888;")
            return
        if sum_parts == total:
            self.consistency_label.setText("✓ 各色总价 = 仓库总价")
            self.consistency_label.setStyleSheet("color: #2e7d32;")
        else:
            diff = total - sum_parts
            self.consistency_label.setText(
                f"⚠ 各色合计 ¥{sum_parts:,} ≠ 总价 ¥{total:,}（差 ¥{diff:,}）"
            )
            self.consistency_label.setStyleSheet("color: #ef6c00;")

    # ---------- 收集字段 → record dict ----------

    def _collect_inputs(self) -> dict[str, Any]:
        return {
            "T": self.in_T.value() or None,
            "B": self.in_B.value() or None,
            "WG": self.in_WG.value() or None,
            "purple_avg": self.in_purple_avg.value() or None,
            "purple_count_est": self.in_purple_count_est.value() or None,
            "v_wg": self.in_v_wg.value() or None,
            "v_b": self.in_v_b.value() or None,
            "v_p": self.in_v_p.value() or None,
            "v_jr": self.in_v_jr.value() or None,
        }

    def _collect_predicted(self, candidates: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        sel_id = self.candidates_group.checkedId()
        if sel_id < 0:
            sel_id = 0
        return {
            "candidates": candidates or [],
            "selected_idx": sel_id,
        }

    def _collect_actual(self) -> dict[str, Any]:
        return {
            "wg": {
                "count": self.act_wg_count.value() or None,
                "total_grids": self.act_wg_grids.value() or None,
            },
            "blue": {
                "count": self.act_b_count.value() or None,
                "total_grids": self.act_b_grids.value() or None,
                "total_value": self.act_b_value.value() or None,
            },
            "purple": {
                "count": self.act_p_count.value() or None,
                "total_grids": self.act_p_grids.value() or None,
                "total_value": self.act_p_value.value() or None,
            },
            "gold": {
                "count": self.act_g_count.value() or None,
                "total_grids": self.act_g_grids.value() or None,
                "total_value": self.act_g_value.value() or None,
            },
            "red": self.red_table.items(),
            "total_value": self.act_total_value.value() or None,
        }

    # ---------- autosave ----------

    def _do_save(self) -> None:
        if self._loading:
            return
        rec = self.current_record

        # 更新所有字段到 record
        rec["strategy"] = self.current_strategy.name
        rec["session_id"] = self.current_session_id
        rec["map_id"] = self.map_combo.currentData() if self.map_combo.currentData() else _try_int(self.map_combo.currentText())
        rec["hero_id"] = self.hero_combo.currentData() if self.hero_combo.currentData() else _try_int(self.hero_combo.currentText())
        rec["inputs"] = self._collect_inputs()

        # 重算并存预测
        result = self.current_strategy.compute(rec["inputs"])
        rec["predicted"] = self._collect_predicted(result.get("candidates", []))

        bid = self.in_bid.value() or None
        rec["bid"] = bid
        # 自动状态升级 (只升不降): draft → bid_placed when bid > 0
        if rec.get("status") == "draft" and bid:
            rec["status"] = "bid_placed"

        rec["actual"] = self._collect_actual()
        rec["note"] = self.note_edit.toPlainText().strip()

        self.store.upsert(rec)

        # 持久化价格默认值（每次价格改了就同步保存）
        self.config.set_strategy_defaults(
            self.current_strategy.name,
            {
                "v_wg": float(self.in_v_wg.value()),
                "v_b": float(self.in_v_b.value()),
                "v_p": float(self.in_v_p.value()),
                "v_jr": float(self.in_v_jr.value()),
                "purple_count_est": float(self.in_purple_count_est.value()),
            },
        )

        self._refresh_status_label()
        self._refresh_session_label()

    # ---------- 按钮 ----------

    def _on_strategy_changed(self, name: str) -> None:
        if name not in self.strategies:
            return
        self.current_strategy = self.strategies[name]
        self._on_field_changed()

    def _on_new_game(self) -> None:
        # 先保存当前
        self._do_save()
        # 让用户选英雄（可选）
        self._start_fresh_record(new_session=True)

    def _on_new_auction(self) -> None:
        # 先保存当前
        self._do_save()
        # 同 session 新一条
        self._start_fresh_record(new_session=False)

    def _on_open_history(self) -> None:
        # 在最后实现 (history_window) 后接进来；这里先延迟 import 避开循环
        from .history_window import HistoryWindow
        self._do_save()
        self._history = HistoryWindow(self.store, on_select=self._open_record_from_history, parent=self)
        self._history.show()

    def _open_record_from_history(self, record_id: str) -> None:
        rec = self.store.get(record_id)
        if not rec:
            return
        self._do_save()  # 先存当前
        self.current_record = rec
        self.current_session_id = rec.get("session_id") or new_session_id()
        self._load_record_into_ui(rec)

    def _on_mark_complete(self) -> None:
        self.current_record["status"] = "completed"
        self._do_save()
        self.status_bar.showMessage("已标记完成，可纳入 ML 数据集", 3000)

    def _on_revert_draft(self) -> None:
        self.current_record["status"] = "draft"
        self._do_save()
        self.status_bar.showMessage("已回滚到 draft", 2000)

    def _on_delete(self) -> None:
        rid = self.current_record.get("record_id")
        if not rid:
            return
        ans = QMessageBox.question(
            self,
            "删除本条记录",
            "确定删除当前记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.store.delete(rid)
        self.status_bar.showMessage("已删除", 2000)
        self._start_fresh_record(new_session=False)


def _try_int(s: str) -> int | None:
    try:
        return int(s.strip().split()[0]) if s.strip() else None
    except (ValueError, IndexError):
        return None
