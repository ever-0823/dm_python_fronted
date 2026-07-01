from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.application.controllers.auth_controller import AuthController
from app.infrastructure.config import AppSettings
from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.devices_page import DevicesPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.widgets.sidebar import Sidebar


class MainWindow(QMainWindow):
    def __init__(self, settings: AppSettings, api_client: ApiClient, auth_controller: AuthController) -> None:
        super().__init__()
        self.settings = settings
        self.api_client = api_client
        self.auth_controller = auth_controller

        self.setWindowTitle(settings.app_name)
        self.resize(1360, 860)

        self.page_title = QLabel("仪表盘")
        self.page_title.setObjectName("PageTitle")
        self.page_hint = QLabel("这里是系统首页，我们先把整体骨架跑通。")
        self.page_hint.setObjectName("PageHint")
        self.status_label = QLabel(f"服务地址：{settings.api_base_url}")

        self.sidebar = Sidebar()
        self.sidebar.page_selected.connect(self.switch_page)

        self.pages = QStackedWidget()
        self.page_map = {}

        self._build_ui()
        self._build_pages()
        self.switch_page("dashboard", "仪表盘")
        self._refresh_user_info()

    def _build_ui(self) -> None:
        shell = QWidget()
        self.setCentralWidget(shell)

        root = QVBoxLayout(shell)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("HeaderBar")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        app_title = QLabel(self.settings.app_name)
        app_title.setObjectName("AppTitle")
        header_layout.addWidget(app_title)
        header_layout.addStretch()

        self.user_label = QLabel("当前用户：未加载")
        header_layout.addWidget(self.user_label)

        logout_button = QPushButton("退出登录")
        logout_button.setProperty("variant", "secondary")
        logout_button.clicked.connect(self.handle_logout)
        header_layout.addWidget(logout_button)
        root.addWidget(header)

        content = QHBoxLayout()
        content.setSpacing(12)

        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("Sidebar")
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.addWidget(self.sidebar)
        sidebar_frame.setFixedWidth(260)
        content.addWidget(sidebar_frame)

        main_surface = QFrame()
        main_surface.setObjectName("MainSurface")
        surface_layout = QVBoxLayout(main_surface)
        surface_layout.setContentsMargins(18, 18, 18, 18)
        surface_layout.setSpacing(16)

        self.page_header = QFrame()
        self.page_header.setObjectName("PageCard")
        page_header_layout = QVBoxLayout(self.page_header)
        page_header_layout.setContentsMargins(18, 16, 18, 16)
        page_header_layout.addWidget(self.page_title)
        page_header_layout.addWidget(self.page_hint)
        surface_layout.addWidget(self.page_header)
        surface_layout.addWidget(self.pages)
        content.addWidget(main_surface, stretch=1)

        root.addLayout(content, stretch=1)

        status_bar = QFrame()
        status_bar.setObjectName("StatusBar")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        status_layout.addWidget(QLabel("状态：桌面骨架已启动"))
        root.addWidget(status_bar)

    def _build_pages(self) -> None:
        page_definitions = {
            "dashboard": DashboardPage(self.api_client),
            "devices": DevicesPage(self.api_client),
            "new_device": PlaceholderPage("新建设备", "下一步我们会把新建设备弹窗接到这个入口上。"),
            "device_logs": PlaceholderPage("设备日志", "后续会支持按设备查看操作日志和时间线。"),
            "attachments": PlaceholderPage("附件管理", "后续会在这里集中展示附件上传、下载和删除能力。"),
            "import_export": PlaceholderPage("数据导入导出", "下一步可以把 CSV 导入导出页面接上。"),
            "profile": PlaceholderPage("当前用户", "后续这里会展示 auth/me 返回的完整用户信息。"),
            "users": PlaceholderPage("用户列表", "后续这里会展示用户列表和角色信息。"),
            "system": PlaceholderPage("服务状态", "后续这里会接健康检查和数据库连通检查。"),
        }

        for key, widget in page_definitions.items():
            self.page_map[key] = widget
            self.pages.addWidget(widget)

    def switch_page(self, page_key: str, title: str) -> None:
        widget = self.page_map.get(page_key)
        if widget is None:
            return
        self.pages.setCurrentWidget(widget)
        self.page_title.setText(title)
        hint = self._page_hint(page_key)
        self.page_hint.setText(hint)
        self.page_hint.setVisible(bool(hint))
        self.page_header.setVisible(page_key != "devices")

    def handle_logout(self) -> None:
        try:
            self.auth_controller.logout()
            QMessageBox.information(self, "退出成功", "登录状态已清除，请重新启动前端后再次登录。")
        except ApiError as exc:
            QMessageBox.warning(self, "已退出本地登录", f"本地登录状态已清除，但服务端退出返回异常：{exc}")
        finally:
            self.close()

    def _refresh_user_info(self) -> None:
        try:
            response = self.api_client.get_current_user()
            user = response.get("data") or {}
            username = user.get("username", "未知用户")
            role = user.get("role", "未知角色")
            self.user_label.setText(f"当前用户：{username} / {role}")
        except ApiError as exc:
            self.user_label.setText("当前用户：获取失败")
            self.status_label.setText(str(exc))

    def _page_hint(self, page_key: str) -> str:
        hints = {
            "dashboard": "这里展示设备总数和状态统计，是系统首页。",
            "devices": "",
            "new_device": "这里预留给新建设备流程。",
            "device_logs": "这里预留给操作日志查询与审计展示。",
            "attachments": "这里预留给附件的集中管理。",
            "import_export": "这里预留给 CSV 导入导出。",
            "profile": "这里预留给当前登录用户信息展示。",
            "users": "这里预留给用户列表与角色信息。",
            "system": "这里预留给服务与数据库状态监控。",
        }
        return hints.get(page_key, "")
