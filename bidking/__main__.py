"""GUI 启动入口。

uv run bidking-gui  → 调用 main()
python -m bidking   → 同上
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BidKing")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
