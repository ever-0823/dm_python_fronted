from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.config import AppSettings
from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class EditProfileDialog(QDialog):
    def __init__(self, current_username: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑资料")
        self.setModal(True)
        self.resize(360, 180)

        self.username_input = QLineEdit(current_username)

        self.submit_button = QPushButton("保存资料")
        self.submit_button.clicked.connect(self.accept)

        cancel_button = QPushButton("取消")
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("用户名", self.username_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(self.submit_button)
        root.addLayout(actions)

    def get_username(self) -> str:
        return self.username_input.text().strip()


class ChangePasswordDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("修改密码")
        self.setModal(True)
        self.resize(400, 220)

        self.current_password_input = QLineEdit()
        self.current_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_password_input = QLineEdit()
        self.new_password_input.setEchoMode(QLineEdit.EchoMode.Password)

        submit_button = QPushButton("确认修改")
        submit_button.clicked.connect(self.accept)

        cancel_button = QPushButton("取消")
        cancel_button.setProperty("variant", "secondary")
        cancel_button.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.addRow("当前密码", self.current_password_input)
        form.addRow("新密码", self.new_password_input)
        root.addLayout(form)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(submit_button)
        root.addLayout(actions)

    def get_payload(self) -> dict[str, str]:
        return {
            "current_password": self.current_password_input.text().strip(),
            "new_password": self.new_password_input.text().strip(),
        }


class CurrentUserPage(QWidget):
    profile_updated = Signal()

    def __init__(self, settings: AppSettings, api_client: ApiClient) -> None:
        super().__init__()
        self.settings = settings
        self.api_client = api_client

        self.status_hint = QLabel("准备加载当前用户信息。")
        self.status_hint.setObjectName("ResultBanner")
        self.status_hint.setProperty("status", "info")
        self.status_hint.setWordWrap(True)

        self.user_id_value = QLabel("-")
        self.username_value = QLabel("-")
        self.role_value = QLabel("-")
        self.role_value.setObjectName("RoleBadge")
        self.role_value.setMinimumWidth(72)
        self.role_value.setMaximumWidth(120)
        self.role_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_status_value = QLabel("未校验")
        self.login_status_value.setObjectName("StatusBadge")
        self.login_status_value.setProperty("status", "unknown")
        self.login_status_value.setFixedWidth(72)
        self.login_status_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.service_value = QLabel(settings.api_base_url)

        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        # ponytail: 当前页只展示 auth/me 现成能拿到的数据，不为“未来资料页”先搭复杂结构。
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self.status_hint)

        info_card = QFrame()
        info_card.setObjectName("PageCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(14)

        header_row = QHBoxLayout()
        section_title = QLabel("账户信息")
        section_title.setObjectName("SectionTitle")
        header_row.addWidget(section_title)
        header_row.addStretch()

        self.refresh_button = QPushButton("刷新信息")
        self.refresh_button.setProperty("variant", "secondary")
        self.refresh_button.clicked.connect(self.refresh_data)
        edit_button = QPushButton("编辑资料")
        edit_button.setProperty("variant", "secondary")
        edit_button.clicked.connect(self.edit_profile)
        change_password_button = QPushButton("修改密码")
        change_password_button.clicked.connect(self.change_password)
        header_row.addWidget(edit_button)
        header_row.addWidget(change_password_button)
        header_row.addWidget(self.refresh_button)
        info_layout.addLayout(header_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        self._add_info_row(grid, 0, "用户 ID", self.user_id_value)
        self._add_info_row(grid, 0, "用户名", self.username_value, 2)
        self._add_info_row(grid, 1, "角色", self.role_value)
        self._add_info_row(grid, 1, "登录状态", self.login_status_value, 2)
        self._add_info_row(grid, 2, "服务地址", self.service_value)
        info_layout.addLayout(grid)
        root.addWidget(info_card)

        root.addStretch()

    def _add_info_row(self, grid: QGridLayout, row: int, label_text: str, value_label: QLabel, column: int = 0) -> None:
        label = QLabel(f"{label_text}：")
        label.setObjectName("PageHint")
        grid.addWidget(label, row, column)
        grid.addWidget(value_label, row, column + 1)

    def refresh_data(self) -> None:
        self.refresh_button.setEnabled(False)
        self._set_feedback("正在刷新当前用户信息...", "loading")
        try:
            response = self.api_client.get_current_user()
            user = response.get("data") or {}
            self.user_id_value.setText(str(user.get("id", "-")))
            self.username_value.setText(str(user.get("username", "-")))
            self.role_value.setText(str(user.get("role", "-")))
            self.login_status_value.setText("已登录")
            self.login_status_value.setProperty("status", "active")
            self.login_status_value.style().unpolish(self.login_status_value)
            self.login_status_value.style().polish(self.login_status_value)
            self._set_feedback("当前用户信息已更新。", "success")
        except ApiError as exc:
            self.user_id_value.setText("-")
            self.username_value.setText("-")
            self.role_value.setText("-")
            self.login_status_value.setText("获取失败")
            self.login_status_value.setProperty("status", "unknown")
            self.login_status_value.style().unpolish(self.login_status_value)
            self.login_status_value.style().polish(self.login_status_value)
            self._set_feedback(str(exc), "error")
        finally:
            self.refresh_button.setEnabled(True)

    def edit_profile(self) -> None:
        dialog = EditProfileDialog(self.username_value.text(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        username = dialog.get_username()
        if not username:
            QMessageBox.warning(self, "更新失败", "用户名不能为空")
            return

        try:
            # 保存成功后直接刷新当前页，避免手工同步每个显示控件。
            self.api_client.update_profile(username)
            self.refresh_data()
            self._set_feedback("资料更新成功。", "success")
            self.profile_updated.emit()
        except ApiError as exc:
            QMessageBox.critical(self, "更新失败", str(exc))
            self._set_feedback(f"资料更新失败：{exc}", "error")

    def change_password(self) -> None:
        dialog = ChangePasswordDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.get_payload()
        if not payload["current_password"] or not payload["new_password"]:
            QMessageBox.warning(self, "修改失败", "请填写当前密码和新密码")
            return

        try:
            self.api_client.change_password(payload["current_password"], payload["new_password"])
            QMessageBox.information(self, "修改成功", "密码已更新，请使用新密码重新登录。")
            self._set_feedback("密码修改成功。", "success")
        except ApiError as exc:
            QMessageBox.critical(self, "修改失败", str(exc))
            self._set_feedback(f"密码修改失败：{exc}", "error")

    def _set_feedback(self, message: str, status: str) -> None:
        # 账户操作复用全局反馈条样式，并立即刷新同步请求前的加载状态。
        self.status_hint.setText(message)
        self.status_hint.setProperty("status", status)
        self.status_hint.style().unpolish(self.status_hint)
        self.status_hint.style().polish(self.status_hint)
        QApplication.processEvents()
