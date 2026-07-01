from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.infrastructure.http.api_client import ApiClient, ApiError


class DeviceFormDialog(QDialog):
    device_saved = Signal()

    def __init__(self, api_client: ApiClient, device: dict | None = None, parent=None) -> None:
        super().__init__(parent)
        self.api_client = api_client
        self.device = device or {}
        self.is_edit_mode = bool(device)
        self.setWindowTitle("编辑设备" if self.is_edit_mode else "新建设备")
        self.resize(460, 360)
        self.setModal(True)

        self.device_id_input = QLineEdit()
        self.device_name_input = QLineEdit()
        self.model_input = QLineEdit()
        self.manufacturer_input = QLineEdit()
        self.location_input = QLineEdit()

        self.status_input = QComboBox()
        self.status_input.addItem("启用中", "active")
        self.status_input.addItem("维护中", "maintenance")
        self.status_input.addItem("已停用", "inactive")
        self.status_input.addItem("已报废", "retired")

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #dc2626;")
        self.error_label.setWordWrap(True)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.setProperty("variant", "secondary")
        self.cancel_button.clicked.connect(self.reject)

        self.submit_button = QPushButton("保存修改" if self.is_edit_mode else "确定创建")
        self.submit_button.clicked.connect(self.submit)

        self._build_ui()
        self._load_initial_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        intro = QLabel("请填写设备基础信息，提交后将调用后端设备保存接口。")
        intro.setObjectName("PageHint")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(form.labelAlignment())
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("设备编号", self.device_id_input)
        form.addRow("设备名称", self.device_name_input)
        form.addRow("设备型号", self.model_input)
        form.addRow("厂商名称", self.manufacturer_input)
        form.addRow("所在位置", self.location_input)
        form.addRow("设备状态", self.status_input)
        root.addLayout(form)
        root.addWidget(self.error_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.submit_button)
        root.addLayout(button_row)

        self.device_id_input.setPlaceholderText("例如 D1001")
        self.device_name_input.setPlaceholderText("例如 仓库扫码终端")
        self.model_input.setPlaceholderText("例如 M-100")
        self.manufacturer_input.setPlaceholderText("例如 OpenAI Devices")
        self.location_input.setPlaceholderText("例如 上海仓库 A 区")

    def _load_initial_data(self) -> None:
        if not self.is_edit_mode:
            return

        self.device_id_input.setText(str(self.device.get("device_id", "")))
        self.device_id_input.setReadOnly(True)
        self.device_name_input.setText(str(self.device.get("device_name", "")))
        self.model_input.setText(str(self.device.get("model", "")))
        self.manufacturer_input.setText(str(self.device.get("manufacturer", "")))
        self.location_input.setText(str(self.device.get("location", "")))

        status = str(self.device.get("status", "active"))
        index = self.status_input.findData(status)
        if index >= 0:
            self.status_input.setCurrentIndex(index)

    def submit(self) -> None:
        payload = {
            "device_id": self.device_id_input.text().strip(),
            "device_name": self.device_name_input.text().strip(),
            "model": self.model_input.text().strip(),
            "manufacturer": self.manufacturer_input.text().strip(),
            "location": self.location_input.text().strip(),
            "status": self.status_input.currentData(),
        }

        validation_error = self._validate(payload)
        if validation_error:
            self.error_label.setText(validation_error)
            return

        self.submit_button.setEnabled(False)
        self.error_label.setText("")

        try:
            if self.is_edit_mode:
                self.api_client.update_device(payload["device_id"], self._build_update_payload(payload))
            else:
                self.api_client.create_device(payload)
            self.device_saved.emit()
            self.accept()
        except ApiError as exc:
            self.error_label.setText(str(exc))
        finally:
            self.submit_button.setEnabled(True)

    def _validate(self, payload: dict) -> str:
        required_fields = {
            "device_id": "设备编号不能为空",
            "device_name": "设备名称不能为空",
            "model": "设备型号不能为空",
            "manufacturer": "厂商名称不能为空",
            "location": "所在位置不能为空",
        }

        for field_name, message in required_fields.items():
            if not payload.get(field_name):
                return message

        return ""

    def _build_update_payload(self, payload: dict) -> dict:
        return {
            "device_name": payload["device_name"],
            "model": payload["model"],
            "manufacturer": payload["manufacturer"],
            "location": payload["location"],
            "status": payload["status"],
        }
