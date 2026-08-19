from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox as QtMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _MessageDialog(QDialog):
    """项目统一消息弹窗，替代系统默认 QMessageBox 外观。"""

    def __init__(self, parent: QWidget | None, title: str, message: str, tone: str, confirm: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("MessageDialog")
        self.setProperty("tone", tone)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)

        # 左侧色带表达弹窗类型，不再使用尺寸不统一的系统图标。
        accent = QFrame()
        accent.setObjectName("DialogAccent")
        accent.setFixedWidth(4)
        header.addWidget(accent)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("DialogTitle")
        text_layout.addWidget(title_label)

        message_label = QLabel(message)
        message_label.setObjectName("DialogMessage")
        message_label.setWordWrap(True)
        # 文件路径和错误信息允许鼠标选择，便于复制排查。
        message_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_layout.addWidget(message_label)
        header.addLayout(text_layout, stretch=1)
        root.addLayout(header)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addStretch()

        if confirm:
            cancel_button = QPushButton("取消")
            cancel_button.setProperty("variant", "secondary")
            cancel_button.clicked.connect(self.reject)
            actions.addWidget(cancel_button)

        confirm_button = QPushButton("确认" if confirm else "确定")
        if confirm:
            confirm_button.setProperty("variant", "danger")
        confirm_button.clicked.connect(self.accept)
        confirm_button.setDefault(True)
        actions.addWidget(confirm_button)
        root.addLayout(actions)


class AppMessageBox:
    """保留 QMessageBox 静态调用接口，集中切换为项目自定义弹窗。"""

    StandardButton = QtMessageBox.StandardButton

    @staticmethod
    def information(parent: QWidget | None, title: str, message: str, *_args, **_kwargs):
        _MessageDialog(parent, title, message, "success").exec()
        return AppMessageBox.StandardButton.Ok

    @staticmethod
    def warning(parent: QWidget | None, title: str, message: str, *_args, **_kwargs):
        _MessageDialog(parent, title, message, "warning").exec()
        return AppMessageBox.StandardButton.Ok

    @staticmethod
    def critical(parent: QWidget | None, title: str, message: str, *_args, **_kwargs):
        _MessageDialog(parent, title, message, "error").exec()
        return AppMessageBox.StandardButton.Ok

    @staticmethod
    def question(parent: QWidget | None, title: str, message: str, *_args, **_kwargs):
        accepted = _MessageDialog(parent, title, message, "warning", confirm=True).exec() == QDialog.DialogCode.Accepted
        return AppMessageBox.StandardButton.Yes if accepted else AppMessageBox.StandardButton.No
