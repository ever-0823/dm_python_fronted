from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.domain.models.dashboard import DeviceStats
from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.widgets.stat_card import StatCard


class DashboardPage(QWidget):
    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.welcome_label = QLabel("欢迎进入设备管理控制台")
        self.welcome_label.setObjectName("PageTitle")

        self.total_card = StatCard("设备总数", "0")
        self.active_card = StatCard("启用中", "0")
        self.maintenance_card = StatCard("维护中", "0")
        self.inactive_card = StatCard("已停用", "0")
        self.retired_card = StatCard("已报废", "0")

        self.status_hint = QLabel("准备加载系统概况")
        self.status_hint.setObjectName("PageHint")

        self._build_ui()
        self.refresh_data()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self.welcome_label)
        top_bar.addStretch()

        refresh_button = QPushButton("刷新数据")
        refresh_button.clicked.connect(self.refresh_data)
        top_bar.addWidget(refresh_button)
        root.addLayout(top_bar)

        card_grid = QGridLayout()
        card_grid.setHorizontalSpacing(16)
        card_grid.setVerticalSpacing(16)
        card_grid.addWidget(self.total_card, 0, 0)
        card_grid.addWidget(self.active_card, 0, 1)
        card_grid.addWidget(self.maintenance_card, 0, 2)
        card_grid.addWidget(self.inactive_card, 1, 0)
        card_grid.addWidget(self.retired_card, 1, 1)
        root.addLayout(card_grid)

        hint_card = QFrame()
        hint_card.setObjectName("PageCard")
        hint_layout = QVBoxLayout(hint_card)
        hint_layout.setContentsMargins(20, 20, 20, 20)
        hint_layout.setSpacing(8)

        section_title = QLabel("本页说明")
        section_title.setObjectName("SectionTitle")
        hint_layout.addWidget(section_title)
        hint_layout.addWidget(QLabel("1. 这里会展示设备总数和状态统计。"))
        hint_layout.addWidget(QLabel("2. 后续我们会继续在这里加快捷入口、图表和最近操作。"))
        hint_layout.addWidget(self.status_hint)

        root.addWidget(hint_card, alignment=Qt.AlignmentFlag.AlignTop)
        root.addStretch()

    def refresh_data(self) -> None:
        try:
            current_user = self.api_client.get_current_user().get("data") or {}
            stats_response = self.api_client.get_device_statistics()
            stats = DeviceStats.from_dict(stats_response.get("data"))

            username = current_user.get("username") or "用户"
            self.welcome_label.setText(f"欢迎你，{username}")
            self.total_card.set_value(str(stats.total))
            self.active_card.set_value(str(stats.active))
            self.maintenance_card.set_value(str(stats.maintenance))
            self.inactive_card.set_value(str(stats.inactive))
            self.retired_card.set_value(str(stats.retired))
            self.status_hint.setText("数据加载成功，可以继续扩展仪表盘内容。")
        except ApiError as exc:
            self.status_hint.setText(str(exc))
