import io
import json
import tempfile
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import patch

from app.infrastructure.http.api_client import ApiClient, ApiError


class FakeResponse(io.BytesIO):
    """为 urllib 测试补充响应头。"""

    def __init__(self, content: bytes, content_disposition: str = "") -> None:
        super().__init__(content)
        self.headers = {"Content-Disposition": content_disposition}


class BlockingStreamResponse:
    """模拟收到元数据后持续等待的流，用于验证用户主动中断。"""

    def __init__(self) -> None:
        self.reading = Event()
        self.closed = Event()

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def __iter__(self):
        yield b'{"type":"metadata","sources":[],"items":[]}\n'
        self.reading.set()
        self.closed.wait(2)

    def close(self) -> None:
        self.closed.set()


def test_transport_reuses_upload_and_download_paths() -> None:
    """共享 transport implementation 应保留认证、文件内容和文件名。"""
    client = ApiClient(
        SimpleNamespace(api_base_url="http://127.0.0.1:8000/api"),
        SimpleNamespace(get_token=lambda: "test-token"),
    )

    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "知识文档.txt"
        source.write_bytes("维护前切断电源。".encode("utf-8"))
        response = FakeResponse(json.dumps({"success": True, "data": {"id": 1}}).encode("utf-8"))

        # 上传检查不访问后端，只检查最终交给 urllib 的请求。
        with patch("app.infrastructure.http.api_client.urlopen", return_value=response) as mocked_open:
            result = client.upload_knowledge_document(str(source), qa_split=True)

        request = mocked_open.call_args.args[0]
        assert result["data"]["id"] == 1
        assert request.full_url.endswith("/knowledge/upload")
        assert request.get_header("Authorization") == "Bearer test-token"
        assert request.get_header("Content-type").startswith("multipart/form-data; boundary=")
        assert source.read_bytes() in request.data
        assert b'name="qa_split"' in request.data
        assert b"true" in request.data
        assert mocked_open.call_args.kwargs["timeout"] == 1800

        preview_response = FakeResponse(
            json.dumps({"success": True, "data": {"chunk_count": 1}}).encode("utf-8")
        )
        with patch("app.infrastructure.http.api_client.urlopen", return_value=preview_response) as mocked_open:
            preview = client.preview_knowledge_document(str(source))

        assert preview["data"]["chunk_count"] == 1
        assert mocked_open.call_args.args[0].full_url.endswith("/knowledge/preview")
        assert mocked_open.call_args.kwargs["timeout"] == 180

    download = FakeResponse(b"csv-data", 'attachment; filename="devices.csv"')
    with patch("app.infrastructure.http.api_client.urlopen", return_value=download):
        content, filename = client.export_devices_csv()

    assert content == b"csv-data"
    assert filename == "devices.csv"


def test_stream_knowledge_answer_uses_backend_error_event() -> None:
    """流已建立后的后端错误应保留具体原因，不再显示笼统的连接中断。"""
    events = (
        {"type": "metadata", "sources": [], "items": []},
        {"type": "error", "message": "Ollama 未返回有效答案"},
    )
    response = io.BytesIO(
        b"\n".join(json.dumps(event, ensure_ascii=False).encode("utf-8") for event in events)
    )
    client = ApiClient(
        SimpleNamespace(api_base_url="http://127.0.0.1:8000/api"),
        SimpleNamespace(get_token=lambda: "test-token"),
    )

    with patch("app.infrastructure.http.api_client.urlopen", return_value=response):
        try:
            client.stream_knowledge_answer("员工上班时间", 5, lambda _content: None)
        except ApiError as exc:
            assert str(exc) == "Ollama 未返回有效答案"
        else:
            raise AssertionError("error 事件必须转换为 ApiError")


def test_stream_knowledge_answer_can_be_cancelled() -> None:
    """关闭活动响应后，流式请求应快速返回并标记为用户取消。"""
    response = BlockingStreamResponse()
    client = ApiClient(
        SimpleNamespace(api_base_url="http://127.0.0.1:8000/api"),
        SimpleNamespace(get_token=lambda: "test-token"),
    )
    results = []

    # 使用真实线程复现聊天页调用方式，避免只验证同步分支。
    with patch("app.infrastructure.http.api_client.urlopen", return_value=response):
        thread = Thread(
            target=lambda: results.append(
                client.stream_knowledge_answer("员工上班时间", 5, lambda _content: None)
            )
        )
        thread.start()
        assert response.reading.wait(1)
        client.cancel_knowledge_answer()
        thread.join(1)

    assert not thread.is_alive()
    assert response.closed.is_set()
    assert results[0]["cancelled"] is True


if __name__ == "__main__":
    test_transport_reuses_upload_and_download_paths()
    test_stream_knowledge_answer_uses_backend_error_event()
    test_stream_knowledge_answer_can_be_cancelled()
    print("ok")
