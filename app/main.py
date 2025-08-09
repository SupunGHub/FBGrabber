from __future__ import annotations

import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from app.downloader import Downloader
from app.models import FormatOption, QueueItem, QueueStatus
from app.settings import AppSettings


class Signals(QtCore.QObject):
    formatsFetched = QtCore.Signal(str, list)  # title, formats
    progress = QtCore.Signal(int, float, str, str, str)  # row, percent, speed, eta, status
    finished = QtCore.Signal(int, bool, str, str)  # row, success, output_path, error_message


class DownloadManager(QtCore.QObject):
    def __init__(self, settings: AppSettings, ui: "MainWindow") -> None:
        super().__init__()
        self.settings = settings
        self.ui = ui
        self.signals = Signals()
        self.executor = ThreadPoolExecutor(max_workers=self.settings.max_concurrent_downloads)
        self.downloader = Downloader(cookies_file=self.settings.cookies_file)

        # Model state
        self.items: List[QueueItem] = []
        self.row_for_item_id: Dict[int, int] = {}
        self._next_id: int = 1

        # Connect UI signals
        ui.requestFetchFormats.connect(self.fetch_formats)
        ui.requestAddToQueue.connect(self.add_to_queue)
        ui.requestChooseDownloadDir.connect(self.choose_download_dir)
        ui.requestChooseCookiesFile.connect(self.choose_cookies_file)
        ui.requestOpenDownloadDir.connect(self.open_download_dir)

        # Context menu actions
        ui.requestOpenItemFile.connect(self.open_item_file)
        ui.requestOpenItemFolder.connect(self.open_item_folder)
        ui.requestCopyItemUrl.connect(self.copy_item_url)
        ui.requestCopyItemOutputPath.connect(self.copy_item_output)
        ui.requestRetryItem.connect(self.retry_item)
        ui.requestRemoveItem.connect(self.remove_item)

        # Connect internal signals to UI update methods
        self.signals.formatsFetched.connect(self._on_formats_fetched)
        self.signals.progress.connect(self._on_progress)
        self.signals.finished.connect(self._on_finished)

    # UI slot handlers
    @QtCore.Slot(str)
    def fetch_formats(self, url: str) -> None:
        def task() -> Tuple[str, List[FormatOption]]:
            return self.downloader.fetch_formats(url)

        def done(fut: Future):
            try:
                title, formats = fut.result()
                self.signals.formatsFetched.emit(title, formats)
            except Exception as e:  # noqa: BLE001
                QtWidgets.QMessageBox.critical(self.ui, "Error", f"Failed to fetch formats:\n{e}")

        self.executor.submit(task).add_done_callback(done)

    @QtCore.Slot(str, object, str, str)
    def add_to_queue(self, url: str, selected_format_id: Optional[str], title: str, quality_text: str) -> None:
        item = QueueItem(id=self._next_id, url=url, title=title, selected_format_id=selected_format_id,
                         status=QueueStatus.PENDING)
        self._next_id += 1
        self.items.append(item)
        row = self.ui.add_queue_row(item, quality_text)
        self.row_for_item_id[item.id] = row

        self._start_item(item)

    def _start_item(self, item: QueueItem) -> None:
        row = self.row_for_item_id[item.id]
        item.status = QueueStatus.DOWNLOADING
        self.ui.update_progress_row(row, 0.0, "", "", "Queued")

        def progress(percent: float, speed: str, eta: str, status_text: str) -> None:
            # Simplify status to friendly text
            if status_text.lower().startswith("download"):
                status_friendly = "Downloading"
            elif status_text.lower().startswith("merge") or status_text.lower().startswith("post-process"):
                status_friendly = "Processing"
            else:
                status_friendly = "Downloading"
            self.signals.progress.emit(row, percent, speed, eta, status_friendly)

        def task() -> Path:
            return self.downloader.download(
                url=item.url,
                title=item.title,
                download_dir=self.settings.download_dir,
                selected_format_id=item.selected_format_id,
                progress_callback=progress,
            )

        def done(fut: Future):
            success = True
            output_path = ""
            error_message = ""
            try:
                path = fut.result()
                output_path = str(path)
            except Exception as e:  # noqa: BLE001
                success = False
                error_message = str(e)
            self.signals.finished.emit(row, success, output_path, error_message)

        self.executor.submit(task).add_done_callback(done)

    # File system helpers
    @QtCore.Slot()
    def choose_download_dir(self) -> None:
        dir_path = QtWidgets.QFileDialog.getExistingDirectory(self.ui, "Choose Download Folder",
                                                              str(self.settings.download_dir))
        if dir_path:
            self.settings.download_dir = Path(dir_path)
            self.settings.download_dir.mkdir(parents=True, exist_ok=True)
            self.settings.save()

    @QtCore.Slot()
    def choose_cookies_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self.ui, "Select Cookies File", str(Path.home()),
                                                             "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.settings.cookies_file = Path(file_path)
            self.settings.save()
            self.downloader.set_cookies_file(self.settings.cookies_file)

    @QtCore.Slot()
    def open_download_dir(self) -> None:
        path = self.settings.download_dir
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(path)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(path)])

    # Internal signal handlers
    @QtCore.Slot(str, list)
    def _on_formats_fetched(self, title: str, formats: List[FormatOption]) -> None:
        from app.ui.main_window import MainWindow  # avoid circular import for type checkers

        if isinstance(self.ui, MainWindow):
            self.ui.set_formats(title, formats)

    @QtCore.Slot(int, float, str, str, str)
    def _on_progress(self, row: int, percent: float, speed: str, eta: str, status: str) -> None:
        self.ui.update_progress_row(row, percent, speed, eta, status)

    @QtCore.Slot(int, bool, str, str)
    def _on_finished(self, row: int, success: bool, output_path: str, error_message: str) -> None:
        self.ui.mark_row_finished(row, output_path, success, error_message)

    # Context menu slots
    @QtCore.Slot(int)
    def open_item_file(self, item_id: int) -> None:
        item = next((i for i in self.items if i.id == item_id), None)
        if not item:
            return
        row = self.row_for_item_id.get(item_id)
        if row is None:
            return
        out_text = self.ui.table.item(row, 6).text()
        if not out_text:
            return
        path = Path(out_text)
        if not path.exists():
            return
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(path)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(path)])

    @QtCore.Slot(int)
    def open_item_folder(self, item_id: int) -> None:
        path = self.settings.download_dir
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            QtCore.QProcess.startDetached("open", [str(path)])
        else:
            QtCore.QProcess.startDetached("xdg-open", [str(path)])

    @QtCore.Slot(int)
    def copy_item_url(self, item_id: int) -> None:
        item = next((i for i in self.items if i.id == item_id), None)
        if not item:
            return
        QtWidgets.QApplication.clipboard().setText(item.url)

    @QtCore.Slot(int)
    def copy_item_output(self, item_id: int) -> None:
        row = self.row_for_item_id.get(item_id)
        if row is None:
            return
        out_text = self.ui.table.item(row, 6).text()
        if out_text:
            QtWidgets.QApplication.clipboard().setText(out_text)

    @QtCore.Slot(int)
    def retry_item(self, item_id: int) -> None:
        item = next((i for i in self.items if i.id == item_id), None)
        if not item:
            return
        row = self.row_for_item_id.get(item_id)
        if row is None:
            return
        # Reset UI state
        self.ui.update_progress_row(row, 0.0, "", "", "Queued")
        self._start_item(item)

    @QtCore.Slot(int)
    def remove_item(self, item_id: int) -> None:
        row = self.row_for_item_id.get(item_id)
        if row is None:
            return
        self.ui.table.removeRow(row)
        self.row_for_item_id.pop(item_id, None)
        self.items = [i for i in self.items if i.id != item_id]


def load_styles(app: QtWidgets.QApplication) -> None:
    # Look for styles.qss in multiple locations to support PyInstaller bundles
    candidates = []
    # Source run (this file sits in app/)
    candidates.append(Path(__file__).parent / "styles.qss")
    # PyInstaller one-folder: data copied next to exe under app/styles.qss
    candidates.append(Path(sys.executable).parent / "app" / "styles.qss")
    # PyInstaller one-file: temporary extraction dir
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "styles.qss")
        candidates.append(Path(meipass) / "styles.qss")
    # Also try next to exe root just in case
    candidates.append(Path(sys.executable).parent / "styles.qss")

    for path in candidates:
        if path and path.exists():
            app.setStyleSheet(path.read_text(encoding="utf-8"))
            break


def load_app_icon(app: QtWidgets.QApplication, window: Optional[QtWidgets.QWidget] = None) -> None:
    # Prefer a custom icon if present
    candidates = []
    # Source tree
    candidates.append(Path(__file__).parent / "assets" / "icon.ico")
    candidates.append(Path(__file__).parent / "icon.ico")
    # Next to executable
    candidates.append(Path(sys.executable).parent / "app" / "assets" / "icon.ico")
    candidates.append(Path(sys.executable).parent / "icon.ico")
    # PyInstaller temp
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "assets" / "icon.ico")
        candidates.append(Path(meipass) / "icon.ico")

    loaded = False
    for path in candidates:
        if path and path.exists():
            icon = QtGui.QIcon(str(path))
            if not icon.isNull():
                app.setWindowIcon(icon)
                if window is not None:
                    window.setWindowIcon(icon)
                loaded = True
                break

    # Fallback: on Windows, try to use the EXE's embedded icon
    if not loaded and sys.platform.startswith("win"):
        exe_icon = QtGui.QIcon(sys.executable)
        if not exe_icon.isNull():
            app.setWindowIcon(exe_icon)
            if window is not None:
                window.setWindowIcon(exe_icon)


def set_windows_appusermodel_id(app_id: str) -> None:
    """On Windows, set an explicit AppUserModelID so the taskbar uses the exe icon
    and groups windows properly. Safe no-op on other platforms."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)  # type: ignore[attr-defined]
    except Exception:
        # Silently ignore if unavailable
        pass


def main() -> None:
    # Set Windows AppUserModelID before any window is created
    set_windows_appusermodel_id("com.fbgrabber.app")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("FBGrabber")
    load_styles(app)

    from app.ui.main_window import MainWindow

    window = MainWindow()
    load_app_icon(app, window)
    settings = AppSettings.load()
    manager = DownloadManager(settings, window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

