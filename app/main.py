from __future__ import annotations

import os
import sys
import tempfile
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
                self.ui.reset_fetch_button()
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
            self.ui.set_download_dir_display(str(self.settings.download_dir))

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


def _generate_combo_arrow(dark: bool) -> str:
    """Create a small chevron-down PNG for the combo box and return its path."""
    pm = QtGui.QPixmap(20, 12)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    color = QtGui.QColor(255, 255, 255, 180) if dark else QtGui.QColor(0, 0, 0, 140)
    pen = QtGui.QPen(color, 2.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin)
    p.setPen(pen)
    p.drawLine(QtCore.QPointF(4, 3), QtCore.QPointF(10, 9))
    p.drawLine(QtCore.QPointF(10, 9), QtCore.QPointF(16, 3))
    p.end()

    arrow_path = os.path.join(tempfile.gettempdir(), "fbgrabber_combo_arrow.png")
    pm.save(arrow_path, "PNG")
    return arrow_path


_LIGHT_VARS: Dict[str, str] = {
    "bg_window": "#F5F5F7",
    "text_primary": "#1D1D1F",
    "text_secondary": "#6E6E73",
    "text_tertiary": "#AEAEB2",
    "text_muted": "#AEAEB2",
    "text_header": "#8E8E93",
    "badge_text": "white",
    "badge_bg": "#8E8E93",
    "border": "#D2D2D7",
    "border_light": "#E5E5EA",
    "border_faint": "rgba(0, 0, 0, 0.06)",
    "border_subtle": "#E5E5EA",
    "bg_input": "#FFFFFF",
    "bg_button": "#FFFFFF",
    "bg_button_hover": "#F5F5F7",
    "bg_button_pressed": "#E8E8ED",
    "bg_button_disabled": "#F5F5F7",
    "bg_card": "#FFFFFF",
    "bg_menu": "rgba(255, 255, 255, 0.95)",
    "bg_tooltip": "rgba(255, 255, 255, 0.95)",
    "alt_row": "rgba(0, 0, 0, 0.02)",
    "selection_bg": "rgba(0, 113, 227, 0.12)",
    "hover_bg": "rgba(0, 0, 0, 0.04)",
    "progress_track": "#E5E5EA",
    "scrollbar": "rgba(0, 0, 0, 0.15)",
    "scrollbar_hover": "rgba(0, 0, 0, 0.30)",
    "menu_sep": "#E5E5EA",
    "separator": "#E5E5EA",
    "status_dir": "#8E8E93",
}

_DARK_VARS: Dict[str, str] = {
    "bg_window": "#1C1C1E",
    "text_primary": "#F5F5F7",
    "text_secondary": "#98989D",
    "text_tertiary": "#636366",
    "text_muted": "#636366",
    "text_header": "#98989D",
    "badge_text": "white",
    "badge_bg": "#636366",
    "border": "#38383A",
    "border_light": "#38383A",
    "border_faint": "rgba(255, 255, 255, 0.06)",
    "border_subtle": "#38383A",
    "bg_input": "#1C1C1E",
    "bg_button": "#2C2C2E",
    "bg_button_hover": "#3A3A3C",
    "bg_button_pressed": "#48484A",
    "bg_button_disabled": "#2C2C2E",
    "bg_card": "#1C1C1E",
    "bg_menu": "rgba(44, 44, 46, 0.95)",
    "bg_tooltip": "rgba(44, 44, 46, 0.95)",
    "alt_row": "rgba(255, 255, 255, 0.03)",
    "selection_bg": "rgba(0, 113, 227, 0.25)",
    "hover_bg": "rgba(255, 255, 255, 0.06)",
    "progress_track": "#38383A",
    "scrollbar": "rgba(255, 255, 255, 0.20)",
    "scrollbar_hover": "rgba(255, 255, 255, 0.35)",
    "menu_sep": "#38383A",
    "separator": "#38383A",
    "status_dir": "#98989D",
}


def _find_qss_file(qss_file: str) -> Optional[str]:
    """Locate the QSS file across source tree and PyInstaller bundles."""
    candidates = [
        Path(__file__).parent / qss_file,
        Path(sys.executable).parent / "app" / qss_file,
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / qss_file)
        candidates.append(Path(meipass) / qss_file)
    candidates.append(Path(sys.executable).parent / qss_file)

    for path in candidates:
        if path and path.exists():
            return path.read_text(encoding="utf-8")
    return None


def _apply_palette(app: QtWidgets.QApplication, is_dark: bool) -> None:
    """Set the application palette for dark or light mode."""
    pal = app.palette()
    if is_dark:
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#1C1C1E"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2C2C2E"))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#38383A"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#2C2C2E"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#0071E3"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#FFFFFF"))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#2C2C2E"))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor("#636366"))
        pal.setColor(QtGui.QPalette.Mid, QtGui.QColor("#38383A"))
        pal.setColor(QtGui.QPalette.Dark, QtGui.QColor("#1C1C1E"))
        pal.setColor(QtGui.QPalette.Shadow, QtGui.QColor("#000000"))
    else:
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#1D1D1F"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#FFFFFF"))
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#F5F5F7"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#1D1D1F"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#FFFFFF"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#1D1D1F"))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#0071E3"))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#FFFFFF"))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor("#FFFFFF"))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor("#1D1D1F"))
        pal.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor("#AEAEB2"))
        pal.setColor(QtGui.QPalette.Mid, QtGui.QColor("#D2D2D7"))
        pal.setColor(QtGui.QPalette.Dark, QtGui.QColor("#8E8E93"))
        pal.setColor(QtGui.QPalette.Shadow, QtGui.QColor("#000000"))
    app.setPalette(pal)


def load_styles(app: QtWidgets.QApplication, force_dark: Optional[bool] = None) -> None:
    qss_file = "styles_macos.qss" if sys.platform == "darwin" else "styles.qss"
    qss_text = _find_qss_file(qss_file)
    if not qss_text:
        return

    # On macOS, substitute @var@ placeholders and apply palette for light/dark mode
    if sys.platform == "darwin":
        if force_dark is not None:
            is_dark = force_dark
        else:
            is_dark = app.palette().color(QtGui.QPalette.Window).lightness() < 128

        _apply_palette(app, is_dark)

        variables = _DARK_VARS if is_dark else _LIGHT_VARS
        arrow_path = _generate_combo_arrow(is_dark)
        variables = {**variables, "arrow_path": arrow_path}

        for key, value in variables.items():
            qss_text = qss_text.replace(f"@{key}@", value)

    app.setStyleSheet(qss_text)


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


def _resolve_dark(settings: AppSettings, app: QtWidgets.QApplication) -> bool:
    """Determine whether the app should be in dark mode."""
    if settings.theme == "dark":
        return True
    if settings.theme == "light":
        return False
    # "system" — detect from palette
    return app.palette().color(QtGui.QPalette.Window).lightness() < 128


def main() -> None:
    # Set Windows AppUserModelID before any window is created
    set_windows_appusermodel_id("com.fbgrabber.app")

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("FBGrabber")
    # Use Fusion style for reliable QSS/palette support on all platforms
    app.setStyle("Fusion")

    settings = AppSettings.load()
    is_dark = _resolve_dark(settings, app)
    load_styles(app, force_dark=is_dark)

    from app.ui.main_window import MainWindow

    window = MainWindow()
    load_app_icon(app, window)
    window.set_theme_icon(is_dark)
    window.set_brand_logo(is_dark)

    def toggle_theme() -> None:
        nonlocal is_dark
        is_dark = not is_dark
        settings.theme = "dark" if is_dark else "light"
        settings.save()
        app.setStyleSheet("")
        load_styles(app, force_dark=is_dark)
        window.set_theme_icon(is_dark)
        window.set_brand_logo(is_dark)

    window.requestToggleTheme.connect(toggle_theme)

    manager = DownloadManager(settings, window)
    window.set_download_dir_display(str(settings.download_dir))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

