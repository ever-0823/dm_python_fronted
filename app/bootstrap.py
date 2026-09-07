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

    def open_login_window() -> None:
        # 退出登录后复用同一事件循环，直接创建新的登录窗口。
        login_window = LoginWindow(auth_controller)
        login_window.login_succeeded.connect(open_main_window)
        login_window.show()
        windows["login_window"] = login_window
        windows.pop("main_window", None)

    def open_main_window() -> None:
        # 创建主窗口并显示
        main_window = MainWindow(settings, api_client, auth_controller)
        main_window.logout_completed.connect(open_login_window)
        main_window.show()
        windows["main_window"] = main_window
        # 若存在登录窗口，则将其关闭（切换窗口）
        login_window = windows.pop("login_window", None)
        if login_window is not None:
            login_window.close()

    try:
        # 如果本地有 token，尝试通过 API 获取当前用户信息
        if token_store.get_token():
            api_client.get_current_user()
            open_main_window()
        else:
            raise ApiError("未找到登录状态")
    except ApiError:
        open_login_window()

    exit_code = app.exec()
    sys.exit(exit_code)


def load_stylesheet() -> str:
    # 为分页下拉框提供稳定可见的本地图标，避免系统默认箭头被样式覆盖后消失。
    pagination_arrow = (Path(__file__).resolve().parent / "ui" / "assets" / "chevron-down.svg").as_posix()
    # 全局样式集中维护颜色、尺寸和交互状态，页面只负责布局与业务逻辑。
    stylesheet = """
    /* 基础排版：子控件默认透明，避免表格操作列和复选框出现背景色块。 */
    QWidget {
        background-color: transparent;
        color: #202938;
        font-family: 'Microsoft YaHei';
        font-size: 13px;
    }
    QMainWindow, QWidget#LoginWindow {
        background-color: #f4f7fb;
    }
    QDialog {
        background-color: #ffffff;
    }
    QDialog#MessageDialog {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QFrame#DialogAccent {
        background-color: #1f4e79;
        border-radius: 2px;
    }
    QDialog#MessageDialog[tone="success"] QFrame#DialogAccent {
        background-color: #2f8f4e;
    }
    QDialog#MessageDialog[tone="warning"] QFrame#DialogAccent {
        background-color: #d9982b;
    }
    QDialog#MessageDialog[tone="error"] QFrame#DialogAccent {
        background-color: #c43d3d;
    }
    QLabel#DialogTitle {
        color: #173f67;
        font-size: 16px;
        font-weight: 700;
    }
    QLabel#DialogMessage {
        color: #475467;
        line-height: 1.4;
    }
    QMessageBox {
        background-color: #ffffff;
    }
    QMessageBox QLabel {
        color: #344054;
        min-width: 280px;
    }
    QMessageBox QPushButton {
        min-width: 72px;
    }
    /* 项目消息弹窗使用统一标题、正文间距和状态色带。 */
    QDialog#MessageDialog {
        background-color: #ffffff;
    }
    QLabel#DialogTitle {
        color: #173f67;
        font-size: 17px;
        font-weight: 700;
    }
    QLabel#DialogMessage {
        color: #475467;
    }
    QFrame#DialogAccent {
        background-color: #4d7ca8;
        border: none;
        border-radius: 2px;
    }
    QDialog#MessageDialog[tone="success"] QFrame#DialogAccent {
        background-color: #2f8f4e;
    }
    QDialog#MessageDialog[tone="warning"] QFrame#DialogAccent {
        background-color: #d9982b;
    }
    QDialog#MessageDialog[tone="error"] QFrame#DialogAccent {
        background-color: #c43d3d;
    }
    QLabel {
        background-color: transparent;
    }

    /* 页面容器：白色内容面配合细边框，保持企业后台的清晰层级。 */
    QFrame#MainSurface, QFrame#PageCard, QFrame#LoginCard, QFrame#Sidebar,
    QFrame#HeaderBar, QFrame#ToolbarCard, QFrame#StatusBar, QFrame#StatCard {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QFrame#MainSurface {
        border-color: #e7ecf2;
    }
    QFrame#Sidebar {
        border-radius: 8px;
    }
    QFrame#StatusBar {
        color: #64748b;
    }
    QFrame#AttachmentDropZone {
        background-color: #f8fbfe;
        border: 1px dashed #aebfd1;
        border-radius: 8px;
    }
    QFrame#AttachmentDropZone[dragActive="true"] {
        background-color: #eaf2f9;
        border: 2px dashed #4d7ca8;
    }
    QLabel#KnowledgeUploadIcon {
        color: #2f6fed;
        font-size: 28px;
        font-weight: 700;
    }
    QFrame#KnowledgeStepBar {
        background-color: #f7f9fc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QLabel#KnowledgeStepCircle {
        color: #667085;
        background-color: #e8edf3;
        border-radius: 13px;
        font-weight: 700;
    }
    QLabel#KnowledgeStepCircle[stepState="current"],
    QLabel#KnowledgeStepCircle[stepState="complete"] {
        color: #ffffff;
        background-color: #3f78ee;
    }
    QLabel#KnowledgeStepText {
        color: #667085;
    }
    QLabel#KnowledgeStepText[stepState="current"],
    QLabel#KnowledgeStepText[stepState="complete"] {
        color: #233b5d;
        font-weight: 700;
    }
    QFrame#KnowledgeStepLine {
        background-color: #dce3ec;
        border: none;
    }
    QFrame#KnowledgeStepLine[active="true"] {
        background-color: #3f78ee;
    }
    QFrame#KnowledgeSettingsPanel {
        background-color: #ffffff;
        border: none;
    }
    QFrame#KnowledgeOptionCard {
        background-color: #ffffff;
        border: 1px solid #d9e1eb;
        border-radius: 8px;
    }
    QFrame#KnowledgeOptionCard[selected="true"] {
        background-color: #f7faff;
        border: 2px solid #4a7ff0;
    }
    QFrame#KnowledgeSettingsPanel QRadioButton {
        color: #26364d;
        spacing: 8px;
        font-weight: 700;
    }
    QFrame#KnowledgeSettingsPanel QRadioButton::indicator {
        width: 15px;
        height: 15px;
    }
    QFrame#KnowledgePreviewPane {
        background-color: #ffffff;
        border: 1px solid #dfe6ee;
        border-radius: 8px;
    }
    QLabel#KnowledgeSelectedFile {
        color: #24415f;
        background-color: #eef4ff;
        border: 1px solid #5b87ee;
        border-radius: 7px;
        padding: 14px 12px;
    }
    QTableWidget#KnowledgeWizardTable {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        gridline-color: #edf1f5;
    }
    /* 向导表格单元格增加水平留白，不影响设备列表等其他表格。 */
    QTableWidget#KnowledgeWizardTable::item {
        padding-left: 12px;
        padding-right: 12px;
    }
    QTableWidget#KnowledgeWizardTable QHeaderView::section {
        background-color: #f5f7fa;
        color: #344054;
        padding: 10px 12px;
        border: none;
        border-bottom: 1px solid #dfe6ee;
        font-weight: 700;
    }
    QProgressBar#KnowledgeFileProgress {
        background-color: #e8edf3;
        color: #356046;
        border: none;
        border-radius: 4px;
        text-align: center;
        min-height: 8px;
        max-height: 18px;
    }
    QProgressBar#KnowledgeFileProgress::chunk {
        background-color: #37b978;
        border-radius: 4px;
    }
    /* 知识库工作台页签居中显示，数据集和搜索测试保持同一页面层级。 */
    QTabWidget#KnowledgeWorkspaceTabs {
        background-color: #ffffff;
    }
    QTabWidget#KnowledgeWorkspaceTabs::pane {
        background-color: #ffffff;
        border: none;
        border-top: 1px solid #e2e8f0;
    }
    QTabWidget#KnowledgeWorkspaceTabs::tab-bar {
        alignment: center;
    }
    QTabWidget#KnowledgeWorkspaceTabs QTabBar::tab {
        background-color: transparent;
        color: #475467;
        border: none;
        border-bottom: 2px solid transparent;
        padding: 11px 18px;
        min-width: 72px;
    }
    QTabWidget#KnowledgeWorkspaceTabs QTabBar::tab:selected {
        color: #2f6fed;
        border-bottom-color: #2f6fed;
        font-weight: 700;
    }
    QFrame#KnowledgeDatasetToolbar {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QLabel#KnowledgeDatasetCount {
        color: #173f67;
        font-size: 15px;
        font-weight: 700;
    }
    QTableWidget#KnowledgeDatasetTable,
    QTableWidget#KnowledgeChunksTable {
        border-radius: 8px;
    }
    /* 知识库聊天页采用独立会话栏、消息区和输入区，不影响其他业务页面。 */
    QFrame#KnowledgeChatPanel {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QFrame#KnowledgeChatSidebar {
        background-color: #f7f8fa;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
    }
    QLabel#KnowledgeChatSidebarTitle,
    QLabel#KnowledgeChatTitle {
        color: #173f67;
        font-size: 16px;
        font-weight: 700;
    }
    QPushButton#KnowledgeChatSession {
        background-color: #e8f0fb;
        color: #1f4e79;
        border: none;
        border-radius: 6px;
        padding: 8px 10px;
        text-align: left;
    }
    QFrame#KnowledgeChatHeader {
        background-color: #ffffff;
        border: none;
        border-bottom: 1px solid #e2e8f0;
    }
    QScrollArea#KnowledgeChatMessages,
    QWidget#KnowledgeChatMessagesContainer {
        background-color: #ffffff;
        border: none;
    }
    QFrame#KnowledgeChatWelcome {
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }
    QLabel#KnowledgeChatWelcomeTitle {
        color: #173f67;
        font-size: 24px;
        font-weight: 700;
    }
    QFrame#KnowledgeChatBubble {
        background-color: transparent;
        border: none;
        border-radius: 0;
    }
    QFrame#KnowledgeChatBubble[role="assistant"] {
        background-color: transparent;
        border: none;
    }
    QFrame#KnowledgeChatBubble[role="user"] {
        background-color: #f1f2f4;
        border: none;
        border-radius: 14px;
    }
    QLabel#KnowledgeChatAvatar {
        color: #ffffff;
        background-color: #2f6fed;
        border-radius: 16px;
        font-size: 11px;
        font-weight: 700;
    }
    QLabel#KnowledgeChatRole {
        color: #344054;
        font-size: 13px;
        font-weight: 700;
    }
    QLabel#KnowledgeChatMessage {
        color: #26364d;
        line-height: 1.5;
    }
    QLabel#KnowledgeChatMessage[role="user"] {
        color: #202938;
    }
    QLabel#KnowledgeChatSources {
        color: #667085;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 8px 10px;
        font-size: 12px;
    }
    QFrame#KnowledgeChatComposer {
        background-color: #ffffff;
        border: none;
        border-top: 1px solid #e2e8f0;
    }
    QFrame#KnowledgeChatInputShell {
        background-color: #ffffff;
        border: 1px solid #d0d5dd;
        border-radius: 22px;
    }
    QPlainTextEdit#KnowledgeChatInput {
        background-color: transparent;
        color: #202938;
        border: none;
        padding: 6px 4px;
    }
    QToolButton#KnowledgeChatSend {
        background-color: #8b8f94;
        color: #ffffff;
        border: none;
        border-radius: 18px;
        padding: 0;
        font-size: 20px;
        font-weight: 700;
    }
    QToolButton#KnowledgeChatSend:hover {
        background-color: #6f747a;
    }
    QToolButton#KnowledgeChatSend:pressed {
        background-color: #565b61;
    }
    QToolButton#KnowledgeChatSend:disabled {
        background-color: #d0d5dd;
        color: #ffffff;
    }
    QFrame#OcrDropZone {
        background-color: #f8fbfe;
        border: 1px dashed #aebfd1;
        border-radius: 8px;
        min-height: 64px;
    }
    QFrame#OcrDropZone[dragActive="true"] {
        background-color: #eaf2f9;
        border: 2px dashed #4d7ca8;
    }
    QLabel#OcrPreview {
        background-color: #f4f6f8;
        color: #98a2b3;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }
    QLabel#AttachmentFile {
        background-color: #f8fafc;
        color: #344054;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 8px 10px;
    }

    /* 标题层级：控制台标题、页面标题和区块标题使用同一深蓝体系。 */
    QLabel#AppTitle {
        font-size: 22px;
        font-weight: 700;
        color: #173f67;
    }
    QLabel#PageTitle {
        font-size: 20px;
        font-weight: 700;
        color: #173f67;
    }
    QLabel#PageHint {
        color: #667085;
    }
    QLabel#StatValue {
        font-size: 28px;
        font-weight: 700;
        color: #173f67;
    }
    QLabel#StatLabel {
        color: #667085;
    }
    QLabel#SectionTitle {
        font-size: 15px;
        font-weight: 700;
        color: #173f67;
    }
    QLabel#ErrorLabel {
        color: #b42318;
        background-color: #fef3f2;
        border: 1px solid #fecdca;
        border-radius: 5px;
        padding: 6px 8px;
    }
    QLabel#EmptyState {
        color: #98a2b3;
        background-color: #f8fafc;
        border: 1px dashed #d0d5dd;
        border-radius: 6px;
        padding: 12px 16px;
    }
    QLabel#ResultBanner {
        color: #475467;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        padding: 9px 12px;
    }
    QLabel#ResultBanner[status="loading"] {
        color: #1f4e79;
        background-color: #edf4fa;
        border-color: #bfd4e8;
    }
    QLabel#ResultBanner[status="success"] {
        color: #287a43;
        background-color: #edf8f1;
        border-color: #b7dfc3;
    }
    QLabel#ResultBanner[status="error"] {
        color: #b42318;
        background-color: #fef3f2;
        border-color: #fecdca;
    }
    QLabel#RoleBadge {
        color: #1f4e79;
        background-color: #edf3f8;
        border: 1px solid #cbd8e6;
        border-radius: 4px;
        padding: 3px 8px;
        font-size: 12px;
        font-weight: 700;
    }

    /* 仪表盘指标使用细色带区分语义，不增加额外图标或装饰组件。 */
    QFrame#StatCard {
        min-height: 94px;
    }
    QFrame#StatCard[metric="total"] {
        border-top: 3px solid #1f4e79;
    }
    QFrame#StatCard[metric="active"] {
        border-top: 3px solid #2f8f4e;
    }
    QFrame#StatCard[metric="maintenance"] {
        border-top: 3px solid #d9982b;
    }
    QFrame#StatCard[metric="inactive"] {
        border-top: 3px solid #98a2b3;
    }
    QFrame#StatCard[metric="retired"] {
        border-top: 3px solid #c43d3d;
    }
    QFrame#StatCard[metric="active"] QLabel#StatValue {
        color: #287a43;
    }
    QFrame#StatCard[metric="maintenance"] QLabel#StatValue {
        color: #9a5b13;
    }
    QFrame#StatCard[metric="inactive"] QLabel#StatValue {
        color: #667085;
    }
    QFrame#StatCard[metric="retired"] QLabel#StatValue {
        color: #a83232;
    }

    /* 按钮：统一 34px 左右的视觉高度，并补齐悬停、按压和禁用状态。 */
    QPushButton {
        background-color: #1f4e79;
        color: #ffffff;
        border: 1px solid #1f4e79;
        border-radius: 6px;
        padding: 6px 14px;
        min-height: 20px;
    }
    QPushButton:hover {
        background-color: #285f92;
        border-color: #285f92;
    }
    QPushButton:pressed {
        background-color: #173f67;
        border-color: #173f67;
    }
    QPushButton:disabled {
        background-color: #cbd5e1;
        border-color: #cbd5e1;
        color: #f8fafc;
    }
    QPushButton[variant="secondary"] {
        background-color: #f8fafc;
        color: #1f4e79;
        border: 1px solid #cbd8e6;
    }
    QPushButton[variant="secondary"]:hover {
        background-color: #edf3f8;
        border-color: #aebfd1;
    }
    QPushButton[variant="secondary"]:pressed {
        background-color: #e1eaf3;
    }
    QPushButton[variant="secondary"]:disabled {
        background-color: #f1f5f9;
        border-color: #e2e8f0;
        color: #94a3b8;
    }
    QPushButton[variant="danger"] {
        background-color: #c43d3d;
        border-color: #c43d3d;
    }
    QPushButton[variant="danger"]:hover {
        background-color: #ad3030;
        border-color: #ad3030;
    }
    QPushButton[variant="danger"]:pressed {
        background-color: #922929;
        border-color: #922929;
    }
    QPushButton[variant="danger"]:disabled {
        background-color: #e2e8f0;
        border-color: #e2e8f0;
        color: #94a3b8;
    }

    /* 知识库向导导航按钮用外边框表示焦点，移除文字内部虚线。 */
    QPushButton[wizardNavigation="true"] {
        outline: none;
    }
    QPushButton[wizardNavigation="true"]:focus {
        border: 2px solid #6f9fca;
        padding: 5px 13px;
    }

    /* 表格操作按钮仅显示文字，避免操作列出现重复边框和背景块。 */
    QPushButton[tableAction="true"] {
        background-color: transparent;
        color: #1f4e79;
        border: none;
        padding: 0px;
        min-height: 20px;
    }
    QPushButton[tableAction="true"]:hover {
        background-color: transparent;
        color: #285f92;
    }
    QPushButton[tableAction="true"]:pressed {
        background-color: transparent;
        color: #173f67;
    }

    /* 分页按钮保持轻量文字形态，不继承普通命令按钮的实体背景。 */
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
        color: #1f4e79;
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

    /* 表单控件：输入框、下拉框和跳页框使用同一边框与焦点反馈。 */
    QLineEdit {
        background-color: #ffffff;
        border: 1px solid #cfd8e3;
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 20px;
        selection-background-color: #bfd4e8;
    }
    QLineEdit:hover {
        border-color: #aebfd1;
    }
    QLineEdit:focus {
        border: 1px solid #4d7ca8;
    }
    QLineEdit:read-only {
        background-color: #f4f6f8;
        color: #667085;
    }
    QPlainTextEdit {
        background-color: #ffffff;
        color: #202938;
        border: 1px solid #dfe6ee;
        border-radius: 6px;
        padding: 10px;
        selection-background-color: #bfd4e8;
    }
    QTabWidget::pane {
        background-color: #ffffff;
        border: 1px solid #dfe6ee;
        border-radius: 6px;
        top: -1px;
    }
    QTabBar::tab {
        background-color: #f4f6f8;
        color: #667085;
        border: 1px solid #dfe6ee;
        padding: 8px 16px;
        min-width: 72px;
    }
    QTabBar::tab:selected {
        background-color: #ffffff;
        color: #173f67;
        font-weight: 700;
    }
    QSplitter::handle {
        background-color: #e2e8f0;
        width: 1px;
    }
    QComboBox {
        background-color: #ffffff;
        border: 1px solid #cfd8e3;
        border-radius: 6px;
        min-height: 20px;
        padding: 6px 34px 6px 14px;
        color: #475467;
    }
    QComboBox:hover {
        border-color: #aebfd1;
    }
    QComboBox:on {
        border-color: #4d7ca8;
    }
    QComboBox:focus {
        border: 1px solid #4d7ca8;
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
        color: #344054;
        border: 1px solid #cfd8e3;
        border-radius: 6px;
        outline: 0;
        padding: 4px;
        selection-background-color: #e8f0f8;
        selection-color: #173f67;
    }
    QSpinBox#PaginationJumpSpin {
        background-color: #ffffff;
        border: 1px solid #cfd8e3;
        border-radius: 6px;
        min-height: 20px;
        padding: 6px 8px;
        color: #475467;
    }
    QSpinBox#PaginationJumpSpin:focus {
        border: 1px solid #4d7ca8;
    }

    /* 菜单树：分组安静、功能入口明确，悬停和选中状态保持一致。 */
    QTreeWidget {
        background-color: #ffffff;
        border: none;
        outline: 0;
        padding: 4px;
        show-decoration-selected: 0;
    }
    QTreeWidget::item {
        height: 34px;
        padding: 0 8px;
        color: #475467;
        border-radius: 6px;
    }
    QTreeWidget::item:hover {
        background-color: #f1f5f9;
        color: #173f67;
    }
    QTreeWidget::item:selected {
        background-color: #e5eef7;
        color: #173f67;
        font-weight: 700;
    }
    QTreeWidget::branch {
        background-color: transparent;
    }
    QTreeWidget::branch:selected {
        background-color: transparent;
    }

    /* 数据表格：使用轻量斑马纹和清晰表头，减少横向信息噪声。 */
    QTableWidget {
        background-color: #ffffff;
        alternate-background-color: #f7f9fc;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        gridline-color: #edf1f5;
        color: #202938;
    }
    QHeaderView::section {
        background-color: #f2f5f8;
        color: #344054;
        padding: 8px;
        border: none;
        border-bottom: 1px solid #dfe6ee;
        font-weight: 700;
    }
    QTableWidget::item {
        padding: 8px;
    }

    /* 设备状态标签使用低饱和底色，便于快速区分运行状态。 */
    QLabel#StatusBadge {
        border-radius: 4px;
        padding: 3px 8px;
        font-size: 12px;
        font-weight: 700;
    }
    QLabel#StatusBadge[status="active"] {
        background-color: #e8f5ec;
        color: #287a43;
    }
    QLabel#StatusBadge[status="maintenance"] {
        background-color: #fff3dc;
        color: #9a5b13;
    }
    QLabel#StatusBadge[status="inactive"] {
        background-color: #eef1f4;
        color: #667085;
    }
    QLabel#StatusBadge[status="retired"] {
        background-color: #fdeaea;
        color: #a83232;
    }
    QLabel#StatusBadge[status="unknown"] {
        background-color: #eef1f4;
        color: #667085;
    }

    /* 滚动条和提示框沿用低干扰中性色，避免抢占主要操作视觉。 */
    QScrollBar:vertical {
        background-color: transparent;
        width: 10px;
        margin: 2px;
    }
    QScrollBar::handle:vertical {
        background-color: #cbd5e1;
        border-radius: 4px;
        min-height: 28px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #aebac8;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background-color: transparent;
        border: none;
        height: 0px;
    }
    QToolTip {
        background-color: #202938;
        color: #ffffff;
        border: none;
        padding: 5px 8px;
    }
    """
    return stylesheet.replace("__PAGINATION_ARROW__", pagination_arrow)
