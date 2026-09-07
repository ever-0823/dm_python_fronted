from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QStyle, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget


class Sidebar(QWidget):
    page_selected = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        # 侧边栏菜单树负责承载一级分组和二级功能入口。
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        # 固定缩进和行高，让一级分组与二级入口形成稳定层级。
        self.tree.setIndentation(18)
        # 隐藏树控件预留但不可见的原生分支，把自定义箭头放到最左侧点击区。
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(True)
        # 一级菜单使用 Qt 原生箭头，并在展开或折叠时同步更新方向。
        self.tree.itemExpanded.connect(self._update_section_icon)
        self.tree.itemCollapsed.connect(self._update_section_icon)
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
            "文件与数据": [
                ("ocr", "图片文字识别"),
                ("attachments", "附件管理"),
                ("import_export", "数据导入导出"),
                # 向量知识库使用单一入口，数据集和搜索测试在页面顶部切换。
                ("knowledge", "向量知识库"),
            ],
            "用户中心": [("profile", "当前用户"), ("users", "用户列表")],
            "系统管理": [("system", "服务状态")],
        }

        for section_title, children in sections.items():
            root = QTreeWidgetItem([section_title])
            # 一级节点只做分组展示，不允许被直接选中。
            root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            # 一级分组使用粗体，帮助用户快速扫描菜单结构。
            section_font = QFont(self.tree.font())
            section_font.setBold(True)
            root.setFont(0, section_font)
            root.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
            self.tree.addTopLevelItem(root)
            for menu_item in children:
                page_key, child_title = menu_item[:2]
                child = QTreeWidgetItem([child_title])
                root.addChild(child)
                nested_items = menu_item[2] if len(menu_item) == 3 else []
                if nested_items:
                    # 有下级菜单的节点只负责展开和收起，不直接切换页面。
                    child.setFlags(child.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                    child.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
                    for nested_key, nested_title in nested_items:
                        nested = QTreeWidgetItem([nested_title])
                        # 末级节点保存页面 key，主窗口据此切换页面。
                        nested.setData(0, Qt.ItemDataRole.UserRole, (nested_key, nested_title))
                        child.addChild(nested)
                    child.setExpanded(True)
                else:
                    # 将页面 key 和标题挂到末级节点上，点击时可直接读取。
                    child.setData(0, Qt.ItemDataRole.UserRole, (page_key, child_title))
            root.setExpanded(True)

        # 默认选中第一个功能入口，保证首次进入时导航状态明确。
        first_item = self.tree.topLevelItem(0).child(0)
        self.tree.setCurrentItem(first_item)

    def _update_section_icon(self, item: QTreeWidgetItem) -> None:
        """根据一级菜单的展开状态切换方向符号。"""
        if not item.childCount():
            return
        icon_type = QStyle.StandardPixmap.SP_ArrowDown if item.isExpanded() else QStyle.StandardPixmap.SP_ArrowRight
        item.setIcon(0, self.style().standardIcon(icon_type))

    def select_page(self, page_key: str) -> None:
        """按页面标识同步菜单选中状态。"""
        # 菜单数量较少，直接遍历可保持实现清晰且无需额外索引结构。
        for root_index in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(root_index)
            stack = [root]
            while stack:
                item = stack.pop()
                payload = item.data(0, Qt.ItemDataRole.UserRole)
                if payload and payload[0] == page_key:
                    # 展开当前节点的所有父级，保证切页后用户能看到选中项。
                    parent = item.parent()
                    while parent is not None:
                        parent.setExpanded(True)
                        parent = parent.parent()
                    self.tree.setCurrentItem(item)
                    return
                stack.extend(item.child(index) for index in range(item.childCount()))

    def _handle_item_clicked(self, item: QTreeWidgetItem, _: int) -> None:
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        # 点击一级菜单的箭头或文字都可展开、收起对应功能列表。
        if not payload and item.childCount():
            item.setExpanded(not item.isExpanded())
            return
        if payload:
            page_key, title = payload
            # 侧边栏只负责发出导航信号，不直接操作页面容器。
            self.page_selected.emit(page_key, title)
