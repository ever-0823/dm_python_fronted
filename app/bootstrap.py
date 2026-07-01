import sys
from pathlib import Path

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
    # 为分页下拉框提供稳定可见的本地图标，避免系统默认箭头被样式覆盖后消失。
    pagination_arrow = (Path(__file__).resolve().parent / "ui" / "assets" / "chevron-down.svg").as_posix()
    # 将下拉框视觉升级为全局标准样式，后续新增页面时可以直接复用这一套企业风格。
    stylesheet = """
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
    QLabel {
    background-color: transparent;
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
    QPushButton[pagination="true"] {
        background-color: transparent;
        color: #374151;
        border: none;
        min-width: 26px;
        padding: 4px 5px;
        border-radius: 6px;
        font-size: 13px;
    }
    QPushButton[pagination="true"][active="true"] {
        color: #3b82f6;
        font-weight: 700;
    }
    QPushButton[paginationNav="true"] {
        background-color: transparent;
        color: #6b7280;
        border: none;
        min-width: 20px;
        padding: 4px 2px;
        font-size: 15px;
    }
    QPushButton[paginationNav="true"]:hover {
        color: #1f4e79;
        background-color: transparent;
    }
    QPushButton[paginationNav="true"]:disabled {
        color: #cbd5e1;
        background-color: transparent;
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
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #d1d5db;
        border-radius: 8px;
        padding: 8px 10px;
        min-height: 18px;
    }
    QLineEdit:focus {
        border: 1px solid #1f4e79;
    }
    QComboBox {
        background-color: #ffffff;
        border: 1px solid #d9e0ea;
        border-radius: 6px;
        min-height: 18px;
        padding: 6px 34px 6px 14px;
        color: #6b7280;
    }
    QComboBox:hover {
        border: 1px solid #cfd8e3;
        background-color: #ffffff;
    }
    QComboBox:on {
        border: 1px solid #cfd8e3;
        background-color: #ffffff;
    }
    QComboBox:focus {
        border: 1px solid #93c5fd;
    }
    QComboBox::drop-down {
        width: 30px;
        border: none;
        background-color: transparent;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }
    QComboBox::down-arrow {
        width: 12px;
        height: 12px;
        image: url(__PAGINATION_ARROW__);
    }
    QComboBox QAbstractItemView {
        background-color: #ffffff;
        color: #4b5563;
        border: 1px solid #d9e0ea;
        border-radius: 8px;
        outline: 0;
        padding: 4px;
        selection-background-color: #f3f6fb;
        selection-color: #374151;
    }
    QSpinBox#PaginationJumpSpin {
        background-color: #ffffff;
        border: 1px solid #d9e0ea;
        border-radius: 6px;
        min-height: 18px;
        padding: 6px 8px;
    }
    QSpinBox#PaginationJumpSpin {
        color: #6b7280;
    }
    QSpinBox#PaginationJumpSpin:focus {
        border: 1px solid #93c5fd;
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
    return stylesheet.replace("__PAGINATION_ARROW__", pagination_arrow)
