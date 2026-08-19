import os

# 离屏模式让自检无需打开真实窗口，适合本地或 CI 直接运行。
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from app.ui.dialogs.message_box import _MessageDialog


def main() -> None:
    app = QApplication.instance() or QApplication([])

    info_dialog = _MessageDialog(None, "成功", "操作完成", "success")
    assert [button.text() for button in info_dialog.findChildren(QPushButton)] == ["确定"]

    confirm_dialog = _MessageDialog(None, "删除确认", "删除后不可恢复", "warning", confirm=True)
    assert [button.text() for button in confirm_dialog.findChildren(QPushButton)] == ["取消", "确认"]
    assert app is not None


if __name__ == "__main__":
    main()
