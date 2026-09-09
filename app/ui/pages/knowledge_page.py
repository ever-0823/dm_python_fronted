from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
import qtawesome as qta

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


def _format_file_size(value: int) -> str:
    """把字节数转换为便于阅读的文件大小。"""
    size = float(value or 0)
    if size < 1024:
        return f"{size:.0f} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


class KnowledgeDropZone(QFrame):
    """知识文档拖拽区，支持 Docling 可解析的常见文档格式。"""

    file_dropped = Signal(str)
    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("AttachmentDropZone")
        self.setProperty("dragActive", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        upload_icon = QLabel("↑")
        upload_icon.setObjectName("KnowledgeUploadIcon")
        upload_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(upload_icon)
        title = QLabel("点击或拖动文件到此处上传")
        title.setObjectName("SectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        hint = QLabel("支持 PDF、DOCX、PPTX、XLSX、HTML、TXT，单个文件最大 20 MB")
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

    def mousePressEvent(self, event) -> None:
        # 点击空白拖拽区时打开文件选择器，拖拽与点击共用同一文件校验流程。
        self.clicked.emit()
        event.accept()

    def _set_drag_active(self, active: bool) -> None:
        # 动态属性变化后刷新 QSS，及时反馈当前拖拽状态。
        self.setProperty("dragActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class KnowledgeOptionCard(QFrame):
    """支持点击整张区域的知识库处理方式卡片。"""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        # 点击卡片任意空白区域时，交由关联的单选按钮完成选择。
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


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


class KnowledgePageBase(QWidget):
    """知识库页面共用线程、状态和错误处理。"""

    answer_chunk_received = Signal(str)

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self._thread: QThread | None = None
        self._worker: KnowledgeWorker | None = None
        self._on_success = None

    def _start_worker(self, operation, *args, on_success=None) -> None:
        # 每个操作使用短生命周期线程，完成后释放线程和 worker，避免界面卡顿。
        self._thread = QThread(self)
        self._worker = KnowledgeWorker(operation, *args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        # 统一经过页面对象的槽切回主线程，普通 lambda 不能直接修改 Qt 界面。
        self._on_success = on_success
        self._worker.succeeded.connect(self._operation_succeeded)
        self._worker.failed.connect(self._operation_failed)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(dict)
    def _operation_succeeded(self, response: dict) -> None:
        """在 UI 主线程调用当前网络操作的成功回调。"""
        on_success = self._on_success
        self._on_success = None
        if on_success:
            on_success(response)

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        self._set_status(message, "error")
        self.status_label.setVisible(True)
        QMessageBox.critical(self, "知识库操作失败", message)

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._on_success = None
        self._set_busy(False)
        self._after_thread_finished()

    def _after_thread_finished(self) -> None:
        """为需要在线程完成后刷新的页面提供钩子。"""

    def _busy_widgets(self) -> tuple[QWidget, ...]:
        return ()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        for widget in self._busy_widgets():
            widget.setEnabled(not busy)
        if message:
            self._set_status(message, "loading")
            self.status_label.setVisible(True)

    def _set_status(self, message: str, status: str) -> None:
        self.status_label.setText(message)
        self.status_label.setProperty("status", status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


class KnowledgeImportPage(KnowledgePageBase):
    """按照选择、设置、预览、确认四步完成知识文档导入。"""

    document_imported = Signal()
    ALLOWED_SUFFIXES = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".txt"}
    MAX_FILE_BYTES = 20 * 1024 * 1024
    STEP_TITLES = ("选择文件", "参数设置", "数据预览", "确认上传")

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__(api_client)
        self.selected_file: Path | None = None
        self.preview_data: dict = {}
        self.current_step = 0
        self.upload_completed = False
        self._build_ui()
        self._show_step(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.status_label = QLabel("")
        self.status_label.setObjectName("ResultBanner")
        self.status_label.setProperty("status", "info")
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)
        root.addWidget(self._build_step_bar())

        self.step_stack = QStackedWidget()
        self.step_stack.setObjectName("KnowledgeImportStack")
        self.step_stack.addWidget(self._build_file_step())
        self.step_stack.addWidget(self._build_settings_step())
        self.step_stack.addWidget(self._build_preview_step())
        self.step_stack.addWidget(self._build_confirm_step())
        root.addWidget(self.step_stack, stretch=1)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("← 上一步")
        # 导航按钮使用外边框显示焦点，避免文字周围出现系统虚线框。
        self.previous_button.setProperty("wizardNavigation", "true")
        self.previous_button.setProperty("variant", "secondary")
        self.previous_button.clicked.connect(self.previous_step)
        navigation.addWidget(self.previous_button)
        navigation.addStretch()
        self.next_button = QPushButton("下一步")
        self.next_button.setProperty("wizardNavigation", "true")
        self.next_button.clicked.connect(self.next_step)
        navigation.addWidget(self.next_button)
        root.addLayout(navigation)

    def _build_step_bar(self) -> QFrame:
        """创建横向步骤指示器。"""
        bar = QFrame()
        bar.setObjectName("KnowledgeStepBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(36, 16, 36, 16)
        layout.setSpacing(10)
        self.step_circles: list[QLabel] = []
        self.step_labels: list[QLabel] = []
        self.step_lines: list[QFrame] = []
        for index, title in enumerate(self.STEP_TITLES):
            circle = QLabel(str(index + 1))
            circle.setObjectName("KnowledgeStepCircle")
            circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            circle.setFixedSize(26, 26)
            label = QLabel(title)
            label.setObjectName("KnowledgeStepText")
            layout.addWidget(circle)
            layout.addWidget(label)
            self.step_circles.append(circle)
            self.step_labels.append(label)
            if index < len(self.STEP_TITLES) - 1:
                line = QFrame()
                line.setObjectName("KnowledgeStepLine")
                line.setFixedHeight(2)
                layout.addWidget(line, stretch=1)
                self.step_lines.append(line)
        return bar

    def _build_file_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        layout.setSpacing(14)

        self.drop_zone = KnowledgeDropZone()
        self.drop_zone.setMinimumHeight(150)
        self.drop_zone.file_dropped.connect(self.select_pending_file)
        self.drop_zone.clicked.connect(self.select_file)
        layout.addWidget(self.drop_zone)

        self.pending_table = self._create_file_table(["文件名", "文件准备状态", "文件大小", "操作"])
        # 固定信息列保持舒展间距，文件名列继续自适应剩余宽度。
        self.pending_table.setColumnWidth(1, 240)
        self.pending_table.setColumnWidth(2, 120)
        self.pending_table.setColumnWidth(3, 88)
        layout.addWidget(self.pending_table)
        layout.addStretch()
        return page

    def _build_settings_step(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 8, 0, 0)
        outer.addStretch()

        panel = QFrame()
        panel.setObjectName("KnowledgeSettingsPanel")
        panel.setMaximumWidth(680)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        title = QLabel("数据处理方式设置")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        hint = QLabel("选择文档入库前采用的处理方式")
        hint.setObjectName("PageHint")
        layout.addWidget(hint)

        self.processing_group = QButtonGroup(self)
        self.normal_radio = QRadioButton("分块存储")
        self.normal_radio.setToolTip("按段落和长度切分原文后直接生成向量")
        self.qa_radio = QRadioButton("问答对提取")
        self.qa_radio.setToolTip("使用 Ollama 将文本块整理为问题和答案后再生成向量")
        self.processing_group.addButton(self.normal_radio)
        self.processing_group.addButton(self.qa_radio)
        self.normal_radio.setChecked(True)

        choices = QHBoxLayout()
        choices.addWidget(self._radio_card(self.normal_radio, "保留原文上下文，适合制度、手册和长文档"))
        choices.addWidget(self._radio_card(self.qa_radio, "生成明确问答，适合故障处理和常见问题"))
        layout.addLayout(choices)

        parameter_title = QLabel("分块处理参数")
        parameter_title.setObjectName("PageHint")
        layout.addWidget(parameter_title)
        default_card = QFrame()
        default_card.setObjectName("KnowledgeOptionCard")
        default_card.setProperty("selected", "true")
        default_layout = QVBoxLayout(default_card)
        default_layout.setContentsMargins(16, 12, 16, 12)
        default_layout.addWidget(QLabel("默认"))
        default_hint = QLabel("使用系统配置的文本块大小与重叠规则")
        default_hint.setObjectName("PageHint")
        default_layout.addWidget(default_hint)
        layout.addWidget(default_card)

        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(panel)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()
        return page

    def _radio_card(self, radio: QRadioButton, description: str) -> QFrame:
        """把处理方式包装成选项卡。"""
        card = KnowledgeOptionCard()
        card.setObjectName("KnowledgeOptionCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.addWidget(radio)
        hint = QLabel(description)
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)
        # 整张卡片与圆形按钮使用同一选择入口，扩大可点击区域。
        card.clicked.connect(lambda target=radio: target.setChecked(True))
        radio.toggled.connect(lambda checked, target=card: self._set_card_selected(target, checked))
        self._set_card_selected(card, radio.isChecked())
        return card

    def _build_preview_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("KnowledgePreviewSplitter")

        left = QFrame()
        left.setObjectName("KnowledgePreviewPane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(18, 16, 18, 16)
        left_layout.addWidget(self._section_label("文件列表"))
        self.preview_file_label = QLabel("尚未选择文件")
        self.preview_file_label.setObjectName("KnowledgeSelectedFile")
        self.preview_file_label.setWordWrap(True)
        left_layout.addWidget(self.preview_file_label)
        self.preview_stats_label = QLabel("")
        self.preview_stats_label.setObjectName("PageHint")
        left_layout.addWidget(self.preview_stats_label)
        left_layout.addStretch()

        right = QFrame()
        right.setObjectName("KnowledgePreviewPane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(18, 16, 18, 16)
        right_layout.addWidget(self._section_label("分块预览"))
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("文档提取结果将在这里显示")
        right_layout.addWidget(self.preview_text, stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)
        return page

    def _build_confirm_step(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 2, 0, 0)
        self.confirm_table = self._create_file_table(["来源名", "处理方式", "预计文本块", "状态"])
        self.confirm_table.setColumnWidth(1, 180)
        self.confirm_table.setColumnWidth(2, 120)
        self.confirm_table.setColumnWidth(3, 120)
        layout.addWidget(self.confirm_table)
        layout.addStretch()
        return page

    def _create_file_table(self, headers: list[str]) -> QTableWidget:
        """创建向导中统一使用的文件表格。"""
        table = QTableWidget(0, len(headers))
        table.setObjectName("KnowledgeWizardTable")
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(54)
        table.setFixedHeight(116)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, len(headers)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        return table

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("SectionTitle")
        return label

    def select_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择知识文档",
            "",
            "知识文档 (*.pdf *.docx *.pptx *.xlsx *.html *.htm *.txt)",
        )
        if file_path:
            self.select_pending_file(file_path)

    def select_pending_file(self, file_path: str) -> None:
        """校验并保存待上传文件，真正上传延迟到第四步。"""
        if self._thread is not None:
            return
        path = Path(file_path)
        try:
            if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                raise ValueError("仅支持 PDF、DOCX、PPTX、XLSX、HTML、TXT 文档")
            size = path.stat().st_size
            if size <= 0:
                raise ValueError("文档不能为空")
            if size > self.MAX_FILE_BYTES:
                raise ValueError("文档大小不能超过 20 MB")
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "文档不可用", str(exc))
            return

        self.selected_file = path
        self.preview_data = {}
        self.upload_completed = False
        self._fill_pending_table(size)
        self.status_label.setVisible(False)
        self._update_navigation()

    def _fill_pending_table(self, size: int) -> None:
        self.pending_table.setRowCount(1)

        # 文件名保持左对齐，并在行内垂直居中。
        file_item = QTableWidgetItem(self.selected_file.name)
        file_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.pending_table.setItem(0, 0, file_item)

        progress = QProgressBar()
        progress.setObjectName("KnowledgeFileProgress")
        progress.setRange(0, 100)
        progress.setValue(100)
        progress.setFormat("已选择")
        progress.setFixedHeight(18)

        # 透明容器提供左右留白，并让准备状态在单元格内上下居中。
        progress_container = QWidget()
        progress_layout = QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(12, 0, 12, 0)
        progress_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        progress_layout.addWidget(progress)
        self.pending_table.setCellWidget(0, 1, progress_container)

        # 文件大小在对应单元格内水平、垂直居中显示。
        size_item = QTableWidgetItem(self._format_size(size))
        size_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pending_table.setItem(0, 2, size_item)

        remove_button = QPushButton("移除")
        remove_button.setProperty("tableAction", "true")
        remove_button.clicked.connect(self.remove_pending_file)

        # 操作文字使用独立容器居中，避免贴近单元格边缘。
        action_container = QWidget()
        action_layout = QHBoxLayout(action_container)
        action_layout.setContentsMargins(8, 0, 8, 0)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        action_layout.addWidget(remove_button)
        self.pending_table.setCellWidget(0, 3, action_container)

    def remove_pending_file(self) -> None:
        if self._thread is not None:
            return
        self.selected_file = None
        self.preview_data = {}
        self.pending_table.setRowCount(0)
        self._update_navigation()

    def next_step(self) -> None:
        if self.current_step == 0:
            if self.selected_file:
                self._show_step(1)
            return
        if self.current_step == 1:
            self._load_preview()
            return
        if self.current_step == 2:
            self._fill_confirm_table()
            self._show_step(3)
            return
        if self.upload_completed:
            self._reset_wizard()
            return
        self._start_upload()

    def previous_step(self) -> None:
        if self.current_step > 0 and self._thread is None and not self.upload_completed:
            self._show_step(self.current_step - 1)

    def _load_preview(self) -> None:
        if not self.selected_file or self._thread is not None:
            return
        self._set_busy(True, "正在提取文档并生成分块预览。")
        self._start_worker(
            self.api_client.preview_knowledge_document,
            str(self.selected_file),
            on_success=self._preview_loaded,
        )

    @Slot(dict)
    def _preview_loaded(self, response: dict) -> None:
        self.preview_data = response.get("data") or {}
        items = self.preview_data.get("items") or []
        blocks = []
        for index, item in enumerate(items, start=1):
            blocks.append(f"文本块 {index}  ·  第 {item.get('page_number', '-')} 页\n{item.get('content', '')}")
        if self.preview_data.get("truncated"):
            blocks.append("仅展示前 10 个文本块，其余内容将在确认上传后继续处理。")
        # 使用横线分隔相邻文本块，让块边界在长文档预览中更清晰。
        self.preview_text.setPlainText(("\n\n" + "-" * 72 + "\n\n").join(blocks))
        self.preview_file_label.setText(self.selected_file.name if self.selected_file else "")
        self.preview_stats_label.setText(
            f"共 {self.preview_data.get('page_count', 0)} 页，预计生成 "
            f"{self.preview_data.get('chunk_count', 0)} 个文本块"
        )
        self.status_label.setVisible(False)
        self._show_step(2)

    def _fill_confirm_table(self) -> None:
        self.confirm_table.setRowCount(1)
        mode = "QA 问答对提取" if self.qa_radio.isChecked() else "普通分块存储"
        values = [
            self.selected_file.name if self.selected_file else "",
            mode,
            self.preview_data.get("chunk_count", 0),
            "等待上传",
        ]
        for column, value in enumerate(values):
            self.confirm_table.setItem(0, column, QTableWidgetItem(str(value)))

    def _start_upload(self) -> None:
        if not self.selected_file or self._thread is not None:
            return
        mode = "QA 拆分" if self.qa_radio.isChecked() else "普通文本切分"
        self._set_busy(True, f"正在上传并执行{mode}、向量化和入库。")
        self._start_worker(
            self.api_client.upload_knowledge_document,
            str(self.selected_file),
            self.qa_radio.isChecked(),
            on_success=self._upload_succeeded,
        )

    @Slot(dict)
    def _upload_succeeded(self, response: dict) -> None:
        data = response.get("data") or {}
        self.upload_completed = True
        self.confirm_table.setItem(0, 2, QTableWidgetItem(str(data.get("chunk_count", 0))))
        self.confirm_table.setItem(0, 3, QTableWidgetItem("已入库"))
        self._set_status("文档上传成功，文本提取、向量化和入库已完成。", "success")
        self.status_label.setVisible(True)
        self._update_navigation()
        # 通知数据集页面刷新列表，让新入库文档立即可见。
        self.document_imported.emit()

    def _show_step(self, step: int) -> None:
        self.current_step = step
        self.step_stack.setCurrentIndex(step)
        self._update_step_bar()
        self._update_navigation()

    def _update_step_bar(self) -> None:
        for index, (circle, label) in enumerate(zip(self.step_circles, self.step_labels)):
            state = "complete" if index < self.current_step else "current" if index == self.current_step else "pending"
            circle.setProperty("stepState", state)
            label.setProperty("stepState", state)
            circle.setText("✓" if state == "complete" else str(index + 1))
            self._refresh_style(circle)
            self._refresh_style(label)
        for index, line in enumerate(self.step_lines):
            line.setProperty("active", "true" if index < self.current_step else "false")
            self._refresh_style(line)

    def _update_navigation(self) -> None:
        self.previous_button.setVisible(self.current_step > 0 and not self.upload_completed)
        self.next_button.setText("重新导入" if self.current_step == 3 and self.upload_completed else "开始上传" if self.current_step == 3 else "下一步")
        self.next_button.setEnabled(self.selected_file is not None and self._thread is None)

    def _reset_wizard(self) -> None:
        self.selected_file = None
        self.preview_data = {}
        self.upload_completed = False
        self.pending_table.setRowCount(0)
        self.confirm_table.setRowCount(0)
        self.preview_text.clear()
        self.status_label.setVisible(False)
        self.normal_radio.setChecked(True)
        self._show_step(0)

    def _busy_widgets(self) -> tuple[QWidget, ...]:
        return self.drop_zone, self.normal_radio, self.qa_radio, self.previous_button, self.next_button

    def _set_card_selected(self, card: QFrame, selected: bool) -> None:
        card.setProperty("selected", "true" if selected else "false")
        self._refresh_style(card)

    def _refresh_style(self, widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _format_size(self, value: int) -> str:
        return _format_file_size(value)


class KnowledgeDatasetPage(KnowledgePageBase):
    """展示已入库数据集，并提供文本块分页预览和文档导入入口。"""

    CHUNK_PAGE_SIZE = 50

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__(api_client)
        self.documents: list[dict] = []
        self.current_document: dict = {}
        self.chunk_page = 1
        self.chunk_pages = 1
        self._pending_source_image: tuple[int, int] | None = None
        self._loaded = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.status_label = QLabel("")
        self.status_label.setObjectName("ResultBanner")
        self.status_label.setProperty("status", "info")
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)

        self.view_stack = QStackedWidget()
        self.list_page = self._build_list_page()
        self.detail_page = self._build_detail_page()
        self.import_page_container = self._build_import_page()
        self.view_stack.addWidget(self.list_page)
        self.view_stack.addWidget(self.detail_page)
        self.view_stack.addWidget(self.import_page_container)
        root.addWidget(self.view_stack, stretch=1)

    def _build_list_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        toolbar = QFrame()
        toolbar.setObjectName("KnowledgeDatasetToolbar")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        self.dataset_count_label = QLabel("数据集")
        self.dataset_count_label.setObjectName("KnowledgeDatasetCount")
        toolbar_layout.addWidget(self.dataset_count_label)
        toolbar_layout.addStretch()

        self.dataset_search_input = QLineEdit()
        self.dataset_search_input.setPlaceholderText("搜索数据集名称")
        self.dataset_search_input.setMaximumWidth(240)
        self.dataset_search_input.textChanged.connect(self._apply_filter)
        toolbar_layout.addWidget(self.dataset_search_input)

        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.clicked.connect(self.refresh_documents)
        toolbar_layout.addWidget(self.refresh_button)

        self.import_button = QPushButton("新建/导入")
        self.import_button.clicked.connect(self.show_import_page)
        toolbar_layout.addWidget(self.import_button)
        layout.addWidget(toolbar)

        self.documents_table = QTableWidget(0, 8)
        self.documents_table.setObjectName("KnowledgeDatasetTable")
        self.documents_table.setHorizontalHeaderLabels(
            ["名称", "处理模式", "文本块", "文件大小", "创建人", "创建时间", "状态", "操作"]
        )
        self.documents_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.documents_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 数据集行只承担打开详情的点击行为，不显示蓝色选中背景和文字焦点虚线。
        self.documents_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.documents_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.documents_table.setAlternatingRowColors(True)
        self.documents_table.verticalHeader().setVisible(False)
        self.documents_table.verticalHeader().setDefaultSectionSize(54)
        header = self.documents_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 8):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        # 处理模式需要完整显示“问答对提取”，名称列使用剩余空间自适应。
        self.documents_table.setColumnWidth(1, 140)
        self.documents_table.setColumnWidth(2, 90)
        self.documents_table.setColumnWidth(3, 100)
        self.documents_table.setColumnWidth(4, 100)
        self.documents_table.setColumnWidth(5, 150)
        self.documents_table.setColumnWidth(6, 90)
        self.documents_table.setColumnWidth(7, 80)
        # 点击任意单元格都打开对应数据集，避免用户必须寻找单独操作按钮。
        self.documents_table.cellClicked.connect(self.open_document)
        layout.addWidget(self.documents_table, stretch=1)
        return page

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        self.detail_back_button = QPushButton("← 返回数据集")
        # 返回按钮使用外边框表示焦点，避免文字周围出现虚线。
        self.detail_back_button.setProperty("wizardNavigation", "true")
        self.detail_back_button.setProperty("variant", "secondary")
        self.detail_back_button.clicked.connect(self.show_list_page)
        header_row.addWidget(self.detail_back_button)
        self.detail_title = QLabel("数据集详情")
        self.detail_title.setObjectName("SectionTitle")
        header_row.addWidget(self.detail_title)
        header_row.addStretch()
        self.source_image_button = QPushButton("查看原图")
        self.source_image_button.setProperty("variant", "secondary")
        self.source_image_button.setVisible(False)
        self.source_image_button.clicked.connect(self.view_source_image)
        header_row.addWidget(self.source_image_button)
        layout.addLayout(header_row)

        self.detail_meta_label = QLabel("")
        self.detail_meta_label.setObjectName("PageHint")
        layout.addWidget(self.detail_meta_label)

        self.chunks_table = QTableWidget(0, 4)
        self.chunks_table.setObjectName("KnowledgeChunksTable")
        self.chunks_table.setHorizontalHeaderLabels(["文本块", "页码/图片", "来源图片", "内容"])
        self.chunks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.chunks_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 文本块详情仅用于阅读，不显示蓝色选中背景和文字焦点虚线。
        self.chunks_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.chunks_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chunks_table.setWordWrap(True)
        self.chunks_table.verticalHeader().setVisible(False)
        chunks_header = self.chunks_table.horizontalHeader()
        chunks_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        chunks_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        chunks_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        chunks_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.chunks_table.setColumnWidth(0, 88)
        self.chunks_table.setColumnWidth(1, 90)
        self.chunks_table.setColumnWidth(2, 180)
        layout.addWidget(self.chunks_table, stretch=1)

        pagination = QHBoxLayout()
        pagination.addStretch()
        self.chunk_previous_button = QPushButton("上一页")
        self.chunk_previous_button.setProperty("variant", "secondary")
        self.chunk_previous_button.clicked.connect(self.previous_chunk_page)
        pagination.addWidget(self.chunk_previous_button)
        self.chunk_page_label = QLabel("第 1 / 1 页")
        pagination.addWidget(self.chunk_page_label)
        self.chunk_next_button = QPushButton("下一页")
        self.chunk_next_button.setProperty("variant", "secondary")
        self.chunk_next_button.clicked.connect(self.next_chunk_page)
        pagination.addWidget(self.chunk_next_button)
        pagination.addStretch()
        layout.addLayout(pagination)
        return page

    def _build_import_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        # 顶部留白与按钮下方间距保持一致，避免按钮贴住页签分隔线。
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)
        back_button = QPushButton("← 返回数据集")
        back_button.setProperty("wizardNavigation", "true")
        back_button.setProperty("variant", "secondary")
        back_button.clicked.connect(self.show_list_page)
        header = QHBoxLayout()
        header.addWidget(back_button)
        header.addStretch()
        layout.addLayout(header)

        self.import_page = KnowledgeImportPage(self.api_client)
        self.import_page.document_imported.connect(self._document_imported)
        layout.addWidget(self.import_page, stretch=1)
        return page

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._loaded:
            self.refresh_documents()

    def refresh_documents(self) -> None:
        """从后端重新读取已建立的数据集。"""
        if self._thread is not None:
            return
        self._set_busy(True, "正在加载知识库数据集。")
        self._start_worker(self.api_client.get_knowledge_documents, on_success=self._documents_loaded)

    @Slot(dict)
    def _documents_loaded(self, response: dict) -> None:
        self.documents = (response.get("data") or {}).get("items") or []
        self._loaded = True
        self._apply_filter()
        if self.documents:
            self.status_label.setVisible(False)
        else:
            self._set_status("暂无数据集，请点击“新建/导入”添加文档。", "info")
            self.status_label.setVisible(True)

    def _apply_filter(self, _text: str = "") -> None:
        """按数据集名称在已加载列表中进行本地筛选。"""
        keyword = self.dataset_search_input.text().strip().lower()
        visible_documents = [
            document
            for document in self.documents
            if keyword in str(document.get("original_name") or "").lower()
        ]
        self.dataset_count_label.setText(f"数据集（{len(visible_documents)}）")
        self.documents_table.setRowCount(len(visible_documents))
        for row, document in enumerate(visible_documents):
            values = [
                document.get("original_name", ""),
                # 处理模式由后端记录，历史数据没有该字段时按普通分割显示。
                document.get("processing_mode") or "正常分割",
                document.get("chunk_count", 0),
                _format_file_size(document.get("size_bytes", 0)),
                document.get("created_by", ""),
                self._format_created_at(document.get("created_at", "")),
                "已就绪",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 0:
                    # 文档数据挂在名称单元格上，点击行后无需再次查找列表。
                    item.setData(Qt.ItemDataRole.UserRole, document)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.documents_table.setItem(row, column, item)

            remove_button = QPushButton("移除")
            remove_button.setProperty("tableAction", "true")
            remove_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            remove_button.clicked.connect(
                lambda _checked=False, target=document: self.confirm_remove_document(target)
            )
            # 操作按钮使用透明容器居中，避免文字贴近列边缘。
            action_container = QWidget()
            action_layout = QHBoxLayout(action_container)
            action_layout.setContentsMargins(8, 0, 8, 0)
            action_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            action_layout.addWidget(remove_button)
            self.documents_table.setCellWidget(row, 7, action_container)

    def confirm_remove_document(self, document: dict) -> None:
        """确认后删除数据集及其全部文本块和向量。"""
        if self._thread is not None:
            return
        name = str(document.get("original_name") or "当前数据集")
        result = QMessageBox.question(
            self,
            "移除数据集",
            f"确认移除“{name}”吗？\n移除后，相关文本块和向量将一并删除，且不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        document_id = int(document["id"])
        self._set_busy(True, f"正在移除数据集：{name}")
        self._start_worker(
            self.api_client.delete_knowledge_document,
            document_id,
            on_success=lambda _response, target_id=document_id, target_name=name: self._document_removed(
                target_id,
                target_name,
            ),
        )

    def _document_removed(self, document_id: int, name: str) -> None:
        """删除成功后同步更新当前数据集列表。"""
        self.documents = [document for document in self.documents if int(document.get("id", 0)) != document_id]
        self._apply_filter()
        self._set_status(f"数据集“{name}”已移除。", "success")
        self.status_label.setVisible(True)

    def open_document(self, row: int, _column: int = 0) -> None:
        """读取用户点击的数据集并打开文本块预览。"""
        item = self.documents_table.item(row, 0)
        document = item.data(Qt.ItemDataRole.UserRole) if item else None
        if not document or self._thread is not None:
            return
        self.current_document = document
        self.chunk_page = 1
        self._load_document_chunks()

    def _load_document_chunks(self) -> None:
        if not self.current_document or self._thread is not None:
            return
        self._set_busy(True, "正在加载数据集内容。")
        self._start_worker(
            self.api_client.get_knowledge_document_chunks,
            int(self.current_document["id"]),
            self.chunk_page,
            self.CHUNK_PAGE_SIZE,
            on_success=self._chunks_loaded,
        )

    @Slot(dict)
    def _chunks_loaded(self, response: dict) -> None:
        data = response.get("data") or {}
        self.current_document = data.get("document") or self.current_document
        items = data.get("items") or []
        total = int(data.get("total") or 0)
        page_size = int(data.get("page_size") or self.CHUNK_PAGE_SIZE)
        self.chunk_page = int(data.get("page") or 1)
        self.chunk_pages = max(1, (total + page_size - 1) // page_size)

        self.detail_title.setText(str(self.current_document.get("original_name") or "数据集详情"))
        self.detail_meta_label.setText(
            f"共 {total} 个文本块 · {_format_file_size(self.current_document.get('size_bytes', 0))} · "
            f"创建人：{self.current_document.get('created_by', '-')}"
        )
        self.source_image_button.setVisible(self.current_document.get("source_type") in {"image", "image_set"})
        self.chunks_table.setRowCount(len(items))
        for row, chunk in enumerate(items):
            values = [
                int(chunk.get("chunk_index", 0)) + 1,
                chunk.get("page_number", "-"),
                chunk.get("source_image_name") or "-",
                chunk.get("content", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                # 详情内容直接在表格中换行展示，不设置悬停弹窗。
                if column < 2:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.chunks_table.setItem(row, column, item)
        self.chunks_table.resizeRowsToContents()
        self.chunk_page_label.setText(f"第 {self.chunk_page} / {self.chunk_pages} 页")
        self.chunk_previous_button.setEnabled(self.chunk_page > 1)
        self.chunk_next_button.setEnabled(self.chunk_page < self.chunk_pages)
        self.status_label.setVisible(False)
        self.view_stack.setCurrentWidget(self.detail_page)

    def view_source_image(self) -> None:
        """读取当前知识库的图片列表，单图直接打开，多图先让用户选择。"""
        if not self.current_document or self._thread is not None:
            return
        self._set_busy(True, "正在读取原图列表。")
        self._start_worker(
            self.api_client.get_knowledge_document_images,
            int(self.current_document["id"]),
            on_success=self._source_images_loaded,
        )

    @Slot(dict)
    def _source_images_loaded(self, response: dict) -> None:
        """选择需要查看的来源图片，并等待当前列表线程结束后下载。"""
        images = (response.get("data") or {}).get("items") or []
        if not images:
            QMessageBox.warning(self, "原图不可用", "当前知识库没有可查看的原图。")
            return
        selected = images[0]
        if len(images) > 1:
            labels = [f"{image.get('image_index', index + 1)}. {image.get('original_name', '')}" for index, image in enumerate(images)]
            label, accepted = QInputDialog.getItem(self, "选择原图", "来源图片", labels, 0, False)
            if not accepted:
                return
            selected = images[labels.index(label)]
        self._pending_source_image = (int(self.current_document["id"]), int(selected["id"]))

    def _after_thread_finished(self) -> None:
        """图片列表请求结束后，再启动选中原图的下载请求。"""
        if self._pending_source_image is None:
            return
        document_id, image_id = self._pending_source_image
        self._pending_source_image = None
        QTimer.singleShot(0, lambda: self._load_source_image(document_id, image_id))

    def _load_source_image(self, document_id: int, image_id: int) -> None:
        """异步下载用户选中的一张来源图片。"""
        if self._thread is not None:
            return
        self._set_busy(True, "正在读取原图。")
        self._start_worker(
            self.api_client.get_knowledge_document_image,
            document_id,
            image_id,
            on_success=self._show_source_image,
        )

    @Slot(dict)
    def _show_source_image(self, response: dict) -> None:
        """在可滚动对话框中按比例展示知识来源原图。"""
        pixmap = QPixmap()
        if not pixmap.loadFromData(response.get("content") or b""):
            QMessageBox.warning(self, "原图不可用", "原图文件无法读取。")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(str(response.get("filename") or "知识来源原图"))
        dialog.resize(900, 700)
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setPixmap(
            pixmap.scaled(860, 640, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        layout.addWidget(label)
        dialog.exec()

    def previous_chunk_page(self) -> None:
        if self.chunk_page > 1:
            self.chunk_page -= 1
            self._load_document_chunks()

    def next_chunk_page(self) -> None:
        if self.chunk_page < self.chunk_pages:
            self.chunk_page += 1
            self._load_document_chunks()

    def show_list_page(self) -> None:
        if self._thread is None:
            self.view_stack.setCurrentWidget(self.list_page)

    def show_import_page(self) -> None:
        if self._thread is not None:
            return
        if self.import_page.upload_completed:
            self.import_page._reset_wizard()
        self.view_stack.setCurrentWidget(self.import_page_container)

    @Slot()
    def _document_imported(self) -> None:
        # 入库成功后返回数据集列表并重新读取后端数据。
        self.view_stack.setCurrentWidget(self.list_page)
        self._loaded = False
        self.refresh_documents()

    def _busy_widgets(self) -> tuple[QWidget, ...]:
        return (
            self.dataset_search_input,
            self.refresh_button,
            self.import_button,
            self.documents_table,
            self.detail_back_button,
            self.chunk_previous_button,
            self.chunk_next_button,
            self.source_image_button,
        )

    def _format_created_at(self, value) -> str:
        """把接口时间压缩为列表使用的分钟精度。"""
        return str(value or "").replace("T", " ")[:16]


class KnowledgeSearchPage(KnowledgePageBase):
    """使用知识库检索和 Ollama 流式回答的聊天页面。"""

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__(api_client)
        self._answer_buffer = ""
        self._active_answer_label: QLabel | None = None
        self._active_source_label: QLabel | None = None
        self._message_rows: list[QWidget] = []
        self._build_ui()
        self.answer_chunk_received.connect(self._append_answer_chunk)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.status_label = QLabel("")
        self.status_label.setObjectName("ResultBanner")
        self.status_label.setProperty("status", "info")
        self.status_label.setVisible(False)
        root.addWidget(self.status_label)

        body = QHBoxLayout()
        body.setSpacing(12)

        sidebar = QFrame()
        sidebar.setObjectName("KnowledgeChatSidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(12)
        sidebar_title = QLabel("聊天")
        sidebar_title.setObjectName("KnowledgeChatSidebarTitle")
        sidebar_layout.addWidget(sidebar_title)

        self.new_chat_button = QPushButton("＋ 新对话")
        self.new_chat_button.setProperty("variant", "secondary")
        self.new_chat_button.clicked.connect(self.new_conversation)
        sidebar_layout.addWidget(self.new_chat_button)

        session_button = QPushButton("知识库问答")
        session_button.setObjectName("KnowledgeChatSession")
        session_button.setProperty("active", "true")
        session_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sidebar_layout.addWidget(session_button)
        sidebar_layout.addStretch()
        body.addWidget(sidebar)

        chat_panel = QFrame()
        chat_panel.setObjectName("KnowledgeChatPanel")
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        chat_header = QFrame()
        chat_header.setObjectName("KnowledgeChatHeader")
        header_layout = QVBoxLayout(chat_header)
        header_layout.setContentsMargins(22, 14, 22, 14)
        header_layout.setSpacing(3)
        title = QLabel("企业知识库助手")
        title.setObjectName("KnowledgeChatTitle")
        header_layout.addWidget(title)
        hint = QLabel("回答仅依据已入库的数据集，并展示引用来源")
        hint.setObjectName("PageHint")
        header_layout.addWidget(hint)
        chat_layout.addWidget(chat_header)

        self.messages_scroll = QScrollArea()
        self.messages_scroll.setObjectName("KnowledgeChatMessages")
        self.messages_scroll.setWidgetResizable(True)
        self.messages_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.messages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.messages_container = QWidget()
        self.messages_container.setObjectName("KnowledgeChatMessagesContainer")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(36, 28, 36, 28)
        self.messages_layout.setSpacing(18)

        self.welcome_panel = QFrame()
        self.welcome_panel.setObjectName("KnowledgeChatWelcome")
        self.welcome_panel.setMaximumWidth(620)
        welcome_layout = QVBoxLayout(self.welcome_panel)
        welcome_layout.setContentsMargins(28, 30, 28, 30)
        welcome_layout.setSpacing(8)
        welcome_title = QLabel("今天想了解什么？")
        welcome_title.setObjectName("KnowledgeChatWelcomeTitle")
        welcome_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_layout.addWidget(welcome_title)
        welcome_hint = QLabel("可以询问制度、手册、设备维护和故障处理等已入库内容")
        welcome_hint.setObjectName("PageHint")
        welcome_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_hint.setWordWrap(True)
        welcome_layout.addWidget(welcome_hint)
        self.messages_layout.addWidget(
            self.welcome_panel,
            stretch=1,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.messages_layout.addStretch()
        self.messages_scroll.setWidget(self.messages_container)
        chat_layout.addWidget(self.messages_scroll, stretch=1)

        composer = QFrame()
        composer.setObjectName("KnowledgeChatComposer")
        composer_layout = QHBoxLayout(composer)
        composer_layout.setContentsMargins(18, 14, 18, 14)
        composer_layout.setSpacing(12)

        # 输入框与发送按钮共用胶囊容器，保持聊天输入区的一体化布局。
        input_shell = QFrame()
        input_shell.setObjectName("KnowledgeChatInputShell")
        input_shell_layout = QHBoxLayout(input_shell)
        input_shell_layout.setContentsMargins(12, 8, 10, 8)
        input_shell_layout.setSpacing(8)

        self.query_input = QPlainTextEdit()
        self.query_input.setObjectName("KnowledgeChatInput")
        self.query_input.setPlaceholderText("输入问题，Ctrl + Enter 发送")
        self.query_input.setFixedHeight(52)
        self.query_input.installEventFilter(self)
        input_shell_layout.addWidget(self.query_input, stretch=1)

        # 图标发送操作使用工具按钮，避免受到全局文字按钮尺寸规则影响。
        self.search_button = QToolButton()
        self.search_button.setObjectName("KnowledgeChatSend")
        # 使用 qtawesome 矢量图标替换字符箭头，保证不同字体环境下显示一致。
        self.search_button.setIcon(qta.icon("fa5s.arrow-up", color="white"))
        self.search_button.setIconSize(QSize(17, 17))
        self.search_button.setToolTip("发送问题")
        self.search_button.setAccessibleName("发送问题")
        self.search_button.setFixedSize(36, 36)
        self.search_button.clicked.connect(self.search)
        input_shell_layout.addWidget(self.search_button, alignment=Qt.AlignmentFlag.AlignBottom)
        composer_layout.addWidget(input_shell, stretch=1)
        chat_layout.addWidget(composer)
        body.addWidget(chat_panel, stretch=1)
        root.addLayout(body, stretch=1)

    def search(self) -> None:
        if self._thread is not None:
            self._stop_answer()
            return
        query = self.query_input.toPlainText().strip()
        if not query:
            return
        self.query_input.clear()
        self.welcome_panel.setVisible(False)
        self._add_message("user", query)
        self._active_answer_label, self._active_source_label = self._add_message("assistant", "正在检索知识库。")
        self._answer_buffer = ""
        self._set_busy(True)
        # 工作线程通过 Signal.emit 传回文本片段，避免直接跨线程修改控件。
        self._start_worker(
            self.api_client.stream_knowledge_answer,
            query,
            5,
            self.answer_chunk_received.emit,
            on_success=self._search_succeeded,
        )

    @Slot(dict)
    def _search_succeeded(self, response: dict) -> None:
        data = response.get("data") or {}
        if response.get("cancelled"):
            # 停止后保留已经生成的正文，没有正文时给出明确状态。
            stopped_text = self._answer_buffer.rstrip()
            if self._active_answer_label is not None:
                self._active_answer_label.setText(
                    f"{stopped_text}\n\n已停止生成。" if stopped_text else "已停止生成。"
                )
            self.status_label.setVisible(False)
            return
        answer = str(data.get("answer") or "未生成答案。")
        if self._active_answer_label is not None:
            # 最终答案也按纯文本显示，避免模型不完整 Markdown 造成正文被隐藏。
            self._active_answer_label.setTextFormat(Qt.TextFormat.PlainText)
            self._active_answer_label.setText(answer)

        sources = data.get("sources") or []
        if self._active_source_label is not None and sources:
            # 来源只展示文档、页码和相似度，避免把大段命中文本重复塞入聊天区。
            source_lines = [
                f"{'图片来源' if source.get('source_type') in {'image', 'image_set'} else '文档来源'}："
                f"{source.get('document', '未知文档')}"
                + (f" / {source.get('image')}" if source.get("image") else "")
                + f" · 第 {source.get('page', '-')} 页 · "
                f"{float(source.get('score', 0)) * 100:.1f}%"
                for source in sources
            ]
            self._active_source_label.setText("参考来源\n" + "\n".join(source_lines))
            self._active_source_label.setVisible(True)
        self.status_label.setVisible(False)
        self._scroll_to_bottom()

    @Slot(str)
    def _append_answer_chunk(self, content: str) -> None:
        """把新到达的答案片段追加到当前机器人气泡。"""
        self._answer_buffer += content
        if self._active_answer_label is not None:
            # 流式阶段按纯文本刷新，确保正文在 Markdown 尚未闭合时仍可见。
            self._active_answer_label.setTextFormat(Qt.TextFormat.PlainText)
            self._active_answer_label.setText(self._answer_buffer)
        self._scroll_to_bottom()

    def _add_message(self, role: str, content: str) -> tuple[QLabel, QLabel]:
        """创建一条用户或机器人消息，并返回正文与来源标签。"""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        bubble = QFrame()
        bubble.setObjectName("KnowledgeChatBubble")
        bubble.setProperty("role", role)
        # 助手正文使用更宽的阅读区域，用户气泡仍随内容收缩并靠右显示。
        bubble.setMaximumWidth(1000 if role == "assistant" else 620)
        bubble.setSizePolicy(
            QSizePolicy.Policy.Expanding if role == "assistant" else QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(
            *((0, 4, 0, 4) if role == "assistant" else (14, 10, 14, 10))
        )
        bubble_layout.setSpacing(7)

        if role == "assistant":
            # 助手名称与头像共同标识回答来源，符合常见 AI 对话信息层级。
            role_label = QLabel("知识库助手")
            role_label.setObjectName("KnowledgeChatRole")
            bubble_layout.addWidget(role_label)

        message_label = QLabel(content)
        message_label.setObjectName("KnowledgeChatMessage")
        message_label.setProperty("role", role)
        # 助手回答按 Markdown 展示结构化内容，用户提问保持原样文本。
        message_label.setTextFormat(
            Qt.TextFormat.MarkdownText if role == "assistant" else Qt.TextFormat.PlainText
        )
        message_label.setWordWrap(True)
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble_layout.addWidget(message_label)

        source_label = QLabel("")
        source_label.setObjectName("KnowledgeChatSources")
        source_label.setWordWrap(True)
        source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        source_label.setVisible(False)
        bubble_layout.addWidget(source_label)

        if role == "user":
            row_layout.addStretch()
            row_layout.addWidget(bubble)
        else:
            # 助手回答从消息区左侧开始排列，右侧伸缩项保留正文阅读宽度。
            avatar = QLabel("AI")
            avatar.setObjectName("KnowledgeChatAvatar")
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            avatar.setFixedSize(32, 32)
            row_layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            # 正文优先占用可用宽度，避免列表和引用来源过早换行。
            row_layout.addWidget(bubble, stretch=10)
            row_layout.addStretch(1)
        # 消息插入到底部伸缩项之前，保持短会话靠上显示。
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        self._message_rows.append(row)
        self._scroll_to_bottom()
        return message_label, source_label

    def new_conversation(self) -> None:
        """清空当前内存会话，不影响知识库数据。"""
        if self._thread is not None:
            return
        for row in self._message_rows:
            self.messages_layout.removeWidget(row)
            row.deleteLater()
        self._message_rows.clear()
        self._answer_buffer = ""
        self._active_answer_label = None
        self._active_source_label = None
        self.welcome_panel.setVisible(True)
        self.query_input.clear()
        self.query_input.setFocus()

    def eventFilter(self, watched, event) -> bool:
        # 多行输入框使用 Ctrl + Enter 发送，普通 Enter 继续用于换行。
        if (
            watched is self.query_input
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.search()
            return True
        return super().eventFilter(watched, event)

    def _scroll_to_bottom(self) -> None:
        """在布局刷新后把聊天记录滚动到最新消息。"""
        QTimer.singleShot(
            0,
            lambda: self.messages_scroll.verticalScrollBar().setValue(
                self.messages_scroll.verticalScrollBar().maximum()
            ),
        )

    def _stop_answer(self) -> None:
        """请求关闭当前流，并防止用户在工作线程退出前重复点击。"""
        self.api_client.cancel_knowledge_answer()
        self.search_button.setEnabled(False)
        self.search_button.setToolTip("正在停止")
        self.search_button.setAccessibleName("正在停止回答")

    @Slot(str)
    def _operation_failed(self, message: str) -> None:
        if self._active_answer_label is not None and not self._answer_buffer:
            self._active_answer_label.setText("回答失败，请稍后重试。")
        super()._operation_failed(message)

    def _busy_widgets(self) -> tuple[QWidget, ...]:
        return self.query_input, self.new_chat_button

    def _set_busy(self, busy: bool, message: str = "") -> None:
        """生成中保留圆形操作按钮，并把发送箭头切换为停止方块。"""
        super()._set_busy(busy, message)
        self.search_button.setEnabled(True)
        icon_name = "fa5s.stop" if busy else "fa5s.arrow-up"
        action_name = "停止回答" if busy else "发送问题"
        self.search_button.setIcon(qta.icon(icon_name, color="white"))
        self.search_button.setToolTip(action_name)
        self.search_button.setAccessibleName(action_name)


class KnowledgeWorkspacePage(QWidget):
    """在同一页面中组合知识库数据集和搜索测试。"""

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("KnowledgeWorkspaceTabs")
        self.dataset_page = KnowledgeDatasetPage(api_client)
        self.search_page = KnowledgeSearchPage(api_client)
        self.tabs.addTab(self.dataset_page, "数据集")
        self.tabs.addTab(self.search_page, "搜索测试")
        root.addWidget(self.tabs)


# 保留旧类名，避免外部脚本导入旧入口时立即失效。
KnowledgePage = KnowledgeImportPage
