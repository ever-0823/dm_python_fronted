from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class Sidebar(QWidget):
    page_selected = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        # 侧边栏菜单树负责承载一级分组和二级功能入口。
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        # 点击具体页面节点后，把页面标识交给主窗口处理。
        self.tree.itemClicked.connect(self._handle_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.tree)

        self._build_tree()

    def _build_tree(self) -> None:
        # 菜单结构集中定义，后续新增模块时只需要改这里。
        sections = {
            "首页": [("dashboard", "仪表盘")],
            "设备管理": [("devices", "设备列表"), ("new_device", "新建设备"), ("device_logs", "设备日志")],
            "文件与数据": [("attachments", "附件管理"), ("import_export", "数据导入导出")],
            "用户中心": [("profile", "当前用户"), ("users", "用户列表")],
            "系统管理": [("system", "服务状态")],
        }

        for section_title, children in sections.items():
            root = QTreeWidgetItem([section_title])
            # 一级节点只做分组展示，不允许被直接选中。
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(root)
            for page_key, child_title in children:
                child = QTreeWidgetItem([child_title])
                # 将页面 key 和标题挂到节点上，点击时可直接读取。
                child.setData(0, Qt.ItemDataRole.UserRole, (page_key, child_title))
                root.addChild(child)
            root.setExpanded(True)

        # 默认选中第一个功能入口，保证首次进入时导航状态明确。
        first_item = self.tree.topLevelItem(0).child(0)
        self.tree.setCurrentItem(first_item)

    def _handle_item_clicked(self, item: QTreeWidgetItem, _: int) -> None:
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if payload:
            page_key, title = payload
            # 侧边栏只负责发出导航信号，不直接操作页面容器。
            self.page_selected.emit(page_key, title)
