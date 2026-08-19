from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class AttachmentDropZone(QFrame):
    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("AttachmentDropZone")
        # 拖拽状态通过动态属性交给全局 QSS 控制高亮。
        self.setProperty("dragActive", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        title = QLabel("拖拽文件到这里上传附件")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        hint = QLabel("也可以点击下方“上传附件”按钮选择本地文件。")
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        # 只接受本地文件拖拽，避免把普通文本或网址误当成上传内容。
        if event.mimeData().hasUrls():
            local_urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
            if local_urls:
                self._set_drag_active(True)
                event.acceptProposedAction()
                return
        self._set_drag_active(False)
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        # 文件离开区域时立即恢复默认样式。
        self._set_drag_active(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drag_active(False)
        local_urls = [url for url in event.mimeData().urls() if url.isLocalFile()]
        if not local_urls:
            event.ignore()
            return

        # 当前附件区只处理第一个本地文件，避免一次拖多个文件造成结果不明确。
        self.file_dropped.emit(local_urls[0].toLocalFile())
        event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        # 重新刷新当前控件样式，让动态属性变化即时生效。
        self.setProperty("dragActive", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class DeviceDetailPage(QWidget):
    back_requested = Signal()

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.current_device_id = ""

        self.page_title = QLabel("设备详情")
        self.page_title.setObjectName("PageTitle")
        self.page_hint = QLabel("请选择一台设备查看详情。")
        self.page_hint.setObjectName("PageHint")

        self.device_id_value = QLabel("-")
        self.device_name_value = QLabel("-")
        self.model_value = QLabel("-")
        self.manufacturer_value = QLabel("-")
        self.location_value = QLabel("-")
        self.status_value = QLabel("-")
        # 详情页状态沿用设备列表的状态标签视觉。
        self.status_value.setObjectName("StatusBadge")
        self.status_value.setProperty("status", "unknown")
        self.status_value.setFixedWidth(72)
        self.status_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_value = QLabel("暂无附件")
        self.file_value.setObjectName("AttachmentFile")
        self.file_value.setWordWrap(True)
        self.current_file_path = ""
        self.logs_empty_label = QLabel("暂无操作日志")
        self.logs_empty_label.setObjectName("EmptyState")
        self.logs_empty_label.setVisible(False)

        self.logs_table = QTableWidget(0, 4)

        self._build_ui()
        self._update_attachment_buttons()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        top_row = QHBoxLayout()
        top_row.addWidget(self.page_title)
        top_row.addStretch()

        back_button = QPushButton("返回列表")
        back_button.setProperty("variant", "secondary")
        back_button.clicked.connect(self.back_requested.emit)
        top_row.addWidget(back_button)
        root.addLayout(top_row)
        root.addWidget(self.page_hint)

        info_card = QFrame()
        info_card.setObjectName("PageCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(14)

        info_title = QLabel("基础信息")
        info_title.setObjectName("SectionTitle")
        info_layout.addWidget(info_title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        self._add_info_row(grid, 0, "设备编号", self.device_id_value)
        self._add_info_row(grid, 0, "设备名称", self.device_name_value, 2)
        self._add_info_row(grid, 1, "设备型号", self.model_value)
        self._add_info_row(grid, 1, "厂商名称", self.manufacturer_value, 2)
        self._add_info_row(grid, 2, "所在位置", self.location_value)
        self._add_info_row(grid, 2, "设备状态", self.status_value, 2)
        info_layout.addLayout(grid)
        root.addWidget(info_card)

        file_card = QFrame()
        file_card.setObjectName("PageCard")
        file_layout = QVBoxLayout(file_card)
        file_layout.setContentsMargins(18, 18, 18, 18)
        file_layout.setSpacing(12)

        file_title = QLabel("附件信息")
        file_title.setObjectName("SectionTitle")
        file_layout.addWidget(file_title)
        file_layout.addWidget(self.file_value)

        # 拖拽上传区和按钮上传共用同一套上传逻辑。
        self.drop_zone = AttachmentDropZone()
        self.drop_zone.file_dropped.connect(self.upload_attachment_from_path)
        file_layout.addWidget(self.drop_zone)

        file_actions = QHBoxLayout()
        self.upload_button = QPushButton("上传附件")
        self.upload_button.setProperty("variant", "secondary")
        self.upload_button.clicked.connect(self.upload_attachment)
        file_actions.addWidget(self.upload_button)

        self.download_button = QPushButton("下载附件")
        self.download_button.setProperty("variant", "secondary")
        self.download_button.clicked.connect(self.download_attachment)
        file_actions.addWidget(self.download_button)

        self.delete_button = QPushButton("删除附件")
        self.delete_button.setProperty("variant", "danger")
        self.delete_button.clicked.connect(self.delete_attachment)
        file_actions.addWidget(self.delete_button)
        file_actions.addStretch()
        file_layout.addLayout(file_actions)
        root.addWidget(file_card)

        logs_card = QFrame()
        logs_card.setObjectName("PageCard")
        logs_layout = QVBoxLayout(logs_card)
        logs_layout.setContentsMargins(18, 18, 18, 18)
        logs_layout.setSpacing(12)

        logs_header = QHBoxLayout()
        logs_title = QLabel("操作日志")
        logs_title.setObjectName("SectionTitle")
        logs_header.addWidget(logs_title)
        logs_header.addStretch()

        refresh_button = QPushButton("刷新日志")
        refresh_button.setProperty("variant", "secondary")
        refresh_button.clicked.connect(self.refresh_logs)
        logs_header.addWidget(refresh_button)
        logs_layout.addLayout(logs_header)

        self.logs_table.setHorizontalHeaderLabels(["动作", "操作人", "说明", "设备编号"])
        self.logs_table.verticalHeader().setVisible(False)
        self.logs_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.logs_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.logs_table.setAlternatingRowColors(True)
        self.logs_table.verticalHeader().setDefaultSectionSize(42)
        # 说明列自动占用剩余宽度，设备编号保持紧凑固定宽度。
        logs_header_view = self.logs_table.horizontalHeader()
        logs_header_view.setStretchLastSection(False)
        logs_header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        logs_header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        logs_header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        logs_header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.logs_table.setColumnWidth(0, 100)
        self.logs_table.setColumnWidth(1, 100)
        self.logs_table.setColumnWidth(3, 140)
        logs_layout.addWidget(self.logs_table)
        logs_layout.addWidget(self.logs_empty_label, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addWidget(logs_card, stretch=1)

    def _add_info_row(self, grid: QGridLayout, row: int, label_text: str, value_label: QLabel, column: int = 0) -> None:
        label = QLabel(f"{label_text}：")
        label.setObjectName("PageHint")
        grid.addWidget(label, row, column)
        grid.addWidget(value_label, row, column + 1)

    def load_device(self, device_id: str) -> None:
        self.current_device_id = device_id
        self.page_hint.setText(f"正在查看设备 {device_id} 的详细信息。")
        self._load_detail()
        self.refresh_logs()

    def _load_detail(self) -> None:
        if not self.current_device_id:
            return

        try:
            response = self.api_client.get_device_detail(self.current_device_id)
            data = response.get("data") or {}
            device = data.get("device") or {}

            self.page_title.setText(f"设备详情 - {device.get('device_name', self.current_device_id)}")
            self.device_id_value.setText(str(device.get("device_id", "-")))
            self.device_name_value.setText(str(device.get("device_name", "-")))
            self.model_value.setText(str(device.get("model", "-")))
            self.manufacturer_value.setText(str(device.get("manufacturer", "-")))
            self.location_value.setText(str(device.get("location", "-")))
            status = str(device.get("status", ""))
            self.status_value.setText(self._map_status(status))
            self.status_value.setProperty("status", status or "unknown")
            self.status_value.style().unpolish(self.status_value)
            self.status_value.style().polish(self.status_value)

            # 附件显示区缓存后端返回的文件路径，但界面只展示文件名，避免直接暴露服务器路径。
            self.current_file_path = str(device.get("file_path", "") or "")
            self._update_attachment_display()
            self._update_attachment_buttons()
        except ApiError as exc:
            self.page_hint.setText(str(exc))

    def refresh_logs(self) -> None:
        if not self.current_device_id:
            return

        try:
            response = self.api_client.get_device_logs(self.current_device_id)
            logs = response.get("data") or []
            self.logs_table.setRowCount(len(logs))
            self.logs_empty_label.setText("暂无操作日志" if not logs else "")
            self.logs_empty_label.setVisible(not logs)
            for row_index, log in enumerate(logs):
                values = [
                    log.get("action", ""),
                    log.get("operator", ""),
                    log.get("details", ""),
                    log.get("device_id", ""),
                ]
                for col_index, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.logs_table.setItem(row_index, col_index, item)
        except ApiError as exc:
            self.logs_table.setRowCount(0)
            self.logs_empty_label.setText("操作日志加载失败")
            self.logs_empty_label.setVisible(True)
            self.page_hint.setText(str(exc))

    def upload_attachment(self) -> None:
        if not self.current_device_id:
            QMessageBox.warning(self, "无法上传附件", "请先选择一台设备。")
            return

        # 上传前先让用户从本地选择文件，避免误触发空请求。
        file_path, _ = QFileDialog.getOpenFileName(self, "选择要上传的附件")
        if not file_path:
            return

        self.upload_attachment_from_path(file_path)

    def upload_attachment_from_path(self, file_path: str) -> None:
        if not self.current_device_id:
            QMessageBox.warning(self, "无法上传附件", "请先选择一台设备。")
            return

        try:
            self.api_client.upload_device_attachment(self.current_device_id, file_path)
            QMessageBox.information(self, "上传成功", f"附件已上传：{Path(file_path).name}")
            self._load_detail()
            self.refresh_logs()
        except ApiError as exc:
            QMessageBox.critical(self, "上传失败", str(exc))

    def download_attachment(self) -> None:
        if not self.current_device_id:
            QMessageBox.warning(self, "无法下载附件", "请先选择一台设备。")
            return
        if not self.current_file_path:
            QMessageBox.information(self, "暂无附件", "当前设备还没有可下载的附件。")
            return

        suggested_name = Path(self.current_file_path).name or f"{self.current_device_id}_attachment"
        # 下载前先选择保存位置，避免直接写入用户不期望的目录。
        save_path, _ = QFileDialog.getSaveFileName(self, "保存附件", suggested_name)
        if not save_path:
            return

        try:
            file_bytes, filename = self.api_client.download_device_attachment(self.current_device_id)
            target_path = Path(save_path)
            # 如果用户只选了目录或省略后缀，这里保留界面层最终选择的文件名。
            if target_path.name in {"", "."}:
                target_path = target_path / filename
            target_path.write_bytes(file_bytes)
            QMessageBox.information(self, "下载成功", f"附件已保存到：{target_path}")
            self.refresh_logs()
        except ApiError as exc:
            QMessageBox.critical(self, "下载失败", str(exc))
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))

    def delete_attachment(self) -> None:
        if not self.current_device_id:
            QMessageBox.warning(self, "无法删除附件", "请先选择一台设备。")
            return
        if not self.current_file_path:
            QMessageBox.information(self, "暂无附件", "当前设备没有可删除的附件。")
            return

        result = QMessageBox.question(
            self,
            "删除附件确认",
            "确认删除当前附件吗？删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            self.api_client.delete_device_attachment(self.current_device_id)
            QMessageBox.information(self, "删除成功", "当前附件已删除。")
            self._load_detail()
            self.refresh_logs()
        except ApiError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))

    def _update_attachment_buttons(self) -> None:
        # 没有附件时禁用下载和删除，减少无效点击。
        has_attachment = bool(self.current_file_path)
        self.download_button.setEnabled(has_attachment)
        self.delete_button.setEnabled(has_attachment)

    def _update_attachment_display(self) -> None:
        # 列表页和详情页都只显示附件文件名，完整路径仅保留在提示里供排障查看。
        if not self.current_file_path:
            self.file_value.setText("当前附件：暂无附件")
            self.file_value.setToolTip("")
            return

        attachment_name = Path(self.current_file_path).name or self.current_file_path
        self.file_value.setText(f"当前附件：{attachment_name}")
        self.file_value.setToolTip(self.current_file_path)

    def _map_status(self, value: str) -> str:
        status_map = {
            "active": "启用中",
            "maintenance": "维护中",
            "inactive": "已停用",
            "retired": "已报废",
        }
        return status_map.get(value, value or "-")
