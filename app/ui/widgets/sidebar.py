from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class Sidebar(QWidget):
    page_selected = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._handle_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self.tree)

        self._build_tree()

    def _build_tree(self) -> None:
        sections = {
            "首页": [("dashboard", "仪表盘")],
            "设备管理": [("devices", "设备列表"), ("new_device", "新建设备"), ("device_logs", "设备日志")],
            "文件与数据": [("attachments", "附件管理"), ("import_export", "数据导入导出")],
            "用户中心": [("profile", "当前用户"), ("users", "用户列表")],
            "系统管理": [("system", "服务状态")],
        }

        for section_title, children in sections.items():
            root = QTreeWidgetItem([section_title])
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.tree.addTopLevelItem(root)
            for page_key, child_title in children:
                child = QTreeWidgetItem([child_title])
                child.setData(0, Qt.ItemDataRole.UserRole, (page_key, child_title))
                root.addChild(child)
            root.setExpanded(True)

        first_item = self.tree.topLevelItem(0).child(0)
        self.tree.setCurrentItem(first_item)

    def _handle_item_clicked(self, item: QTreeWidgetItem, _: int) -> None:
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if payload:
            page_key, title = payload
            self.page_selected.emit(page_key, title)
