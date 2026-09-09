import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication

from app.ui.pages.knowledge_page import KnowledgeDatasetPage


def test_worker_success_callback_runs_on_ui_thread() -> None:
    """后台请求完成后，界面回调必须切回 Qt 主线程执行。"""
    app = QApplication.instance() or QApplication([])
    page = KnowledgeDatasetPage(object())
    loop = QEventLoop()
    callback_on_ui_thread: list[bool] = []

    # 使用普通函数模拟删除接口，覆盖曾导致表格跨线程刷新的回调形式。
    page._after_thread_finished = loop.quit
    page._start_worker(
        lambda: {"success": True},
        on_success=lambda _response: callback_on_ui_thread.append(
            QThread.currentThread() is app.thread()
        ),
    )
    QTimer.singleShot(2000, loop.quit)
    loop.exec()

    assert callback_on_ui_thread == [True]
    assert page._thread is None
