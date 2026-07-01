import sys

from PySide6.QtWidgets import QApplication

from app.application.controllers.auth_controller import AuthController
from app.infrastructure.config import AppSettings
from app.infrastructure.http.api_client import ApiClient, ApiError
from app.infrastructure.storage.token_store import TokenStore
from app.ui.windows.login_window import LoginWindow
from app.ui.windows.main_window import MainWindow

#应用入口函数，完成所有初始化并进入事件循环。
def bootstrap() -> None:
    # 初始化 Qt 应用实例
    app = QApplication(sys.argv)
    # 设置应用名称。
    app.setApplicationName("设备管理控制台")
    # 加载全局样式表，影响所有控件。
    app.setStyleSheet(load_stylesheet())

    settings = AppSettings()
    # 负责本地存储/读取认证令牌（通常存文件）
    token_store = TokenStore(settings.session_file)
    # 封装 HTTP 请求，自动携带 token，处理 ApiError。
    api_client = ApiClient(settings, token_store)
    # AuthController：业务层，协调认证逻辑（登录、登出、获取当前用户）。
    auth_controller = AuthController(api_client, token_store)

    # 用于跟踪已打开的窗口，便于切换时关闭旧窗口。
    windows: dict[str, object] = {}

    def open_main_window() -> None:
        # 创建主窗口并显示
        main_window = MainWindow(settings, api_client, auth_controller)
        main_window.show()
        windows["main_window"] = main_window
        # 若存在登录窗口，则将其关闭（切换窗口）
        if "login_window" in windows:
            windows["login_window"].close()

    try:
        # 如果本地有 token，尝试通过 API 获取当前用户信息
        if token_store.get_token():
            api_client.get_current_user()
            open_main_window()
        else:
            raise ApiError("未找到登录状态")
    except ApiError:
        login_window = LoginWindow(auth_controller)
        login_window.login_succeeded.connect(open_main_window)
        login_window.show()
        windows["login_window"] = login_window

    exit_code = app.exec()
    sys.exit(exit_code)


def load_stylesheet() -> str:
    return """
    QWidget {
        background-color: #f3f6fb;
        color: #1f2937;
        font-family: 'Microsoft YaHei';
        font-size: 13px;
    }
    QMainWindow, QFrame#MainSurface, QFrame#PageCard, QFrame#LoginCard, QFrame#Sidebar {
        background-color: #ffffff;
    }
    QFrame#HeaderBar, QFrame#ToolbarCard, QFrame#StatusBar, QFrame#StatCard {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
    }
    QFrame#Sidebar {
        border-right: 1px solid #e5e7eb;
    }
    QLabel#AppTitle {
        font-size: 22px;
        font-weight: 700;
        color: #163b62;
    }
    QLabel#PageTitle {
        font-size: 20px;
        font-weight: 700;
        color: #163b62;
    }
    QLabel#PageHint {
        color: #6b7280;
    }
    QLabel#StatValue {
        font-size: 28px;
        font-weight: 700;
        color: #163b62;
    }
    QLabel#StatLabel {
        color: #6b7280;
    }
    QLabel#SectionTitle {
        font-size: 15px;
        font-weight: 700;
        color: #163b62;
    }
    QPushButton {
        background-color: #1f4e79;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 16px;
        min-height: 18px;
    }
    QPushButton:hover {
        background-color: #285f92;
    }
    QPushButton:disabled {
        background-color: #9ca3af;
    }
    QPushButton[variant="secondary"] {
        background-color: #eef3f9;
        color: #1f4e79;
        border: 1px solid #d6e2ef;
    }
    QPushButton[compact="true"] {
        padding: 4px 10px;
        min-height: 14px;
        border-radius: 6px;
        font-size: 12px;
    }
    QPushButton[variant="danger"] {
        background-color: #c2410c;
    }
    QLineEdit, QComboBox {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 8px 10px;
        min-height: 18px;
    }
    QLineEdit:focus, QComboBox:focus {
        border: 1px solid #1f4e79;
    }
    QTreeWidget, QTableWidget {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        gridline-color: #edf0f5;
    }
    QHeaderView::section {
        background-color: #f8fafc;
        color: #374151;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #e5e7eb;
        font-weight: 700;
    }
    QTreeWidget::item {
        height: 30px;
    }
    QTreeWidget::item:selected {
        background-color: #e8f0f8;
        color: #163b62;
        border-radius: 6px;
    }
    QTableWidget::item {
        padding: 8px;
    }
    """
