"""结算截图保存 widget。

支持:
- 点击按钮选择图片文件
- 拖拽图片文件到 widget
- 从剪贴板粘贴 (Ctrl+V)
- 显示缩略图预览
- 复制到 screenshots/<record_id>.png

emits path_changed: 当保存路径变化时通知。
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QClipboard, QPixmap, QImage
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QApplication,
)


class ScreenshotWidget(QWidget):
    path_changed = Signal(str)

    def __init__(self, screenshots_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.screenshots_dir = Path(screenshots_dir)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self._path: str = ""

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        self.preview = QLabel("拖入图片 / 点击选择 / Ctrl+V 粘贴")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(
            "border: 2px dashed #aaa; background: #fafafa; color: #888; min-height: 120px;"
        )
        self.preview.setAcceptDrops(False)
        v.addWidget(self.preview, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_choose = QPushButton("选择文件")
        self.btn_choose.clicked.connect(self._on_choose)
        self.btn_paste = QPushButton("从剪贴板粘贴")
        self.btn_paste.clicked.connect(self._on_paste)
        self.btn_clear = QPushButton("清除")
        self.btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self.btn_choose)
        btn_row.addWidget(self.btn_paste)
        btn_row.addWidget(self.btn_clear)
        v.addLayout(btn_row)

        self.setAcceptDrops(True)

    def get_path(self) -> str:
        return self._path

    def set_path(self, path: str) -> None:
        self._path = path or ""
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if not self._path:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("拖入图片 / 点击选择 / Ctrl+V 粘贴")
            return
        p = Path(self._path)
        if not p.is_absolute():
            p = self.screenshots_dir.parent / self._path
        if not p.exists():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"找不到图片: {self._path}")
            return
        pix = QPixmap(str(p))
        if pix.isNull():
            self.preview.setText(f"无法解析图片: {p.name}")
            return
        scaled = pix.scaled(
            self.preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)
        self.preview.setToolTip(str(p))

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_preview()

    def _save_pixmap(self, pix: QPixmap) -> None:
        filename = f"{uuid.uuid4().hex}.png"
        target = self.screenshots_dir / filename
        pix.save(str(target), "PNG")
        # 存相对路径 (相对项目根)
        rel = target.relative_to(self.screenshots_dir.parent).as_posix()
        self._path = rel
        self._refresh_preview()
        self.path_changed.emit(self._path)

    def _save_file(self, src_path: Path) -> None:
        if not src_path.exists():
            return
        ext = src_path.suffix.lower() or ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        target = self.screenshots_dir / filename
        shutil.copyfile(src_path, target)
        rel = target.relative_to(self.screenshots_dir.parent).as_posix()
        self._path = rel
        self._refresh_preview()
        self.path_changed.emit(self._path)

    def _on_choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择结算截图",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._save_file(Path(path))

    def _on_paste(self) -> None:
        cb: QClipboard = QApplication.clipboard()
        img: QImage = cb.image()
        if not img.isNull():
            self._save_pixmap(QPixmap.fromImage(img))
            return
        # 剪贴板可能是文件路径
        text = cb.text().strip()
        if text:
            p = Path(text)
            if p.exists() and p.is_file():
                self._save_file(p)

    def _on_clear(self) -> None:
        self._path = ""
        self._refresh_preview()
        self.path_changed.emit(self._path)

    def keyPressEvent(self, event):  # type: ignore[override]
        if event.matches(event.standardKey().Paste):  # Ctrl+V
            self._on_paste()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):  # type: ignore[override]
        md = event.mimeData()
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self._save_pixmap(QPixmap.fromImage(img))
                event.acceptProposedAction()
                return
        if md.hasUrls():
            urls = md.urls()
            for url in urls:
                p = Path(url.toLocalFile())
                if p.exists() and p.is_file():
                    self._save_file(p)
                    event.acceptProposedAction()
                    return
        event.ignore()
