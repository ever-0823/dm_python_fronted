from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.infrastructure.http.api_client import ApiClient, ApiError
from app.ui.dialogs.message_box import AppMessageBox as QMessageBox


class ImportExportPage(QWidget):
    def __init__(self, api_client: ApiClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.result_label = QLabel("准备就绪，可下载模板、导出设备或导入 CSV。")
        self.result_label.setObjectName("ResultBanner")
        self.result_label.setProperty("status", "info")
        self.result_label.setWordWrap(True)
        self._build_ui()

    def _build_ui(self) -> None:
        # 页面采用双卡片结构，分别承载导出和导入动作，便于企业后台场景快速操作。
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self.result_label)

        export_card = QFrame()
        export_card.setObjectName("PageCard")
        export_layout = QVBoxLayout(export_card)
        export_layout.setContentsMargins(18, 18, 18, 18)
        export_layout.setSpacing(12)

        export_title = QLabel("导出设备数据")
        export_title.setObjectName("SectionTitle")
        export_layout.addWidget(export_title)
        export_layout.addWidget(QLabel("将当前设备库导出为标准 CSV 文件，便于备份、分析或二次整理。"))

        export_actions = QHBoxLayout()
        self.export_button = QPushButton("导出设备 CSV")
        self.export_button.clicked.connect(self.export_devices)
        export_actions.addWidget(self.export_button)

        self.template_button = QPushButton("下载导入模板")
        self.template_button.setProperty("variant", "secondary")
        self.template_button.clicked.connect(self.download_template)
        export_actions.addWidget(self.template_button)
        export_actions.addStretch()
        export_layout.addLayout(export_actions)
        root.addWidget(export_card)

        import_card = QFrame()
        import_card.setObjectName("PageCard")
        import_layout = QVBoxLayout(import_card)
        import_layout.setContentsMargins(18, 18, 18, 18)
        import_layout.setSpacing(12)

        import_title = QLabel("导入设备数据")
        import_title.setObjectName("SectionTitle")
        import_layout.addWidget(import_title)
        import_layout.addWidget(QLabel("支持按标准 CSV 模板批量导入设备。重复编号或缺失关键字段的记录会被自动跳过。"))

        import_actions = QHBoxLayout()
        self.import_button = QPushButton("选择 CSV 并导入")
        self.import_button.clicked.connect(self.import_devices)
        import_actions.addWidget(self.import_button)
        import_actions.addStretch()
        import_layout.addLayout(import_actions)
        root.addWidget(import_card)
        root.addStretch()

    def export_devices(self) -> None:
        self.export_button.setEnabled(False)
        self._set_result("正在生成设备 CSV...", "loading")
        try:
            file_bytes, filename = self.api_client.export_devices_csv()
            # 导出前由用户选择本地保存路径，避免强行写入固定目录。
            save_path, _ = QFileDialog.getSaveFileName(self, "保存设备导出文件", filename, "CSV Files (*.csv)")
            if not save_path:
                self._set_result("已取消导出。", "info")
                return

            target_path = Path(save_path)
            target_path.write_bytes(file_bytes)
            self._set_result(f"导出完成：{target_path}", "success")
            QMessageBox.information(self, "导出成功", f"设备数据已导出到：\n{target_path}")
        except ApiError as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            self._set_result(f"导出失败：{exc}", "error")
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            self._set_result(f"保存失败：{exc}", "error")
        finally:
            self.export_button.setEnabled(True)

    def download_template(self) -> None:
        # 模板直接使用系统导出表头，确保导入列名和后端解析完全一致。
        save_path, _ = QFileDialog.getSaveFileName(self, "保存导入模板", "devices_template.csv", "CSV Files (*.csv)")
        if not save_path:
            return

        self.template_button.setEnabled(False)
        self._set_result("正在生成导入模板...", "loading")
        try:
            # 模板使用和设备列表一致的中文表头，并保留 BOM 以兼容 Excel。
            template_content = "设备编号,设备名称,型号,厂商,位置,状态\n"
            target_path = Path(save_path)
            target_path.write_bytes(template_content.encode("utf-8-sig"))
            self._set_result(f"模板已生成：{target_path}", "success")
            QMessageBox.information(self, "模板已生成", f"导入模板已保存到：\n{target_path}")
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            self._set_result(f"模板保存失败：{exc}", "error")
        finally:
            self.template_button.setEnabled(True)

    def import_devices(self) -> None:
        # 导入前先选取本地 CSV，避免空文件请求和误操作。
        file_path, _ = QFileDialog.getOpenFileName(self, "选择要导入的 CSV", "", "CSV Files (*.csv)")
        if not file_path:
            return

        self.import_button.setEnabled(False)
        self._set_result(f"正在导入：{Path(file_path).name}", "loading")
        try:
            response = self.api_client.import_devices_csv(file_path)
            data = response.get("data") or {}
            success_count = int(data.get("success_count") or 0)
            skipped_count = int(data.get("skipped_count") or 0)
            # 结果中保留文件名，便于批量操作后快速确认处理对象。
            summary = f"{Path(file_path).name}：成功 {success_count} 条，跳过 {skipped_count} 条。"
            self._set_result(summary, "success")
            QMessageBox.information(self, "导入完成", summary)
        except ApiError as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            self._set_result(f"导入失败：{exc}", "error")
        finally:
            self.import_button.setEnabled(True)

    def _set_result(self, message: str, status: str) -> None:
        # 动态状态交给全局 QSS 着色，并立即刷新以显示同步操作进度。
        self.result_label.setText(message)
        self.result_label.setProperty("status", status)
        self.result_label.style().unpolish(self.result_label)
        self.result_label.style().polish(self.result_label)
        QApplication.processEvents()
