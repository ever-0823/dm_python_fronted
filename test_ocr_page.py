import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.pages.ocr_page import OcrPage


def test_ocr_result_rendering() -> None:
    # 使用模拟结果验证全文、逐行置信度和复制按钮状态，不调用真实后端。
    app = QApplication.instance() or QApplication([])
    page = OcrPage(None)
    page._show_result(
        {
            "data": {
                "text": "设备编号：DEV-001",
                "lines": [{"text": "设备编号：DEV-001", "score": 0.982}],
            }
        }
    )

    assert page.text_result.toPlainText() == "设备编号：DEV-001"
    assert page.lines_table.rowCount() == 1
    assert page.lines_table.item(0, 1).text() == "98.2%"
    assert page.copy_button.isEnabled()


if __name__ == "__main__":
    test_ocr_result_rendering()
