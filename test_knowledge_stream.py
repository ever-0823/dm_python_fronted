import io
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.infrastructure.http.api_client import ApiClient
from app.ui.pages.knowledge_page import KnowledgeSearchPage


def test_stream_knowledge_answer_keeps_chinese_chunks() -> None:
    """前端应逐段回调中文答案，并保留最终完整内容。"""
    events = (
        {"type": "metadata", "sources": [], "items": [{"score": 0.9}]},
        {"type": "delta", "content": "维护前"},
        {"type": "delta", "content": "切断电源。"},
        {"type": "done"},
    )
    response = io.BytesIO(
        b"\n".join(json.dumps(event, ensure_ascii=False).encode("utf-8") for event in events)
    )
    client = ApiClient(
        SimpleNamespace(api_base_url="http://127.0.0.1:8000/api"),
        SimpleNamespace(get_token=lambda: "test-token"),
    )
    chunks: list[str] = []

    # 使用内存字节流替代网络响应，让检查在未启动后端时也能直接运行。
    with patch("app.infrastructure.http.api_client.urlopen", return_value=response):
        result = client.stream_knowledge_answer("维护前做什么？", 3, chunks.append)

    assert chunks == ["维护前", "切断电源。"]
    assert result["data"]["answer"] == "维护前切断电源。"


def test_chat_page_streams_answer_and_sources() -> None:
    """聊天页应展示流式答案、引用来源，并能清空当前会话。"""
    app = QApplication.instance() or QApplication([])
    page = KnowledgeSearchPage(object())
    page._add_message("user", "维护前做什么？")
    page._active_answer_label, page._active_source_label = page._add_message("assistant", "")
    # 流解析已由上一个测试覆盖，这里只验证片段进入聊天气泡后的界面状态。
    page._append_answer_chunk("维护前")
    page._append_answer_chunk("切断电源。")
    page._search_succeeded(
        {
            "data": {
                "answer": "维护前切断电源。",
                "sources": [{"document": "设备规范.txt", "page": 2, "score": 0.91}],
                "items": [],
            }
        }
    )
    app.processEvents()

    assert len(page._message_rows) == 2
    assert page._active_answer_label.text() == "维护前切断电源。"
    assert "设备规范.txt" in page._active_source_label.text()
    page.new_conversation()
    assert page._message_rows == []


if __name__ == "__main__":
    test_stream_knowledge_answer_keeps_chinese_chunks()
    test_chat_page_streams_answer_and_sources()
