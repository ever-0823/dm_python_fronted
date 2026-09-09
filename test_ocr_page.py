import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QColor, QPixmap
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
    assert page.knowledge_button.isEnabled()
    assert page.text_result.isReadOnly() is False
    assert page.knowledge_name_input.maxLength() == 255


def test_multi_image_result_keeps_each_task_separate() -> None:
    """批量识别结果必须写回当前图片，不能覆盖其他图片。"""
    app = QApplication.instance() or QApplication([])
    page = OcrPage(None)
    page.tasks = [
        {"path": "a.png", "name": "a.png", "size": 1, "status": "识别中", "text": "", "lines": [], "error": ""},
        {"path": "b.png", "name": "b.png", "size": 1, "status": "等待识别", "text": "", "lines": [], "error": ""},
    ]
    page._active_task_index = 0
    page._show_result({"data": {"text": "第一张图片", "lines": [{"text": "第一张图片", "score": 0.9}]}})

    assert page.tasks[0]["text"] == "第一张图片"
    assert page.tasks[0]["status"] == "已识别"
    assert page.tasks[1]["text"] == ""


def test_table_json_renders_markdown_preview() -> None:
    """嵌套字段 JSON 应实时渲染标题、分组和报价子项。"""
    app = QApplication.instance() or QApplication([])
    page = OcrPage(None)
    data = {
        "document_title": "合同审批表",
        "sections": [{
            "name": "价格审批",
            "fields": [{
                "name": "对方报价",
                "value": {"订书器": "395620元", "合计": "921920元"},
                "confidence": 0.88,
                "status": "待确认",
            }],
        }],
    }

    page.table_json_result.setPlainText(json.dumps(data, ensure_ascii=False))

    markdown = page._table_to_markdown(data)
    assert "# 合同审批表" in markdown
    assert "## 价格审批" in markdown
    assert "订书器：395620元" in markdown
    assert "88.0%" in markdown
    assert "合同审批表" in page.markdown_preview.toPlainText()

    data["sections"][0]["fields"][0]["confidence"] = "待核对"
    page.table_json_result.setPlainText(json.dumps(data, ensure_ascii=False))
    assert "待核对" in page.markdown_preview.toPlainText()


def test_multi_image_queue_creates_then_appends_same_knowledge() -> None:
    """首张图片创建知识库后，后续图片必须复用返回的 document_id。"""
    app = QApplication.instance() or QApplication([])
    upload_targets: list[int | None] = []

    class FakeApiClient:
        def recognize_image(self, file_path: str) -> dict:
            name = Path(file_path).stem
            return {"data": {"text": name, "lines": [{"text": name, "score": 0.9}]}}

        def upload_knowledge_image(self, _file_path, _knowledge_name, _text, _lines, document_id=None) -> dict:
            upload_targets.append(document_id)
            return {"data": {"id": 42, "duplicate": False, "chunk_count": len(upload_targets)}}

    def wait_until_idle(page: OcrPage) -> None:
        # 用事件循环等待真实 QThread 队列结束，避免测试依赖固定休眠时间。
        loop = QEventLoop()

        def check() -> None:
            if page._thread is None and not page._operation_mode:
                loop.quit()
            else:
                QTimer.singleShot(10, check)

        QTimer.singleShot(10, check)
        QTimer.singleShot(3000, loop.quit)
        loop.exec()

    with tempfile.TemporaryDirectory() as directory:
        paths = []
        for index in range(2):
            path = Path(directory) / f"image-{index + 1}.png"
            pixmap = QPixmap(20, 20)
            pixmap.fill(QColor("white"))
            assert pixmap.save(str(path))
            paths.append(str(path))

        page = OcrPage(FakeApiClient())
        page._add_files(paths)
        page.recognize()
        wait_until_idle(page)
        page.save_to_knowledge()
        wait_until_idle(page)

    assert [task["status"] for task in page.tasks] == ["已保存", "已保存"]
    assert upload_targets == [None, 42]


if __name__ == "__main__":
    test_ocr_result_rendering()
    test_multi_image_result_keeps_each_task_separate()
    test_table_json_renders_markdown_preview()
    test_multi_image_queue_creates_then_appends_same_knowledge()
