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
    QSpinBox,
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
    detail_requested = Signal(str)

    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入设备编号或设备名称")

        self.status_filter = QComboBox()
        # 设备筛选下拉框与分页下拉框统一为同一套企业风格和高度。
        self.status_filter.setFixedHeight(34)
        self.status_filter.addItem("全部", "")
        self.status_filter.addItem("启用中", "active")
        self.status_filter.addItem("维护中", "maintenance")
        self.status_filter.addItem("已停用", "inactive")
        self.status_filter.addItem("已报废", "retired")

        self.table = QTableWidget(0, 8)
        self.header = SelectAllHeader(self.table)
        self.table.setHorizontalHeader(self.header)
        self.header.toggled.connect(self.set_all_rows_checked)

        self.page_hint = QLabel("")
        self.page_hint.setObjectName("PageHint")
        self.page_hint.setVisible(False)
        self.total_label = QLabel("Total 0")
        self.total_label.setObjectName("PageHint")
        self.new_button = QPushButton("新建设备")
        self.batch_delete_button = QPushButton("批量删除")
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItem("10/page", 10)
        self.page_size_combo.addItem("20/page", 20)
        self.page_size_combo.addItem("50/page", 50)
        self.prev_page_button = QPushButton("<")
        self.next_page_button = QPushButton(">")
        self.jump_page_spin = QSpinBox()
        self.jump_page_spin.setMinimum(1)
        self.jump_page_spin.setMaximum(1)
        # 统一维护页码按钮，后续扩展页码显示范围时更容易调整。
        self.page_buttons = [QPushButton(str(index)) for index in range(1, 5)]
        self.devices_cache: list[dict] = []
        self.current_page = 1
        self.page_size = 10
        self.total_pages = 0
        self.total_count = 0

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

        pager_row = QHBoxLayout()
        pager_row.setContentsMargins(0, 8, 0, 2)
        pager_row.setSpacing(14)
        pager_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pager_row.addWidget(self.total_label)
        self.page_size_combo.currentIndexChanged.connect(self.change_page_size)
        self.page_size_combo.setObjectName("PaginationSizeCombo")
        # 分页条数选择器按参考图拉宽一些，保证留白和箭头区域更自然。
        self.page_size_combo.setFixedWidth(136)
        # 与跳页输入框统一高度，保证分页区视觉基线一致。
        self.page_size_combo.setFixedHeight(34)
        pager_row.addWidget(self.page_size_combo)

        self.prev_page_button.setProperty("paginationNav", "true")
        self.prev_page_button.clicked.connect(self.go_prev_page)
        pager_row.addWidget(self.prev_page_button)

        for button in self.page_buttons:
            button.setProperty("pagination", "true")
            # 用默认参数锁定当前按钮实例，避免 lambda 捕获最后一个按钮。
            button.clicked.connect(lambda _checked=False, current_button=button: self.go_to_page(int(current_button.text())))
            pager_row.addWidget(button)

        self.next_page_button.setProperty("paginationNav", "true")
        self.next_page_button.clicked.connect(self.go_next_page)
        pager_row.addWidget(self.next_page_button)

        pager_row.addWidget(QLabel("Go to"))
        self.jump_page_spin.setObjectName("PaginationJumpSpin")
        self.jump_page_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.jump_page_spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.jump_page_spin.setFixedWidth(64)
        # 与每页条数下拉框统一高度，避免两个控件上下尺寸不一致。
        self.jump_page_spin.setFixedHeight(34)
        # 失焦后自动跳转，界面上无需再保留单独的“Go to”按钮。
        self.jump_page_spin.editingFinished.connect(self.go_jump_page)
        pager_row.addWidget(self.jump_page_spin)

        root.addWidget(self.page_hint, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addLayout(pager_row)

    def reset_filters(self) -> None:
        self.search_input.clear()
        self.status_filter.setCurrentIndex(0)
        self.current_page = 1
        self.load_devices()

    def load_devices(self) -> None:
        try:
            response = self.api_client.get_devices(
                page=self.current_page,
                page_size=self.page_size,
                search=self.search_input.text().strip(),
                status=self.status_filter.currentData() or "",
            )
            data = response.get("data") or {}
            items = data.get("items") or []
            total = int(data.get("total") or 0)
            total_pages = int(data.get("total_pages") or 0)

            if total_pages > 0 and self.current_page > total_pages:
                self.current_page = total_pages
                self.load_devices()
                return

            self.devices_cache = items
            self.total_pages = total_pages
            self.total_count = total

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
            self.page_hint.clear()
            self.page_hint.setVisible(False)
            self._update_pagination_ui()
        except ApiError as exc:
            self.table.setRowCount(0)
            self.devices_cache = []
            self.header.set_checked(False)
            self.page_hint.setText(str(exc))
            self.page_hint.setVisible(True)
            self.total_pages = 0
            self.total_count = 0
            self._update_pagination_ui()

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

        # 复选框
        checkbox = QCheckBox()
        container.setStyleSheet("background-color: transparent;")
        checkbox.setStyleSheet("background-color: transparent;")
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
        edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_button.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #1f4e79; padding: 0px; }"
            "QPushButton:hover { color: #285f92; text-decoration: underline; }"
        )
        edit_button.clicked.connect(lambda: self.open_edit_dialog(device))
        layout.addWidget(edit_button)

        detail_button = QPushButton("详情")
        detail_button.setCursor(Qt.CursorShape.PointingHandCursor)
        detail_button.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #1f4e79; padding: 0px; }"
            "QPushButton:hover { color: #285f92; text-decoration: underline; }"
        )
        detail_button.clicked.connect(lambda: self.open_detail(device))
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

    def change_page_size(self) -> None:
        self.page_size = int(self.page_size_combo.currentData() or 10)
        self.current_page = 1
        self.load_devices()

    def go_prev_page(self) -> None:
        if self.current_page <= 1:
            return
        self.current_page -= 1
        self.load_devices()

    def go_next_page(self) -> None:
        if self.total_pages == 0 or self.current_page >= self.total_pages:
            return
        self.current_page += 1
        self.load_devices()

    def go_jump_page(self) -> None:
        target_page = int(self.jump_page_spin.value())
        if target_page == self.current_page:
            return
        self.current_page = target_page
        self.load_devices()

    def go_to_page(self, target_page: int) -> None:
        if target_page < 1 or target_page > self.total_pages or target_page == self.current_page:
            return
        self.current_page = target_page
        self.load_devices()

    def _update_pagination_ui(self) -> None:
        if self.total_pages <= 0:
            self.total_label.setText("Total 0")
            self.prev_page_button.setEnabled(False)
            for button in self.page_buttons:
                button.setVisible(False)
            self.next_page_button.setEnabled(False)
            self.jump_page_spin.setMaximum(1)
            self.jump_page_spin.setValue(1)
            self.jump_page_spin.setEnabled(False)
            return

        self.total_label.setText(f"Total {self.total_count}")
        self.prev_page_button.setEnabled(self.current_page > 1)
        self.next_page_button.setEnabled(self.current_page < self.total_pages)
        self.jump_page_spin.setMaximum(max(self.total_pages, 1))
        self.jump_page_spin.setValue(self.current_page)
        self.jump_page_spin.setEnabled(self.total_pages > 1)
        self._update_page_number_buttons()

    def _update_page_number_buttons(self) -> None:
        if self.total_pages <= 0:
            for button in self.page_buttons:
                button.setVisible(False)
            return

        # 让当前页尽量落在中间区域，视觉上更接近企业后台常见分页布局。
        if self.total_pages <= len(self.page_buttons):
            start_page = 1
        else:
            half_window = len(self.page_buttons) // 2
            start_page = max(1, min(self.current_page - half_window, self.total_pages - len(self.page_buttons) + 1))

        for offset, button in enumerate(self.page_buttons):
            page_number = start_page + offset
            visible = page_number <= self.total_pages
            button.setVisible(visible)
            if not visible:
                continue
            button.setText(str(page_number))
            is_current = page_number == self.current_page
            button.setProperty("active", "true" if is_current else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def open_detail(self, device: dict) -> None:
        device_id = str(device.get("device_id", "") or "")
        if not device_id:
            QMessageBox.warning(self, "无法打开详情", "当前设备缺少设备编号。")
            return
        self.detail_requested.emit(device_id)

    def _map_status(self, value: str) -> str:
        status_map = {
            "active": "启用中",
            "maintenance": "维护中",
            "inactive": "已停用",
            "retired": "已报废",
        }
        return status_map.get(value, value or "-")
