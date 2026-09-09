import json
from html import escape
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class OcrDropZone(QFrame):
    files_dropped = Signal(list)

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
        hint = QLabel("支持同时拖入多张 JPG、PNG、BMP、WEBP，每张最大 10 MB")
        hint.setObjectName("PageHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # 接收全部本地文件，文件格式和数量在页面层统一校验。
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
            self.files_dropped.emit(local_files)
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

    def __init__(self, operation, *args) -> None:
        super().__init__()
        self.operation = operation
        self.args = args

    @Slot()
    def run(self) -> None:
        # 网络请求放到工作线程，避免模型推理期间阻塞界面。
        try:
            self.succeeded.emit(self.operation(*self.args))
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
        self.ocr_lines: list[dict] = []
        self.tasks: list[dict] = []
        self.current_index = -1
        self._active_task_index: int | None = None
        self._recognize_queue: list[int] = []
        self._save_queue: list[int] = []
        self._operation_mode = ""
        self._target_document_id: int | None = None
        self._targets_loaded = False
        self._thread: QThread | None = None
        self._worker: OcrWorker | None = None
        self._on_success = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        self.status_label = QLabel("请选择一张或多张图片开始识别。")
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
        self.drop_zone.files_dropped.connect(self._add_files)
        source_layout.addWidget(self.drop_zone)

        self.files_table = QTableWidget(0, 3)
        self.files_table.setObjectName("OcrFilesTable")
        self.files_table.setHorizontalHeaderLabels(["图片", "状态", "文字行"])
        self.files_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.files_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.files_table.verticalHeader().setVisible(False)
        files_header = self.files_table.horizontalHeader()
        files_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        files_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        files_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        # 固定状态和文字行列的宽度，避免两列文字挤在一起，图片列使用剩余空间。
        self.files_table.setColumnWidth(1, 108)
        self.files_table.setColumnWidth(2, 88)
        # 表头统一居中，保证短标题在各自列的视觉中心对齐。
        files_header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.files_table.setMaximumHeight(190)
        self.files_table.cellClicked.connect(self._select_task)
        source_layout.addWidget(self.files_table)

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
        self.clear_button = QPushButton("清空全部")
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

        target_row = QHBoxLayout()
        target_label = QLabel("保存方式")
        target_label.setObjectName("PageHint")
        target_row.addWidget(target_label)
        self.target_combo = QComboBox()
        self.target_combo.addItem("新建知识库", None)
        self.target_combo.currentIndexChanged.connect(self._target_changed)
        target_row.addWidget(self.target_combo, stretch=1)
        result_layout.addLayout(target_row)

        name_row = QHBoxLayout()
        name_label = QLabel("知识库名称")
        name_label.setObjectName("PageHint")
        name_row.addWidget(name_label)
        self.knowledge_name_input = QLineEdit()
        self.knowledge_name_input.setPlaceholderText("输入图片知识库名称")
        self.knowledge_name_input.setMaxLength(255)
        name_row.addWidget(self.knowledge_name_input, stretch=1)
        result_layout.addLayout(name_row)

        tabs = QTabWidget()
        self.result_tabs = tabs
        self.text_result = QPlainTextEdit()
        # OCR 完成后允许人工校正型号、编号等易错字段，再保存到知识库。
        self.text_result.setPlaceholderText("识别文本将在这里显示，可校正后保存到知识库")
        tabs.addTab(self.text_result, "校正文本")

        self.lines_table = QTableWidget(0, 2)
        self.lines_table.setHorizontalHeaderLabels(["文本", "置信度"])
        self.lines_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.verticalHeader().setVisible(False)
        self.lines_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.lines_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.lines_table.setColumnWidth(1, 100)
        tabs.addTab(self.lines_table, "逐行结果")
        self.table_json_result = QPlainTextEdit()
        self.table_json_result.setPlaceholderText("表格 JSON 识别结果将在这里显示，可人工校正后复制或保存")
        # 用户修改 JSON 后实时刷新 Markdown，便于对照层级和字段归属。
        self.table_json_result.textChanged.connect(self._refresh_markdown_preview)
        tabs.addTab(self.table_json_result, "表格 JSON")
        self.markdown_preview = QTextBrowser()
        self.markdown_preview.setObjectName("TableMarkdownPreview")
        self.markdown_preview.setPlaceholderText("表格识别后将在这里显示 Markdown 预览")
        tabs.addTab(self.markdown_preview, "Markdown 预览")
        result_layout.addWidget(tabs, stretch=1)

        result_actions = QHBoxLayout()
        self.recognize_button = QPushButton("识别全部")
        self.recognize_button.setEnabled(False)
        self.recognize_button.clicked.connect(self.recognize)
        result_actions.addWidget(self.recognize_button)
        self.table_button = QPushButton("表格转 JSON")
        self.table_button.setProperty("variant", "secondary")
        self.table_button.setEnabled(False)
        self.table_button.clicked.connect(self.parse_table)
        result_actions.addWidget(self.table_button)
        self.copy_button = QPushButton("复制全文")
        self.copy_button.setProperty("variant", "secondary")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_text)
        result_actions.addWidget(self.copy_button)
        self.knowledge_button = QPushButton("全部保存到知识库")
        self.knowledge_button.setEnabled(False)
        self.knowledge_button.clicked.connect(self.save_to_knowledge)
        result_actions.addWidget(self.knowledge_button)
        result_actions.addStretch()
        result_layout.addLayout(result_actions)
        splitter.addWidget(result_panel)

        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([400, 600])
        root.addWidget(splitter, stretch=1)

    def select_file(self) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择待识别图片（可多选）",
            "",
            "图片文件 (*.jpg *.jpeg *.png *.bmp *.webp)",
        )
        if file_paths:
            self._add_files(file_paths)

    def _set_file(self, file_path: str) -> None:
        """兼容单文件调用，并统一交给多图片队列处理。"""
        self._add_files([file_path])

    @Slot(list)
    def _add_files(self, file_paths: list[str]) -> None:
        """校验并把多张图片加入待识别队列。"""
        if self._thread is not None:
            return
        existing_paths = {task["path"] for task in self.tasks}
        added_indices: list[int] = []
        errors: list[str] = []

        # 单次最多保留 20 张，避免桌面端一次加载过多大图占满内存。
        for file_path in file_paths[: max(0, 20 - len(self.tasks))]:
            path = Path(file_path).resolve()
            if str(path) in existing_paths:
                continue
            try:
                if path.suffix.lower() not in self.ALLOWED_SUFFIXES:
                    raise ValueError("格式不支持")
                size = path.stat().st_size
                if size > self.MAX_FILE_BYTES:
                    raise ValueError("超过 10 MB")
                pixmap = QPixmap(str(path))
                if pixmap.isNull():
                    raise ValueError("图片损坏或无法读取")
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}：{exc}")
                continue

            self.tasks.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "size": size,
                    "status": "等待识别",
                    "text": "",
                    "lines": [],
                    "table_data": {},
                    "error": "",
                }
            )
            existing_paths.add(str(path))
            added_indices.append(len(self.tasks) - 1)

        self._refresh_files_table()
        if added_indices:
            self._select_task(added_indices[0])
            if self.target_combo.currentData() is None and not self.knowledge_name_input.text().strip():
                # 新建模式默认采用第一张图片的文件名，用户仍可自由修改。
                self.knowledge_name_input.setText(Path(self.tasks[added_indices[0]]["name"]).stem)
            self._set_status(f"已加入 {len(added_indices)} 张图片，可以开始批量识别。", "info")
        if errors:
            QMessageBox.warning(self, "部分图片未加入", "\n".join(errors[:8]))
        self._update_controls()

    def _refresh_files_table(self) -> None:
        """刷新图片任务状态表。"""
        self.files_table.setRowCount(len(self.tasks))
        for row, task in enumerate(self.tasks):
            values = [task["name"], task["status"], len(task["lines"])]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.files_table.setItem(row, column, item)

    def _persist_current_task(self) -> None:
        """切换图片前保存用户在编辑框中的校正文本。"""
        if 0 <= self.current_index < len(self.tasks):
            self.tasks[self.current_index]["text"] = self.text_result.toPlainText()
            table_json = self.table_json_result.toPlainText().strip()
            if table_json:
                try:
                    business = json.loads(table_json)
                    if not isinstance(business, dict):
                        raise ValueError("表格 JSON 必须为对象")
                    # 只更新业务字段，不覆盖后端返回的单元格证据。
                    self.tasks[self.current_index].setdefault("table_data", {}).update(business)
                    self.tasks[self.current_index].pop("table_json_draft", None)
                except ValueError:
                    # 暂存非法 JSON，保留用户输入，保存前由用户继续修正。
                    self.tasks[self.current_index]["table_json_draft"] = table_json
            else:
                self.tasks[self.current_index]["table_json_draft"] = ""

    def _select_task(self, row: int, _column: int = 0) -> None:
        """显示任务列表中指定图片的原图和 OCR 结果。"""
        if not 0 <= row < len(self.tasks):
            return
        self._persist_current_task()
        self.current_index = row
        task = self.tasks[row]
        self.file_path = task["path"]
        self.ocr_lines = task["lines"]
        pixmap = QPixmap(task["path"])
        self.preview_label.setPixmap(
            pixmap.scaled(420, 320, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )
        self.file_label.setText(f"{task['name']}  |  {task['size'] / 1024:.1f} KB")
        self.text_result.setPlainText(task["text"])
        self._fill_lines(task["lines"])
        table_draft = task.get("table_json_draft")
        self.table_json_result.setPlainText(
            table_draft if table_draft is not None else self._format_table_json(task.get("table_data") or {})
        )
        self.files_table.selectRow(row)
        self._update_controls()

    def _fill_lines(self, lines: list[dict]) -> None:
        """把当前图片的逐行 OCR 结果写入右侧表格。"""
        self.lines_table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            self.lines_table.setItem(row, 0, QTableWidgetItem(str(line.get("text") or "")))
            score = line.get("score")
            score_text = "-" if score is None else f"{float(score) * 100:.1f}%"
            score_item = QTableWidgetItem(score_text)
            score_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.lines_table.setItem(row, 1, score_item)
        self.result_summary.setText(f"{len(lines)} 行")

    def recognize(self) -> None:
        if not self.tasks or self._thread is not None:
            return
        self._persist_current_task()
        self._recognize_queue = [
            index
            for index, task in enumerate(self.tasks)
            if task["status"] not in {"已识别", "已保存", "已存在"}
        ]
        if not self._recognize_queue:
            self._set_status("所有图片均已完成识别。", "info")
            return
        self._operation_mode = "recognize"
        self._recognize_next()

    def parse_table(self) -> None:
        """调用后端表格接口，把当前图片转换为可编辑 JSON。"""
        if self._thread is not None or not (0 <= self.current_index < len(self.tasks)):
            return
        self._persist_current_task()
        task = self.tasks[self.current_index]
        self._active_task_index = self.current_index
        self._operation_mode = "table"
        task["status"] = "表格识别中"
        self._refresh_files_table()
        self._set_status(f"正在生成表格 JSON：{task['name']}", "loading")
        self._update_controls()
        self._run_operation(self.api_client.parse_table_image, task["path"], on_success=self._show_table_result)

    def _recognize_next(self) -> None:
        """从队列中取出下一张图片并调用现有单图 OCR 接口。"""
        if not self._recognize_queue:
            return
        self._active_task_index = self._recognize_queue.pop(0)
        task = self.tasks[self._active_task_index]
        task["status"] = "识别中"
        task["error"] = ""
        self._refresh_files_table()
        self._select_task(self._active_task_index)
        self._set_status(f"正在识别：{task['name']}", "loading")
        self._update_controls()
        self._run_operation(self.api_client.recognize_image, task["path"], on_success=self._show_result)

    def _run_operation(self, operation, *args, on_success) -> None:
        """在线程中执行 OCR 或图片知识入库操作。"""
        # 每次请求创建一个短生命周期线程，完成后由 Qt 自动回收。
        self._thread = QThread(self)
        self._worker = OcrWorker(operation, *args)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        # 所有成功回调先切回页面主线程，禁止工作线程直接修改 Qt 控件。
        self._on_success = on_success
        self._worker.succeeded.connect(self._operation_succeeded)
        self._worker.failed.connect(self._show_error)
        self._worker.completed.connect(self._thread.quit)
        self._worker.completed.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    @Slot(dict)
    def _operation_succeeded(self, response: dict) -> None:
        """在 Qt 主线程执行当前操作的成功回调。"""
        on_success = self._on_success
        self._on_success = None
        if on_success:
            on_success(response)

    @Slot(dict)
    def _show_result(self, response: dict) -> None:
        data = response.get("data") or {}
        text = str(data.get("text") or "")
        lines = data.get("lines") or []
        if self._active_task_index is not None:
            task = self.tasks[self._active_task_index]
            task["text"] = text
            task["lines"] = lines
            task["status"] = "已识别" if text else "未识别到文字"
            self.current_index = self._active_task_index
            self._refresh_files_table()
        self.ocr_lines = lines
        self.text_result.setPlainText(text)
        self._fill_lines(lines)
        self.copy_button.setEnabled(bool(text))
        self.knowledge_button.setEnabled(bool(text))
        message = "识别完成。" if lines else "识别完成，未检测到文字。"
        self._set_status(message, "success")

    @Slot(dict)
    def _show_table_result(self, response: dict) -> None:
        """显示表格 JSON，并保留识别坐标供后续人工校正和入库使用。"""
        data = response.get("data") or {}
        if self._active_task_index is not None:
            task = self.tasks[self._active_task_index]
            task["table_data"] = data
            # 新一次识别结果替换旧草稿，防止切换图片后再次显示旧结果。
            task.pop("table_json_draft", None)
            task["status"] = "表格已识别"
            self.current_index = self._active_task_index
            self._refresh_files_table()
        self.table_json_result.setPlainText(self._format_table_json(data))
        self.result_tabs.setCurrentWidget(self.markdown_preview)
        self._set_status("表格结构已识别，请核对手写文字、金额及字段归属。", "info")

    @staticmethod
    def _format_table_json(data: dict) -> str:
        """只展示业务字段 JSON，隐藏坐标等底层识别数据。"""
        if not data:
            return ""
        business_data = {
            "document_title": data.get("document_title", ""),
            "sections": data.get("sections", []),
        }
        return json.dumps(business_data, ensure_ascii=False, indent=2)

    def _refresh_markdown_preview(self) -> None:
        """把用户当前编辑的业务 JSON 实时渲染为 Markdown。"""
        source = self.table_json_result.toPlainText().strip()
        if not source:
            self.markdown_preview.clear()
            return
        try:
            data = json.loads(source)
            if not isinstance(data, dict):
                raise ValueError
        except (json.JSONDecodeError, ValueError):
            self.markdown_preview.setPlainText("JSON 格式有误，修正后将自动更新预览。")
            return
        self.markdown_preview.setMarkdown(self._table_to_markdown(data))

    @staticmethod
    def _table_to_markdown(data: dict) -> str:
        """将嵌套业务字段转换为适合界面预览的 Markdown 表格。"""
        title = escape(str(data.get("document_title") or "未命名表格"), quote=False)
        parts = [f"# {title}"]
        for section in data.get("sections") or []:
            if not isinstance(section, dict):
                continue
            name = escape(str(section.get("name") or "未分类"), quote=False)
            parts.extend([f"\n## {name}", "", "| 字段 | 内容 | 置信度 | 状态 |", "| --- | --- | --- | --- |"])
            for field in section.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                field_name = OcrPage._markdown_cell(field.get("name"))
                value = field.get("value")
                if isinstance(value, dict):
                    value_text = "<br/>".join(
                        f"{OcrPage._markdown_cell(key)}：{OcrPage._markdown_cell(item)}"
                        for key, item in value.items()
                    )
                else:
                    value_text = OcrPage._markdown_cell(value)
                confidence = field.get("confidence")
                try:
                    confidence_text = "-" if confidence is None else f"{float(confidence) * 100:.1f}%"
                except (TypeError, ValueError):
                    # 人工编辑过程中允许临时输入非数字，预览仍保持可用。
                    confidence_text = OcrPage._markdown_cell(confidence)
                status = OcrPage._markdown_cell(field.get("status"))
                parts.append(f"| {field_name} | {value_text} | {confidence_text} | {status} |")
        return "\n".join(parts)

    @staticmethod
    def _markdown_cell(value) -> str:
        """转义表格分隔符和 HTML 字符，避免识别文本破坏 Markdown 布局。"""
        text = escape(str(value or ""), quote=False).replace("|", "\\|")
        return text.replace("\r\n", "<br/>").replace("\n", "<br/>")

    @Slot(str)
    def _show_error(self, message: str) -> None:
        if self._active_task_index is not None:
            task = self.tasks[self._active_task_index]
            task["status"] = "保存失败" if self._operation_mode == "save" else "识别失败"
            task["error"] = message
            self._refresh_files_table()
        action = "保存" if self._operation_mode == "save" else "识别"
        self._set_status(f"{action}失败：{message}", "error")

    @Slot()
    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
        self._on_success = None
        if self._operation_mode == "recognize" and self._recognize_queue:
            QTimer.singleShot(0, self._recognize_next)
            return
        if self._operation_mode == "save" and self._save_queue:
            QTimer.singleShot(0, self._save_next)
            return

        if self._operation_mode == "recognize":
            completed = sum(task["status"] == "已识别" for task in self.tasks)
            self._set_status(f"批量识别完成，共 {completed} 张图片识别成功。", "success")
        elif self._operation_mode == "save":
            saved = sum(task["status"] in {"已保存", "已存在"} for task in self.tasks)
            self._set_status(f"保存完成，共处理 {saved} 张图片。", "success")
            self._add_current_target_to_combo()
        self._operation_mode = ""
        self._active_task_index = None
        self._update_controls()

    def save_to_knowledge(self) -> None:
        """把全部已识别图片新建为一个知识库，或追加到已有知识库。"""
        if self._thread is not None:
            return
        self._persist_current_task()
        knowledge_name = self.knowledge_name_input.text().strip()
        self._target_document_id = self.target_combo.currentData()
        if self._target_document_id is None and not knowledge_name:
            QMessageBox.warning(self, "名称不能为空", "请输入知识库名称。")
            return
        self._save_queue = [
            index
            for index, task in enumerate(self.tasks)
            if task["text"].strip() and task["status"] not in {"已保存", "已存在"}
        ]
        if not self._save_queue:
            QMessageBox.warning(self, "没有可保存内容", "请先完成图片识别并校正文本。")
            return
        self._operation_mode = "save"
        self._save_next()

    def _save_next(self) -> None:
        """按顺序保存图片，第一张创建知识库后复用返回的 ID。"""
        if not self._save_queue:
            return
        self._active_task_index = self._save_queue.pop(0)
        task = self.tasks[self._active_task_index]
        task["status"] = "保存中"
        self._refresh_files_table()
        self._select_task(self._active_task_index)
        self._set_status(f"正在生成向量并保存：{task['name']}", "loading")
        self._update_controls()
        self._run_operation(
            self.api_client.upload_knowledge_image,
            task["path"],
            self.knowledge_name_input.text().strip(),
            task["text"].strip(),
            task["lines"],
            self._target_document_id,
            on_success=self._knowledge_saved,
        )

    @Slot(dict)
    def _knowledge_saved(self, response: dict) -> None:
        """记录单张图片入库结果，并为后续图片保存知识库 ID。"""
        data = response.get("data") or {}
        self._target_document_id = int(data.get("id") or self._target_document_id or 0) or None
        if self._active_task_index is not None:
            task = self.tasks[self._active_task_index]
            task["status"] = "已存在" if data.get("duplicate") else "已保存"
            task["document_id"] = self._target_document_id
            self._refresh_files_table()
        self._set_status(f"已保存：{self.tasks[self._active_task_index]['name']}", "success")

    def copy_text(self) -> None:
        text = self.text_result.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._set_status("识别文本已复制到剪贴板。", "success")

    def clear(self) -> None:
        if self._thread is not None:
            return
        self.file_path = ""
        self.tasks = []
        self.current_index = -1
        self._active_task_index = None
        self._recognize_queue = []
        self._save_queue = []
        self.files_table.setRowCount(0)
        self.preview_label.clear()
        self.preview_label.setText("暂无图片")
        self.file_label.setText("未选择文件")
        if self.target_combo.currentData() is None:
            self.knowledge_name_input.clear()
        self.text_result.clear()
        self.ocr_lines = []
        self.table_json_result.clear()
        self.markdown_preview.clear()
        self.lines_table.setRowCount(0)
        self.result_summary.setText("0 行")
        self._update_controls()
        self._set_status("请选择一张或多张图片开始识别。", "info")

    def showEvent(self, event) -> None:
        """页面首次显示时加载可追加的图片知识库。"""
        super().showEvent(event)
        if self.api_client is not None and not self._targets_loaded and self._thread is None:
            self._operation_mode = "targets"
            self._run_operation(self.api_client.get_knowledge_documents, on_success=self._targets_received)

    @Slot(dict)
    def _targets_received(self, response: dict) -> None:
        """把已有图片知识库填入保存目标下拉框。"""
        current_target = self.target_combo.currentData()
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem("新建知识库", None)
        for document in (response.get("data") or {}).get("items") or []:
            if document.get("source_type") in {"image", "image_set"}:
                self.target_combo.addItem(str(document.get("original_name") or "未命名知识库"), int(document["id"]))
        target_index = self.target_combo.findData(current_target)
        self.target_combo.setCurrentIndex(max(0, target_index))
        self.target_combo.blockSignals(False)
        self._targets_loaded = True
        self._target_changed()

    def _target_changed(self, _index: int = 0) -> None:
        """切换新建或追加模式，并同步知识库名称输入状态。"""
        document_id = self.target_combo.currentData()
        if document_id is not None:
            self.knowledge_name_input.setText(self.target_combo.currentText())
        elif self.tasks and not self.knowledge_name_input.text().strip():
            self.knowledge_name_input.setText(Path(self.tasks[0]["name"]).stem)
        self._update_controls()

    def _add_current_target_to_combo(self) -> None:
        """新建成功后立即把知识库加入下拉框，便于继续追加。"""
        if self._target_document_id is None:
            return
        target_index = self.target_combo.findData(self._target_document_id)
        if target_index < 0:
            self.target_combo.addItem(self.knowledge_name_input.text().strip(), self._target_document_id)
            target_index = self.target_combo.count() - 1
        self.target_combo.setCurrentIndex(target_index)

    def _update_controls(self) -> None:
        """根据队列和线程状态统一更新按钮，避免批处理中重复操作。"""
        busy = self._thread is not None or self._operation_mode in {"recognize", "save", "table"}
        has_text = 0 <= self.current_index < len(self.tasks) and bool(self.tasks[self.current_index]["text"].strip())
        has_savable = any(task["text"].strip() and task["status"] not in {"已保存", "已存在"} for task in self.tasks)
        self.select_button.setEnabled(not busy and len(self.tasks) < 20)
        self.clear_button.setEnabled(not busy and bool(self.tasks))
        self.files_table.setEnabled(not busy)
        self.target_combo.setEnabled(not busy)
        self.knowledge_name_input.setEnabled(not busy and self.target_combo.currentData() is None)
        self.recognize_button.setEnabled(not busy and bool(self.tasks))
        self.copy_button.setEnabled(not busy and has_text)
        self.table_button.setEnabled(not busy and 0 <= self.current_index < len(self.tasks))
        self.knowledge_button.setEnabled(not busy and has_savable)

    def _set_status(self, message: str, status: str) -> None:
        # 识别状态复用全局结果横幅颜色，保持各业务页面反馈一致。
        self.status_label.setText(message)
        self.status_label.setProperty("status", status)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
