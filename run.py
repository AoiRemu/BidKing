"""Standalone entry point for PyInstaller packaging.

Uses absolute imports so PyInstaller can resolve them when running
the script directly (without -m bidking).
"""
import sys

from PySide6.QtWidgets import QApplication

from bidking.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BidKing")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
