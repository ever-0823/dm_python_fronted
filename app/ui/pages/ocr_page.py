from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class OcrDropZone(QFrame):
    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("OcrDropZone")
        self.setProperty("dragActive", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("拖拽图片到这里")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        hint = QLabel("支持 JPG、PNG、BMP、WEBP，最大 10 MB")
        hint.setObjectName("PageHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # 只接收一个本地文件，文件格式在页面层统一校验。
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        local_files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if local_files:
            self.file_dropped.emit(local_files[0])
            event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        # 动态属性变化后刷新控件，立即显示拖拽高亮状态。
        self.setProperty("dragActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class OcrWorker(QObject):
    succeeded = Signal(dict)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, api_client: ApiClient, file_path: str) -> None:
        super().__init__()
        self.api_client = api_client
        self.file_path = file_path

    @Slot()
    def run(self) -> None:
        # 网络请求放到工作线程，避免模型推理期间阻塞界面。
        try:
            self.succeeded.emit(self.api_client.recognize_image(self.file_path))
        except (ApiError, OSError) as exc:
            self.failed.emit(str(exc))
        finally:
            self.completed.emit()


class OcrPage(QWidget):
    ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    MAX_FILE_BYTES = 10 * 1024 * 1024

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.file_path = ""
        self._thread: QThread | None = None
        self._worker: OcrWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.status_label = QLabel("请选择一张图片开始识别。")
        self.status_label.setObjectName("ResultBanner")
        self.status_label.setProperty("status", "info")
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        source_panel = QFrame()
        source_panel.setObjectName("PageCard")
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(18, 18, 18, 18)
        source_layout.setSpacing(12)

        source_title = QLabel("待识别图片")
        source_title.setObjectName("SectionTitle")
        source_layout.addWidget(source_title)

        self.drop_zone = OcrDropZone()
        self.drop_zone.file_dropped.connect(self._set_file)
        source_layout.addWidget(self.drop_zone)

        self.preview_label = QLabel("暂无图片")
        self.preview_label.setObjectName("OcrPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(320, 280)
        source_layout.addWidget(self.preview_label, stretch=1)

        self.file_label = QLabel("未选择文件")
        self.file_label.setObjectName("AttachmentFile")
        self.file_label.setWordWrap(True)
        source_layout.addWidget(self.file_label)

        source_actions = QHBoxLayout()
        self.select_button = QPushButton("选择图片")
        self.select_button.clicked.connect(self.select_file)
        source_actions.addWidget(self.select_button)
        self.clear_button = QPushButton("清空")
        self.clear_button.setProperty("variant", "secondary")
        self.clear_button.clicked.connect(self.clear)
        source_actions.addWidget(self.clear_button)
        source_actions.addStretch()
        source_layout.addLayout(source_actions)
        splitter.addWidget(source_panel)

        result_panel = QFrame()
        result_panel.setObjectName("PageCard")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(18, 18, 18, 18)
        result_layout.setSpacing(12)

        result_header = QHBoxLayout()
        result_title = QLabel("识别结果")
        result_title.setObjectName("SectionTitle")
        result_header.addWidget(result_title)
        result_header.addStretch()
        self.result_summary = QLabel("0 行")
        self.result_summary.setObjectName("PageHint")
        result_header.addWidget(self.result_summary)
        result_layout.addLayout(result_header)

        tabs = QTabWidget()
        self.text_result = QPlainTextEdit()
        self.text_result.setReadOnly(True)
        self.text_result.setPlaceholderText("识别文本将在这里显示")
        tabs.addTab(self.text_result, "识别文本")

        self.lines_table = QTableWidget(0, 2)
        self.lines_table.setHorizontalHeaderLabels(["文本", "置信度"])
        self.lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.verticalHeader().setVisible(False)
        self.lines_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.lines_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.lines_table.setColumnWidth(1, 100)
        tabs.addTab(self.lines_table, "逐行结果")
        result_layout.addWidget(tabs, stretch=1)

        result_actions = QHBoxLayout()
        self.recognize_button = QPushButton("开始识别")
        self.recognize_button.setEnabled(False)
        self.recognize_button.clicked.connect(self.recognize)
        result_actions.addWidget(self.recognize_button)
        self.copy_button = QPushButton("复制全文")
        self.copy_button.setProperty("variant", "secondary")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_text)
        result_actions.addWidget(self.copy_button)
        result_actions.addStretch()
        result_layout.addLayout(result_actions)
        splitter.addWidget(result_panel)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([400, 600])
        root.addWidget(splitter, stretch=1)

    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择待识别图片",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp)",
        )
        if file_path:
            self._set_file(file_path)

    def _set_file(self, file_path: str) -> None:
        if self._thread is not None:
            return
        path = Path(file_path)
        try:
            if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                raise ValueError("仅支持 JPG、PNG、BMP、WEBP 图片")
            if path.stat().st_size > self.MAX_FILE_BYTES:
                raise ValueError("图片大小不能超过 10 MB")
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                raise ValueError("图片无法读取或文件已损坏")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "图片不可用", str(exc))
            return

        # 预览按固定区域等比缩放，避免大图改变左右面板尺寸。
        self.file_path = str(path)
        self.preview_label.setPixmap(
            pixmap.scaled(420, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self.file_label.setText(f"{path.name}  |  {path.stat().st_size / 1024:.1f} KB")
        self.recognize_button.setEnabled(True)
        self._set_status("图片已就绪，可以开始识别。", "info")

    def recognize(self) -> None:
        if not self.file_path or self._thread is not None:
            return

        self.recognize_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.select_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self._set_status("正在识别，请稍候...", "loading")

        # 每次请求创建一个短生命周期线程，完成后由 Qt 自动回收。
        self._thread = QThread(self)
        self._worker = OcrWorker(self.api_client, self.file_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.succeeded.connect(self._show_result)
        self._worker.failed.connect(self._show_error)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(dict)
    def _show_result(self, response: dict) -> None:
        data = response.get("data") or {}
        text = str(data.get("text") or "")
        lines = data.get("lines") or []
        self.text_result.setPlainText(text)
        self.lines_table.setRowCount(len(lines))

        for row, line in enumerate(lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(str(line.get("text") or "")))
            score = line.get("score")
            score_text = "-" if score is None else f"{float(score) * 100:.1f}%"
            score_item = QTableWidgetItem(score_text)
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(row, 1, score_item)

        self.result_summary.setText(f"{len(lines)} 行")
        self.copy_button.setEnabled(bool(text))
        message = "识别完成。" if lines else "识别完成，未检测到文字。"
        self._set_status(message, "success")

    @Slot(str)
    def _show_error(self, message: str) -> None:
        self._set_status(f"识别失败：{message}", "error")
        QMessageBox.critical(self, "识别失败", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self.recognize_button.setEnabled(bool(self.file_path))
        self.select_button.setEnabled(True)
        self.clear_button.setEnabled(True)

    def copy_text(self) -> None:
        text = self.text_result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._set_status("识别文本已复制到剪贴板。", "success")

    def clear(self) -> None:
        if self._thread is not None:
            return
        self.file_path = ""
        self.preview_label.clear()
        self.preview_label.setText("暂无图片")
        self.file_label.setText("未选择文件")
        self.text_result.clear()
        self.lines_table.setRowCount(0)
        self.result_summary.setText("0 行")
        self.recognize_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self._set_status("请选择一张图片开始识别。", "info")

    def _set_status(self, message: str, status: str) -> None:
        # 识别状态复用全局结果横幅颜色，保持各业务页面反馈一致。
        self.status_label.setText(message)
        self.status_label.setProperty("status", status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
