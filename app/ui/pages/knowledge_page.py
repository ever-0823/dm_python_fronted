from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class KnowledgeDropZone(QFrame):
    """知识文档拖拽区，只接受 PDF/TXT 文件。"""

    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("AttachmentDropZone")
        self.setProperty("dragActive", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        title = QLabel("拖拽 PDF/TXT 文档到这里")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        hint = QLabel("单个文件最大 20 MB，导入后自动切分并生成向量")
        hint.setObjectName("PageHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # 文件后缀在页面层校验，这里只判断是否为本地文件。
        if any(url.isLocalFile() for url in event.mimeData().urls()):
            self._set_drag_active(True)
            event.acceptProposedAction()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.file_dropped.emit(files[0])
            event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        # 动态属性变化后刷新 QSS，及时反馈当前拖拽状态。
        self.setProperty("dragActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class KnowledgeWorker(QObject):
    """在线程中执行一个知识库网络操作，避免模型推理阻塞界面。"""

    succeeded = Signal(dict)
    failed = Signal(str)
    completed = Signal()

    def __init__(self, operation, *args) -> None:
        super().__init__()
        self.operation = operation
        self.args = args

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self.operation(*self.args))
        except (ApiError, OSError) as exc:
            self.failed.emit(str(exc))
        finally:
            self.completed.emit()


class KnowledgePage(QWidget):
    """知识库文档管理与相似度检索页面。"""

    ALLOWED_SUFFIXES = {".pdf", ".txt"}
    MAX_FILE_BYTES = 20 * 1024 * 1024

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self._thread: QThread | None = None
        self._worker: KnowledgeWorker | None = None
        self._reload_documents = False
        self._build_ui()
        self.load_documents()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.status_label = QLabel("正在加载知识文档。")
        self.status_label.setObjectName("ResultBanner")
        self.status_label.setProperty("status", "info")
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        document_panel = QFrame()
        document_panel.setObjectName("PageCard")
        document_layout = QVBoxLayout(document_panel)
        document_layout.setContentsMargins(18, 18, 18, 18)
        document_layout.setSpacing(12)

        document_header = QHBoxLayout()
        document_title = QLabel("知识文档")
        document_title.setObjectName("SectionTitle")
        document_header.addWidget(document_title)
        document_header.addStretch()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.clicked.connect(self.load_documents)
        document_header.addWidget(self.refresh_button)
        document_layout.addLayout(document_header)

        self.drop_zone = KnowledgeDropZone()
        self.drop_zone.file_dropped.connect(self.import_file)
        document_layout.addWidget(self.drop_zone)

        self.upload_button = QPushButton("选择文档并导入")
        self.upload_button.clicked.connect(self.select_file)
        document_layout.addWidget(self.upload_button)

        self.documents_table = QTableWidget(0, 5)
        # 文档表不需要键盘编辑，关闭焦点框以免文件名周围出现黑色虚线。
        self.documents_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.documents_table.setHorizontalHeaderLabels(["文档名称", "文本块", "大小", "导入人", "操作"])
        self.documents_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.documents_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.documents_table.verticalHeader().setVisible(False)
        header = self.documents_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.documents_table.setColumnWidth(1, 70)
        self.documents_table.setColumnWidth(2, 90)
        self.documents_table.setColumnWidth(3, 100)
        self.documents_table.setColumnWidth(4, 80)
        document_layout.addWidget(self.documents_table, stretch=1)
        splitter.addWidget(document_panel)

        search_panel = QFrame()
        search_panel.setObjectName("PageCard")
        search_layout = QVBoxLayout(search_panel)
        search_layout.setContentsMargins(18, 18, 18, 18)
        search_layout.setSpacing(12)
        search_title = QLabel("知识检索")
        search_title.setObjectName("SectionTitle")
        search_layout.addWidget(search_title)

        query_row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("输入设备维护、故障处理等问题")
        self.query_input.returnPressed.connect(self.search)
        query_row.addWidget(self.query_input, stretch=1)
        self.search_button = QPushButton("检索")
        self.search_button.clicked.connect(self.search)
        query_row.addWidget(self.search_button)
        search_layout.addLayout(query_row)

        self.results_table = QTableWidget(0, 4)
        self.results_table.setHorizontalHeaderLabels(["相似度", "来源文档", "页码", "命中上下文"])
        self.results_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.results_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.results_table.setWordWrap(True)
        self.results_table.verticalHeader().setVisible(False)
        results_header = self.results_table.horizontalHeader()
        results_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        results_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        results_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        results_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnWidth(0, 72)
        self.results_table.setColumnWidth(1, 150)
        self.results_table.setColumnWidth(2, 55)
        search_layout.addWidget(self.results_table, stretch=1)
        splitter.addWidget(search_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([500, 500])
        root.addWidget(splitter, stretch=1)

    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择知识文档", "", "知识文档 (*.pdf *.txt)")
        if file_path:
            self.import_file(file_path)

    def import_file(self, file_path: str) -> None:
        if self._thread is not None:
            return
        path = Path(file_path)
        try:
            if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                raise ValueError("仅支持 PDF、TXT 文档")
            if path.stat().st_size > self.MAX_FILE_BYTES:
                raise ValueError("文档大小不能超过 20 MB")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "文档不可用", str(exc))
            return

        self._set_busy(True, f"正在导入 {path.name}，模型处理可能需要一些时间。")
        # 回调使用关键字传入，避免被当成上传接口的位置参数。
        self._start_worker(
            self.api_client.upload_knowledge_document,
            str(path),
            on_success=self._import_succeeded,
        )

    def load_documents(self) -> None:
        if self._thread is not None:
            return
        self._set_busy(True, "正在加载知识文档。")
        self._start_worker(self.api_client.get_knowledge_documents, on_success=self._documents_loaded)

    def search(self) -> None:
        query = self.query_input.text().strip()
        if not query or self._thread is not None:
            return
        self._set_busy(True, "正在检索相关知识。")
        # 回调通过关键字传入，避免被误当成 search_knowledge 的位置参数。
        self._start_worker(self.api_client.search_knowledge, query, 5, on_success=self._search_succeeded)

    def delete_document(self, document_id: int, name: str) -> None:
        if self._thread is not None:
            return
        result = QMessageBox.question(
            self, "删除知识文档", f"确认删除“{name}”及其全部向量吗？删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._set_busy(True, "正在删除知识文档。")
        # 回调使用关键字传入，避免被当成删除接口的位置参数。
        self._start_worker(
            self.api_client.delete_knowledge_document,
            document_id,
            on_success=self._delete_succeeded,
        )

    def _start_worker(self, operation, *args, on_success=None) -> None:
        # 每个操作使用短生命周期线程，完成后释放线程和 worker，避免界面卡顿。
        self._thread = QThread(self)
        self._worker = KnowledgeWorker(operation, *args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        if on_success:
            self._worker.succeeded.connect(on_success)
        self._worker.failed.connect(self._operation_failed)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(dict)
    def _import_succeeded(self, response: dict) -> None:
        data = response.get("data") or {}
        self._set_status(f"文档导入成功，共生成 {data.get('chunk_count', 0)} 个文本块。", "success")
        # 当前导入线程尚未结束，交给线程完成回调再刷新列表。
        self._reload_documents = True

    @Slot(dict)
    def _documents_loaded(self, response: dict) -> None:
        items = (response.get("data") or {}).get("items") or []
        self.documents_table.setRowCount(len(items))
        for row, document in enumerate(items):
            values = [
                document.get("original_name", ""),
                document.get("chunk_count", 0),
                self._format_size(document.get("size_bytes", 0)),
                document.get("created_by", ""),
            ]
            for column, value in enumerate(values):
                self.documents_table.setItem(row, column, QTableWidgetItem(str(value)))
            delete_button = QPushButton("删除")
            # 操作列使用无边框紧凑按钮，避免普通按钮内边距撑出表格边缘。
            delete_button.setProperty("tableAction", "true")
            delete_button.setFixedWidth(52)
            delete_button.clicked.connect(
                lambda _checked=False, document_id=document.get("id"), name=document.get("original_name", ""): self.delete_document(document_id, name)
            )
            self.documents_table.setCellWidget(row, 4, delete_button)
        if not items:
            self._set_status("暂无知识文档，请先上传 PDF 或 TXT。", "info")
        else:
            self._set_status(f"已加载 {len(items)} 个知识文档。", "success")

    @Slot(dict)
    def _search_succeeded(self, response: dict) -> None:
        items = (response.get("data") or {}).get("items") or []
        self.results_table.setRowCount(len(items))
        for row, item in enumerate(items):
            values = [
                f"{float(item.get('score', 0)) * 100:.1f}%",
                item.get("original_name", ""),
                item.get("page_number", "-"),
                item.get("context") or item.get("content", ""),
            ]
            for column, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setToolTip(str(value))
                if column < 3:
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.results_table.setItem(row, column, cell)
        self._set_status(f"检索完成，返回 {len(items)} 条相关内容。", "success")

    @Slot(dict)
    def _delete_succeeded(self, _response: dict) -> None:
        self._set_status("知识文档已删除。", "success")
        # 当前删除线程尚未结束，交给线程完成回调再刷新列表。
        self._reload_documents = True

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self._set_status(message, "error")
        QMessageBox.critical(self, "知识库操作失败", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)
        if self._reload_documents:
            self._reload_documents = False
            self.load_documents()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        for widget in (self.upload_button, self.refresh_button, self.search_button, self.query_input):
            widget.setEnabled(not busy)
        if message:
            self._set_status(message, "loading")

    def _set_status(self, message: str, status: str) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("status", status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _format_size(self, value: int) -> str:
        size = float(value or 0)
        if size < 1024:
            return f"{size:.0f} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        return f"{size / 1024 / 1024:.1f} MB"
