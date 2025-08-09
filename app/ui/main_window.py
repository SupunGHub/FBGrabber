from __future__ import annotations

from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from app.models import FormatOption, QueueItem, QueueStatus


class MainWindow(QtWidgets.QMainWindow):
    requestFetchFormats = QtCore.Signal(str)
    # url, selected_format_id (or None), title, quality_text
    requestAddToQueue = QtCore.Signal(str, object, str, str)
    # Context actions
    requestOpenItemFile = QtCore.Signal(int)
    requestOpenItemFolder = QtCore.Signal(int)
    requestCopyItemUrl = QtCore.Signal(int)
    requestCopyItemOutputPath = QtCore.Signal(int)
    requestRetryItem = QtCore.Signal(int)
    requestRemoveItem = QtCore.Signal(int)
    requestChooseDownloadDir = QtCore.Signal()
    requestChooseCookiesFile = QtCore.Signal()
    requestOpenDownloadDir = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FBGrabber")
        self.resize(1100, 700)

        self._build_menu()
        self._build_ui()

        self._formats: List[FormatOption] = []
        self._title_for_url: str = ""

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

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget(self)
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # URL + Fetch
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.url_edit = QtWidgets.QLineEdit()
        self.url_edit.setPlaceholderText("Paste Facebook video URL...")
        self.fetch_btn = QtWidgets.QPushButton("Fetch")
        self.fetch_btn.clicked.connect(self._on_fetch_clicked)
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.fetch_btn, 0)
        layout.addLayout(row)

        # Formats selector
        fmt_group = QtWidgets.QGroupBox("Available Qualities")
        fmt_layout = QtWidgets.QHBoxLayout(fmt_group)
        fmt_layout.setContentsMargins(12, 8, 12, 8)
        self.format_combo = QtWidgets.QComboBox()
        self.format_combo.setEnabled(False)
        self.add_btn = QtWidgets.QPushButton("Add to Queue")
        self.add_btn.setEnabled(False)
        self.add_btn.clicked.connect(self._on_add_clicked)
        fmt_layout.addWidget(self.format_combo, 1)
        fmt_layout.addWidget(self.add_btn, 0)
        layout.addWidget(fmt_group)

        # Queue table
        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "Title", "Quality", "Status", "Progress", "Speed", "ETA", "Output"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for col, w in enumerate([260, 140, 120, 120, 100, 80, 300]):
            self.table.setColumnWidth(col, w)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)

        layout.addWidget(self.table, 1)

        # Actions row
        actions = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.cancel_btn = QtWidgets.QPushButton("Cancel Selected")
        actions.addStretch(1)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.cancel_btn)
        layout.addLayout(actions)

    # UI events
    def _on_fetch_clicked(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self.format_combo.clear()
        self.format_combo.setEnabled(False)
        self.add_btn.setEnabled(False)
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
        # Determine quality display text
        if selected_format_id is None:
            quality_text = "Best available"
        else:
            quality_text = self._formats[idx].display_text()
        self.requestAddToQueue.emit(url, selected_format_id, title, quality_text)

    # External updates
    def set_formats(self, title: str, formats: List[FormatOption]) -> None:
        self._title_for_url = title
        self._formats = formats
        self.format_combo.clear()
        for f in formats:
            self.format_combo.addItem(f.display_text())
        self.format_combo.setEnabled(bool(formats))
        self.add_btn.setEnabled(bool(formats))

    def add_queue_row(self, item: QueueItem, quality_text: str) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        title_item = QtWidgets.QTableWidgetItem(item.title)
        # Store item id for later retrieval in context menu
        title_item.setData(QtCore.Qt.UserRole, item.id)
        self.table.setItem(row, 0, title_item)
        self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(quality_text))
        self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(item.status.value))
        self.table.setItem(row, 3, QtWidgets.QTableWidgetItem("0%"))
        self.table.setItem(row, 4, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(""))
        self.table.setItem(row, 6, QtWidgets.QTableWidgetItem(""))
        return row

    def update_progress_row(self, row: int, percent: float, speed: str, eta: str, status: str) -> None:
        self.table.item(row, 2).setText(status)
        self.table.item(row, 3).setText(f"{percent:.1f}%")
        self.table.item(row, 4).setText(speed)
        self.table.item(row, 5).setText(eta)

    def mark_row_finished(self, row: int, output_path: str, success: bool, error_message: str | None) -> None:
        self.table.item(row, 2).setText("Completed" if success else "Failed")
        self.table.item(row, 3).setText("100%" if success else "")
        self.table.item(row, 6).setText(output_path if success else (error_message or ""))

    # Context menu
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

