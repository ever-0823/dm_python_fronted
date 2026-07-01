from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.device_form_dialog import DeviceFormDialog


class SelectAllHeader(QHeaderView):
    toggled = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.checkbox = QCheckBox(self.viewport())
        self.checkbox.stateChanged.connect(self._emit_toggle)
        self.sectionResized.connect(self._update_checkbox_position)
        self.geometriesChanged.connect(self._update_checkbox_position)

    def _emit_toggle(self, state: int) -> None:
        self.toggled.emit(state == Qt.CheckState.Checked.value)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_checkbox_position()

    def set_checked(self, checked: bool) -> None:
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def _update_checkbox_position(self) -> None:
        if self.count() == 0:
            return
        section_x = self.sectionViewportPosition(0)
        section_width = self.sectionSize(0)
        hint = self.checkbox.sizeHint()
        x = section_x + max((section_width - hint.width()) // 2, 0)
        y = max((self.height() - hint.height()) // 2, 0)
        self.checkbox.move(x, y)


class DevicesPage(QWidget):
    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入设备编号或设备名称")

        self.status_filter = QComboBox()
        self.status_filter.addItem("全部", "")
        self.status_filter.addItem("启用中", "active")
        self.status_filter.addItem("维护中", "maintenance")
        self.status_filter.addItem("已停用", "inactive")
        self.status_filter.addItem("已报废", "retired")

        self.table = QTableWidget(0, 8)
        self.header = SelectAllHeader(self.table)
        self.table.setHorizontalHeader(self.header)
        self.header.toggled.connect(self.set_all_rows_checked)

        self.page_hint = QLabel("准备加载设备数据")
        self.page_hint.setObjectName("PageHint")
        self.new_button = QPushButton("新建设备")
        self.batch_delete_button = QPushButton("批量删除")
        self.devices_cache: list[dict] = []

        self._build_ui()
        self.load_devices()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 5, 0, 4)
        title_row.setSpacing(10)
        title_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("设备列表")
        title.setObjectName("PageTitle")
        title_row.addWidget(title, alignment=Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch()

        self.batch_delete_button.setProperty("variant", "danger")
        self.batch_delete_button.clicked.connect(self.batch_delete_selected)
        title_row.addWidget(self.batch_delete_button, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.new_button.clicked.connect(self.open_create_dialog)
        title_row.addWidget(self.new_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(title_row)

        toolbar = QFrame()
        toolbar.setObjectName("ToolbarCard")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 16, 16, 16)
        toolbar_layout.setSpacing(12)
        toolbar_layout.addWidget(QLabel("搜索设备"))
        toolbar_layout.addWidget(self.search_input, stretch=2)
        toolbar_layout.addWidget(QLabel("设备状态"))
        toolbar_layout.addWidget(self.status_filter, stretch=1)

        query_button = QPushButton("查询")
        query_button.clicked.connect(self.load_devices)
        toolbar_layout.addWidget(query_button)

        reset_button = QPushButton("重置")
        reset_button.setProperty("variant", "secondary")
        reset_button.clicked.connect(self.reset_filters)
        toolbar_layout.addWidget(reset_button)
        root.addWidget(toolbar)

        self.table.setHorizontalHeaderLabels(["", "设备编号", "设备名称", "型号", "厂商", "位置", "状态", "操作"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self._configure_table_columns()
        root.addWidget(self.table)

        footer = QHBoxLayout()
        footer.addWidget(self.page_hint)
        footer.addStretch()

        refresh_button = QPushButton("刷新")
        refresh_button.setProperty("variant", "secondary")
        refresh_button.clicked.connect(self.load_devices)
        footer.addWidget(refresh_button)
        root.addLayout(footer)

    def reset_filters(self) -> None:
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self.load_devices()

    def load_devices(self) -> None:
        try:
            response = self.api_client.get_devices(
                page=1,
                page_size=10,
                search=self.search_input.text().strip(),
                status=self.status_filter.currentData() or "",
            )
            data = response.get("data") or {}
            items = data.get("items") or []
            self.devices_cache = items

            self.table.setRowCount(len(items))
            for row_index, item in enumerate(items):
                self.table.setCellWidget(row_index, 0, self._build_checkbox_widget(item))
                values = [
                    item.get("device_id", ""),
                    item.get("device_name", ""),
                    item.get("model", ""),
                    item.get("manufacturer", ""),
                    item.get("location", ""),
                    self._map_status(item.get("status", "")),
                ]
                for col_index, value in enumerate(values):
                    cell = QTableWidgetItem(str(value))
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(row_index, col_index + 1, cell)
                self.table.setCellWidget(row_index, 7, self._build_action_widget(item))

            self.header.set_checked(False)
            total = data.get("total", 0)
            self.page_hint.setText(f"当前共加载 {len(items)} 条，后端总数 {total} 条。")
        except ApiError as exc:
            self.table.setRowCount(0)
            self.devices_cache = []
            self.header.set_checked(False)
            self.page_hint.setText(str(exc))

    def open_create_dialog(self) -> None:
        dialog = DeviceFormDialog(self.api_client, parent=self)
        dialog.device_saved.connect(self.load_devices)
        dialog.exec()

    def open_edit_dialog(self, device: dict) -> None:
        dialog = DeviceFormDialog(self.api_client, device=device, parent=self)
        dialog.device_saved.connect(self.load_devices)
        dialog.exec()

    def _build_checkbox_widget(self, device: dict) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        checkbox = QCheckBox()
        checkbox.setProperty("device_id", str(device.get("device_id", "")))
        checkbox.stateChanged.connect(self.sync_header_checkbox)
        layout.addWidget(checkbox)
        return container

    def _build_action_widget(self, device: dict) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        edit_button = QPushButton("编辑")
        edit_button.setProperty("variant", "secondary")
        edit_button.setProperty("compact", "true")
        edit_button.setFixedWidth(52)
        edit_button.clicked.connect(lambda: self.open_edit_dialog(device))
        layout.addWidget(edit_button)

        detail_button = QPushButton("详情")
        detail_button.setProperty("variant", "secondary")
        detail_button.setProperty("compact", "true")
        detail_button.setFixedWidth(52)
        detail_button.clicked.connect(lambda: self.show_detail_hint(device))
        layout.addWidget(detail_button)

        return container

    def _configure_table_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 56)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 130)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 90)
        self.table.setColumnWidth(7, 118)

    def set_all_rows_checked(self, checked: bool) -> None:
        for row_index in range(self.table.rowCount()):
            checkbox = self._get_row_checkbox(row_index)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)

    def sync_header_checkbox(self) -> None:
        all_checked = self.table.rowCount() > 0 and all(
            checkbox is not None and checkbox.isChecked()
            for checkbox in (self._get_row_checkbox(row_index) for row_index in range(self.table.rowCount()))
        )
        self.header.set_checked(all_checked)

    def batch_delete_selected(self) -> None:
        selected_devices = self._get_selected_devices()
        if not selected_devices:
            QMessageBox.information(self, "未选择设备", "请先勾选要删除的设备。")
            return

        result = QMessageBox.question(
            self,
            "批量删除确认",
            f"确认删除已选中的 {len(selected_devices)} 台设备吗？\n删除后不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        device_ids = [str(device.get("device_id", "")) for device in selected_devices]
        if any(not device_id for device_id in device_ids):
            QMessageBox.warning(self, "删除失败", "选中的设备里存在空设备编号，无法执行批量删除。")
            return

        try:
            response = self.api_client.batch_delete_devices(device_ids)
            data = response.get("data") or {}
            deleted_count = int(data.get("deleted_count") or 0)
            missing_ids = data.get("missing_ids") or []

            self.load_devices()

            if not missing_ids:
                QMessageBox.information(self, "批量删除完成", f"已成功删除 {deleted_count} 台设备。")
                return

            missing_text = "、".join(str(item) for item in missing_ids[:10])
            if len(missing_ids) > 10:
                missing_text += "..."
            QMessageBox.warning(
                self,
                "批量删除完成",
                f"成功删除 {deleted_count} 台，以下设备未找到：{missing_text}",
            )
        except ApiError as exc:
            QMessageBox.critical(self, "批量删除失败", str(exc))

    def _get_selected_devices(self) -> list[dict]:
        selected_ids: list[str] = []
        for row_index in range(self.table.rowCount()):
            checkbox = self._get_row_checkbox(row_index)
            if checkbox is not None and checkbox.isChecked():
                device_id = str(checkbox.property("device_id") or "")
                if device_id:
                    selected_ids.append(device_id)

        return [device for device in self.devices_cache if str(device.get("device_id", "")) in selected_ids]

    def _get_row_checkbox(self, row_index: int) -> QCheckBox | None:
        container = self.table.cellWidget(row_index, 0)
        if container is None:
            return None
        return container.findChild(QCheckBox)

    def show_detail_hint(self, device: dict) -> None:
        QMessageBox.information(
            self,
            "详情开发中",
            f"设备 {device.get('device_id', '')} / {device.get('device_name', '')} 的详情页会在下一阶段接入。",
        )

    def _map_status(self, value: str) -> str:
        status_map = {
            "active": "启用中",
            "maintenance": "维护中",
            "inactive": "已停用",
            "retired": "已报废",
        }
        return status_map.get(value, value or "-")
