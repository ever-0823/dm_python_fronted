from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.application.controllers.auth_controller import AuthController
from app.infrastructure.http.api_client import ApiError


class LoginWindow(QWidget):
    login_succeeded = Signal()

    def __init__(self, auth_controller: AuthController) -> None:
        super().__init__()
        self.auth_controller = auth_controller
        self.setWindowTitle("登录 - 设备管理控制台")
        self.resize(480, 360)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入用户名")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #dc2626;")
        self.error_label.setWordWrap(True)

        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self.handle_login)

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)

        root.addStretch()

        wrapper = QHBoxLayout()
        wrapper.addStretch()

        card = QFrame()
        card.setObjectName("LoginCard")
        card.setFixedWidth(360)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setSpacing(12)

        title = QLabel("设备管理控制台")
        title.setObjectName("AppTitle")
        subtitle = QLabel("请输入账号信息，连接你的 FastAPI 后端服务")
        subtitle.setObjectName("PageHint")
        subtitle.setWordWrap(True)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(8)
        card_layout.addWidget(QLabel("用户名"))
        card_layout.addWidget(self.username_input)
        card_layout.addWidget(QLabel("密码"))
        card_layout.addWidget(self.password_input)
        card_layout.addWidget(self.error_label)
        card_layout.addSpacing(8)
        card_layout.addWidget(self.login_button)

        wrapper.addWidget(card)
        wrapper.addStretch()
        root.addLayout(wrapper)
        root.addStretch()

        self.password_input.returnPressed.connect(self.handle_login)

    def handle_login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            self.error_label.setText("请输入用户名和密码")
            return

        self.login_button.setEnabled(False)
        self.error_label.setText("")

        try:
            self.auth_controller.login(username, password)
            self.login_succeeded.emit()
        except ApiError as exc:
            self.error_label.setText(str(exc))
        finally:
            self.login_button.setEnabled(True)
