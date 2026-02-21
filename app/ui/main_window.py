from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.models import FormatOption, QueueItem, QueueStatus

_STATUS_COLORS = {
    "Pending": "#8E8E93",
    "Queued": "#8E8E93",
    "Ready": "#8E8E93",
    "Downloading": "#0071E3",
    "Processing": "#FF9F0A",
    "Completed": "#34C759",
    "Failed": "#FF3B30",
    "Canceled": "#8E8E93",
}


class MainWindow(QtWidgets.QMainWindow):
    requestFetchFormats = QtCore.Signal(str)
    requestAddToQueue = QtCore.Signal(str, object, str, str)
    requestOpenItemFile = QtCore.Signal(int)
    requestOpenItemFolder = QtCore.Signal(int)
    requestCopyItemUrl = QtCore.Signal(int)
    requestCopyItemOutputPath = QtCore.Signal(int)
    requestRetryItem = QtCore.Signal(int)
    requestRemoveItem = QtCore.Signal(int)
    requestChooseDownloadDir = QtCore.Signal()
    requestChooseCookiesFile = QtCore.Signal()
    requestOpenDownloadDir = QtCore.Signal()
    requestToggleTheme = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FBGrabber")
        self.resize(960, 680)

        self._build_menu()
        self._build_ui()
        self._build_status_bar()

        self._formats: List[FormatOption] = []
        self._title_for_url: str = ""

    # ── Menu ────────────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        act_choose_dir = QtGui.QAction("Choose Download Folder", self)
        act_choose_dir.triggered.connect(self.requestChooseDownloadDir.emit)
        file_menu.addAction(act_choose_dir)

        act_cookies = QtGui.QAction("Select Cookies File", self)
        act_cookies.triggered.connect(self.requestChooseCookiesFile.emit)
        file_menu.addAction(act_cookies)

        act_open_dir = QtGui.QAction("Open Download Folder", self)
        act_open_dir.triggered.connect(self.requestOpenDownloadDir.emit)
        file_menu.addAction(act_open_dir)

        file_menu.addSeparator()
        act_exit = QtGui.QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

    # ── Main UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(0)

        # ── URL + Fetch (same layout as body for perfect alignment) ─────────

        url_row = QtWidgets.QHBoxLayout()
        url_row.setSpacing(10)
        self.url_edit = QtWidgets.QLineEdit()
        self.url_edit.setPlaceholderText("Paste a Facebook video URL...")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.textChanged.connect(self._on_url_changed)
        self.fetch_btn = QtWidgets.QPushButton("Fetch")
        self.fetch_btn.setObjectName("accentBtn")
        self.fetch_btn.setMinimumWidth(110)
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.fetch_btn)
        layout.addLayout(url_row)

        layout.addSpacing(10)

        # ── Video title (hidden until fetched) ──────────────────────────────

        self._video_title_label = QtWidgets.QLabel("")
        self._video_title_label.setObjectName("videoTitleLabel")
        self._video_title_label.setWordWrap(True)
        self._video_title_label.setVisible(False)
        layout.addWidget(self._video_title_label)
        layout.addSpacing(6)

        # ── Quality + action button (hidden until fetched) ──────────────────

        self._fmt_container = QtWidgets.QWidget()
        self._fmt_container.setVisible(False)
        fmt_row = QtWidgets.QHBoxLayout(self._fmt_container)
        fmt_row.setContentsMargins(0, 0, 0, 0)
        fmt_row.setSpacing(10)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.setView(QtWidgets.QListView())
        self.format_combo.setMaxVisibleItems(10)
        self.add_btn = QtWidgets.QPushButton("Start Download")
        self.add_btn.setObjectName("accentBtn")
        self.add_btn.setMinimumWidth(150)
        self.add_btn.clicked.connect(self._on_add_clicked)
        fmt_row.addWidget(self.format_combo, 1)
        fmt_row.addWidget(self.add_btn)
        layout.addWidget(self._fmt_container)

        layout.addSpacing(20)

        # ── Download Queue header ───────────────────────────────────────────

        queue_header = QtWidgets.QHBoxLayout()
        self._queue_label = QtWidgets.QLabel("Download Queue")
        self._queue_label.setObjectName("sectionLabel")
        self._queue_count = QtWidgets.QLabel("0")
        self._queue_count.setObjectName("countBadge")
        self._queue_count.setVisible(False)
        queue_header.addWidget(self._queue_label)
        queue_header.addSpacing(6)
        queue_header.addWidget(self._queue_count)
        queue_header.addStretch(1)
        self.cancel_btn = QtWidgets.QPushButton("Cancel Selected")
        self.cancel_btn.setEnabled(False)
        queue_header.addWidget(self.cancel_btn)
        layout.addLayout(queue_header)

        layout.addSpacing(10)

        # ── Queue table ────────────────────────────────────────────────────

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setObjectName("queueTable")
        self.table.setHorizontalHeaderLabels([
            "Title", "Quality", "Status", "Progress", "Speed", "ETA", "Output",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        for col, w in enumerate([220, 120, 120, 140, 80, 60, 200]):
            self.table.setColumnWidth(col, w)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        # ── Empty state ─────────────────────────────────────────────────────

        empty_widget = QtWidgets.QWidget()
        empty_widget.setObjectName("emptyState")
        empty_layout = QtWidgets.QVBoxLayout(empty_widget)
        empty_layout.setAlignment(QtCore.Qt.AlignCenter)

        is_dark = self.palette().color(QtGui.QPalette.Window).lightness() < 128
        empty_icon_label = QtWidgets.QLabel()
        empty_icon_label.setPixmap(self._download_icon_pixmap(is_dark))
        empty_icon_label.setAlignment(QtCore.Qt.AlignCenter)

        empty_title = QtWidgets.QLabel("Ready to download")
        empty_title.setObjectName("emptyTitle")
        empty_title.setAlignment(QtCore.Qt.AlignCenter)

        empty_subtitle = QtWidgets.QLabel(
            "Paste a Facebook video URL above, then choose your quality"
        )
        empty_subtitle.setObjectName("emptySubtitle")
        empty_subtitle.setAlignment(QtCore.Qt.AlignCenter)

        empty_layout.addWidget(empty_icon_label)
        empty_layout.addSpacing(16)
        empty_layout.addWidget(empty_title)
        empty_layout.addSpacing(4)
        empty_layout.addWidget(empty_subtitle)

        # ── Stacked: 0 = empty, 1 = table ──────────────────────────────────

        self._stack = QtWidgets.QStackedWidget()
        self._stack.setObjectName("queueStack")
        self._stack.addWidget(empty_widget)
        self._stack.addWidget(self.table)
        self._stack.setCurrentIndex(0)
        layout.addWidget(self._stack, 1)

        self.table.model().rowsInserted.connect(self._update_queue_state)
        self.table.model().rowsRemoved.connect(self._update_queue_state)

    # ── Status bar ──────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        sb = QtWidgets.QStatusBar()
        sb.setObjectName("appStatusBar")
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)

        # Theme toggle (left side)
        self._theme_btn = QtWidgets.QPushButton()
        self._theme_btn.setObjectName("themeToggleBtn")
        self._theme_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._theme_btn.setToolTip("Toggle light/dark mode")
        self._theme_btn.clicked.connect(self.requestToggleTheme.emit)
        sb.addWidget(self._theme_btn)

        self._dir_label = QtWidgets.QLabel("")
        self._dir_label.setObjectName("statusDirLabel")
        sb.addPermanentWidget(self._dir_label)

        # 88techie branding (right side of status bar)
        self._brand_logo = QtWidgets.QLabel()
        self._brand_logo.setObjectName("brandLogo")
        self._brand_logo.setFixedHeight(16)
        self._brand_logo.setToolTip("Built by 88techie")
        self._brand_logo.setCursor(QtCore.Qt.PointingHandCursor)
        sb.addPermanentWidget(self._brand_logo)

    def set_brand_logo(self, is_dark: bool) -> None:
        """Update 88techie logo in status bar for current theme."""
        suffix = "-dark" if is_dark else ""
        candidates = [
            Path(__file__).parent.parent / "assets" / f"88techie{suffix}.svg",
        ]
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "app" / "assets" / f"88techie{suffix}.svg")

        for path in candidates:
            if path.exists():
                pm = QtGui.QPixmap(str(path))
                if not pm.isNull():
                    scaled = pm.scaledToHeight(
                        16, QtCore.Qt.SmoothTransformation
                    )
                    self._brand_logo.setPixmap(scaled)
                    return

    def set_theme_icon(self, is_dark: bool) -> None:
        """Update the theme toggle button to reflect current mode."""
        if is_dark:
            self._theme_btn.setText("Light Mode")
        else:
            self._theme_btn.setText("Dark Mode")

    def set_download_dir_display(self, path: str) -> None:
        display = path
        home = str(Path.home())
        if display.startswith(home):
            display = "~" + display[len(home):]
        if len(display) > 60:
            display = "\u2026" + display[-57:]
        self._dir_label.setText(f"Saving to: {display}")

    # ── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _status_icon(color_hex: str) -> QtGui.QIcon:
        pm = QtGui.QPixmap(10, 10)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor(color_hex))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)
        p.end()
        return QtGui.QIcon(pm)

    @staticmethod
    def _download_icon_pixmap(dark: bool = False) -> QtGui.QPixmap:
        size = 96
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        alpha = 35 if dark else 22
        p.setBrush(QtGui.QColor(0, 113, 227, alpha))
        p.setPen(QtCore.Qt.NoPen)
        p.drawEllipse(0, 0, size, size)

        pen = QtGui.QPen(
            QtGui.QColor(0, 113, 227), 3.0,
            QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin,
        )
        p.setPen(pen)
        cx = size / 2.0
        p.drawLine(QtCore.QPointF(cx, 26), QtCore.QPointF(cx, 56))
        p.drawLine(QtCore.QPointF(cx - 12, 47), QtCore.QPointF(cx, 56))
        p.drawLine(QtCore.QPointF(cx + 12, 47), QtCore.QPointF(cx, 56))
        p.drawLine(QtCore.QPointF(cx - 20, 68), QtCore.QPointF(cx + 20, 68))

        p.end()
        return pm

    def _update_queue_state(self) -> None:
        count = self.table.rowCount()
        if count == 0:
            self._queue_count.setVisible(False)
            self.add_btn.setText("Start Download")
        else:
            self._queue_count.setVisible(True)
            self._queue_count.setText(str(count))
            self.add_btn.setText("Add to Queue")
        self._stack.setCurrentIndex(1 if count > 0 else 0)
        self.cancel_btn.setEnabled(count > 0)

    def _set_status_cell(self, row: int, status_text: str) -> None:
        item = self.table.item(row, 2)
        item.setText(status_text)
        color = _STATUS_COLORS.get(status_text, "#8E8E93")
        item.setIcon(self._status_icon(color))

    # ── UI events ───────────────────────────────────────────────────────────

    def _on_url_changed(self, text: str) -> None:
        if not text.strip():
            self._fmt_container.setVisible(False)
            self._video_title_label.setVisible(False)
            self._formats.clear()
            self.format_combo.clear()

    def _on_fetch_clicked(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.format_combo.clear()
        self._fmt_container.setVisible(False)
        self._video_title_label.setVisible(False)
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching\u2026")
        self.requestFetchFormats.emit(url)

    def _on_add_clicked(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        idx = self.format_combo.currentIndex()
        selected_format_id: Optional[str] = None
        title = self._title_for_url or "Facebook Video"
        if idx >= 0 and idx < len(self._formats):
            selected_format_id = self._formats[idx].format_id
        if selected_format_id is None:
            quality_text = "Best available"
        else:
            quality_text = self._formats[idx].display_text()
        self.requestAddToQueue.emit(url, selected_format_id, title, quality_text)

    # ── External updates ────────────────────────────────────────────────────

    def set_formats(self, title: str, formats: List[FormatOption]) -> None:
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch")
        self._title_for_url = title
        self._formats = formats
        self.format_combo.clear()

        # Detect duplicate display texts and disambiguate with format_id
        texts = [f.display_text() for f in formats]
        seen: dict[str, int] = {}
        for i, t in enumerate(texts):
            seen[t] = seen.get(t, 0) + 1
        dupes = {t for t, c in seen.items() if c > 1}
        for i, f in enumerate(formats):
            label = texts[i]
            if label in dupes:
                label = f"{label} (#{f.format_id})"
            self.format_combo.addItem(label)
        has_formats = bool(formats)
        self._fmt_container.setVisible(has_formats)
        self._video_title_label.setVisible(has_formats)
        if has_formats:
            self._video_title_label.setText(title)
            if self.table.rowCount() == 0:
                self.add_btn.setText("Start Download")
            else:
                self.add_btn.setText("Add to Queue")

    def reset_fetch_button(self) -> None:
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Fetch")

    def add_queue_row(self, item: QueueItem, quality_text: str) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)

        title_item = QtWidgets.QTableWidgetItem(item.title)
        title_item.setData(QtCore.Qt.UserRole, item.id)
        self.table.setItem(row, 0, title_item)
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(quality_text))

        status_text = item.status.value
        status_item = QtWidgets.QTableWidgetItem(status_text)
        color = _STATUS_COLORS.get(status_text, "#8E8E93")
        status_item.setIcon(self._status_icon(color))
        self.table.setItem(row, 2, status_item)

        progress_container = QtWidgets.QWidget()
        progress_container.setObjectName("progressCell")
        pl = QtWidgets.QHBoxLayout(progress_container)
        pl.setContentsMargins(8, 0, 8, 0)
        pl.setSpacing(8)
        progress_bar = QtWidgets.QProgressBar()
        progress_bar.setRange(0, 1000)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedHeight(4)
        progress_label = QtWidgets.QLabel("0%")
        progress_label.setObjectName("progressLabel")
        progress_label.setFixedWidth(36)
        progress_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        pl.addWidget(progress_bar, 1)
        pl.addWidget(progress_label, 0)
        self.table.setCellWidget(row, 3, progress_container)

        mono = QtGui.QFont("SF Mono", 11)
        mono.setStyleHint(QtGui.QFont.Monospace)
        speed_item = QtWidgets.QTableWidgetItem("")
        speed_item.setFont(mono)
        self.table.setItem(row, 4, speed_item)
        eta_item = QtWidgets.QTableWidgetItem("")
        eta_item.setFont(mono)
        self.table.setItem(row, 5, eta_item)

        self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(""))
        return row

    def update_progress_row(self, row: int, percent: float, speed: str, eta: str, status: str) -> None:
        self._set_status_cell(row, status)
        container = self.table.cellWidget(row, 3)
        if container:
            bar = container.findChild(QtWidgets.QProgressBar)
            label = container.findChild(QtWidgets.QLabel)
            if bar:
                bar.setValue(int(percent * 10))
            if label:
                label.setText(f"{percent:.0f}%")
        self.table.item(row, 4).setText(speed)
        self.table.item(row, 5).setText(eta)

    def mark_row_finished(self, row: int, output_path: str, success: bool, error_message: str | None) -> None:
        status_text = "Completed" if success else "Failed"
        self._set_status_cell(row, status_text)
        container = self.table.cellWidget(row, 3)
        if container:
            bar = container.findChild(QtWidgets.QProgressBar)
            label = container.findChild(QtWidgets.QLabel)
            if bar:
                bar.setValue(1000 if success else bar.value())
            if label:
                label.setText("Done" if success else "")
        self.table.item(row, 6).setText(output_path if success else (error_message or ""))

    # ── Context menu ────────────────────────────────────────────────────────

    def _on_table_context_menu(self, pos: QtCore.QPoint) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        id_item = self.table.item(row, 0)
        if id_item is None:
            return
        item_id = id_item.data(QtCore.Qt.UserRole)
        if item_id is None:
            return

        menu = QtWidgets.QMenu(self)
        act_open_file = menu.addAction("Open File")
        act_open_folder = menu.addAction("Open Containing Folder")
        menu.addSeparator()
        act_copy_url = menu.addAction("Copy URL")
        act_copy_out = menu.addAction("Copy Output Path")
        menu.addSeparator()
        act_retry = menu.addAction("Retry")
        act_remove = menu.addAction("Remove from List")

        action = menu.exec(self.table.viewport().mapToGlobal(pos))
        if action is None:
            return
        if action == act_open_file:
            self.requestOpenItemFile.emit(int(item_id))
        elif action == act_open_folder:
            self.requestOpenItemFolder.emit(int(item_id))
        elif action == act_copy_url:
            self.requestCopyItemUrl.emit(int(item_id))
        elif action == act_copy_out:
            self.requestCopyItemOutputPath.emit(int(item_id))
        elif action == act_retry:
            self.requestRetryItem.emit(int(item_id))
        elif action == act_remove:
            self.requestRemoveItem.emit(int(item_id))
