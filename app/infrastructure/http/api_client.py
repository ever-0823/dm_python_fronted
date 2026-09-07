import json
import mimetypes
import re
from collections.abc import Callable
from pathlib import Path
from threading import Event, Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.infrastructure.config import AppSettings
from app.infrastructure.storage.token_store import TokenStore


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, settings: AppSettings, token_store: TokenStore) -> None:
        self.settings = settings
        self.token_store = token_store
        # 聊天页通过关闭当前响应中断流式读取，避免不安全地强制终止 QThread。
        self._knowledge_cancel_event = Event()
        self._knowledge_response = None
        self._knowledge_response_lock = Lock()

    def login(self, username: str, password: str) -> dict:
        payload = {
            "username": username,
            "password": password,
            "role": "user",
        }
        return self.request_json("POST", "/auth/login", payload)

    def logout(self) -> dict:
        return self.request_json("POST", "/auth/logout")

    def get_current_user(self) -> dict:
        return self.request_json("GET", "/auth/me")

    def update_profile(self, username: str) -> dict:
        # 编辑资料当前只支持用户名，接口保持最小请求体。
        return self.request_json("PUT", "/auth/profile", {"username": username})

    def change_password(self, current_password: str, new_password: str) -> dict:
        return self.request_json(
            "POST",
            "/auth/change-password",
            {
                "current_password": current_password,
                "new_password": new_password,
            },
        )

    def get_device_statistics(self) -> dict:
        return self.request_json("GET", "/devices/statistics")

    def get_devices(self, page: int = 1, page_size: int = 10, search: str = "", status: str = "") -> dict:
        params = urlencode(
            {
                "page": page,
                "page_size": page_size,
                "search": search,
                "status": status,
            }
        )
        return self.request_json("GET", f"/devices?{params}")

    def get_device_detail(self, device_id: str) -> dict:
        return self.request_json("GET", f"/devices/{device_id}")

    def get_device_logs(self, device_id: str) -> dict:
        return self.request_json("GET", f"/devices/{device_id}/logs")

    def create_device(self, payload: dict) -> dict:
        return self.request_json("POST", "/devices", payload)

    def update_device(self, device_id: str, payload: dict) -> dict:
        return self.request_json("PUT", f"/devices/{device_id}", payload)

    def delete_device(self, device_id: str) -> dict:
        return self.request_json("DELETE", f"/devices/{device_id}")

    def batch_delete_devices(self, device_ids: list[str]) -> dict:
        return self.request_json("POST", "/devices/batch-delete", {"device_ids": device_ids})

    def upload_device_attachment(self, device_id: str, file_path: str) -> dict:
        # 设备附件仍使用二进制类型，multipart 细节由 transport implementation 统一处理。
        return self._upload_file(
            f"/devices/{device_id}/upload",
            file_path,
            content_type="application/octet-stream",
        )

    def download_device_attachment(self, device_id: str) -> tuple[bytes, str]:
        # 下载接口返回文件流，界面层再决定保存到哪个本地路径。
        return self._request_bytes(f"/devices/{device_id}/download", f"{device_id}_attachment")

    def delete_device_attachment(self, device_id: str) -> dict:
        # 删除附件复用后端现有接口。
        return self.request_json("POST", f"/devices/{device_id}/delete")

    def export_devices_csv(self) -> tuple[bytes, str]:
        # 导出接口直接返回 CSV 文件流，界面层负责让用户选择保存位置。
        return self._request_bytes("/devices/export", "devices.csv")

    def import_devices_csv(self, file_path: str) -> dict:
        # CSV 导入也走 multipart/form-data，请求体里只携带一个上传文件。
        return self._upload_file("/devices/import", file_path, content_type="text/csv")

    def recognize_image(self, file_path: str) -> dict:
        # OCR 接口接收单张图片，超时时间放宽以覆盖首次模型加载。
        return self._upload_file("/ocr/ppocrv6", file_path, timeout=180)

    def upload_knowledge_document(self, file_path: str, qa_split: bool = False) -> dict:
        # 知识文档上传复用现有 multipart 请求写法，模型处理时间较长所以放宽超时。
        # 上传时间超过 30 分钟后超时，避免模型异常时请求永久等待。
        return self._upload_file(
            "/knowledge/upload",
            file_path,
            timeout=1800,
            form_fields={"qa_split": "true" if qa_split else "false"},
        )

    def preview_knowledge_document(self, file_path: str) -> dict:
        # 预览只提取和切分文档，不调用 Embedding、Ollama 或数据库。
        return self._upload_file("/knowledge/preview", file_path, timeout=180)

    def get_knowledge_documents(self) -> dict:
        # 文档列表接口返回已导入的文件和文本块数量。
        return self.request_json("GET", "/knowledge/documents")

    def get_knowledge_document_chunks(self, document_id: int, page: int = 1, page_size: int = 50) -> dict:
        # 数据集详情按页返回文本块，避免大文档一次加载导致界面卡顿。
        return self.request_json(
            "GET",
            f"/knowledge/documents/{document_id}/chunks?page={page}&page_size={page_size}",
        )

    def search_knowledge(self, query: str, top_k: int = 5) -> dict:
        # 首次加载 Qwen3 或 CPU 推理可能超过默认 10 秒，知识检索单独放宽超时。
        return self.request_json("POST", "/knowledge/search", {"query": query, "top_k": top_k}, timeout=180)

    def ask_knowledge(self, query: str, top_k: int = 5) -> dict:
        # Ollama 生成答案时间更长，使用独立长超时，不影响普通接口。
        return self.request_json("POST", "/knowledge/ask", {"query": query, "top_k": top_k}, timeout=300)

    def stream_knowledge_answer(
        self,
        query: str,
        top_k: int,
        on_chunk: Callable[[str], None],
    ) -> dict:
        """读取后端 NDJSON 流，并在每个答案片段到达时通知界面。"""
        request = self._build_request(
            "POST",
            "/knowledge/ask/stream",
            data=json.dumps({"query": query, "top_k": top_k}, ensure_ascii=False).encode("utf-8"),
            content_type="application/json",
        )
        data = {"answer": "", "sources": [], "items": []}
        completed = False
        self._knowledge_cancel_event.clear()
        try:
            with urlopen(request, timeout=300) as response:
                with self._knowledge_response_lock:
                    self._knowledge_response = response
                try:
                    for raw_line in response:
                        if self._knowledge_cancel_event.is_set():
                            return {"success": True, "cancelled": True, "data": data}
                        if not raw_line.strip():
                            continue
                        event = json.loads(raw_line.decode("utf-8"))
                        if event.get("type") == "metadata":
                            data["sources"] = event.get("sources") or []
                            data["items"] = event.get("items") or []
                        elif event.get("type") == "delta":
                            content = str(event.get("content") or "")
                            data["answer"] += content
                            if content:
                                on_chunk(content)
                        elif event.get("type") == "error":
                            # 流已建立后 HTTP 状态码无法改变，后端通过 error 事件传递真实原因。
                            raise ApiError(str(event.get("message") or "流式问答失败，请稍后重试"))
                        elif event.get("type") == "done":
                            completed = True
                finally:
                    with self._knowledge_response_lock:
                        self._knowledge_response = None
        except HTTPError as exc:
            message = self._decode_error(exc)
            raise ApiError(message) from exc
        except (URLError, OSError) as exc:
            if self._knowledge_cancel_event.is_set():
                return {"success": True, "cancelled": True, "data": data}
            raise ApiError("流式问答连接中断，请稍后重试") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            raise ApiError("流式问答返回的数据格式错误") from exc

        if self._knowledge_cancel_event.is_set():
            return {"success": True, "cancelled": True, "data": data}
        if not completed:
            raise ApiError("流式问答未正常结束，请稍后重试")
        return {"success": True, "message": "ok", "data": data}

    def cancel_knowledge_answer(self) -> None:
        """关闭当前知识库流，让工作线程从阻塞读取中安全返回。"""
        self._knowledge_cancel_event.set()
        with self._knowledge_response_lock:
            response = self._knowledge_response
        if response is not None:
            response.close()

    def delete_knowledge_document(self, document_id: int) -> dict:
        # 删除文档时后端通过外键级联删除对应文本块和向量。
        return self.request_json("DELETE", f"/knowledge/documents/{document_id}")

    def request_json(self, method: str, path: str, payload: dict | None = None, timeout: int = 10) -> dict:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = self._build_request(method, path, data=body, content_type="application/json")
        return self._request_json(request, timeout=timeout)

    def _request_json(self, request: Request, timeout: int = 10) -> dict:
        # 所有 JSON 接口统一走这里，保持鉴权和错误处理方式一致。
        content, _ = self._read_response(request, timeout)
        return self._decode_payload(content.decode("utf-8"))


    # 文件上传统
    def _upload_file(
        self,
        path: str,
        file_path: str,
        timeout: int = 10,
        content_type: str | None = None,
        form_fields: dict[str, str] | None = None,
    ) -> dict:
        """构造单文件 multipart 请求并返回标准 JSON 结果。"""
        source_path = Path(file_path)
        boundary = f"----PracticeUpload{uuid4().hex}"
        file_type = content_type or mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        # 清理文件名中的头部分隔字符，避免破坏 multipart 请求格式。
        safe_name = source_path.name.replace('"', "").replace("\r", "").replace("\n", "")
        # 先写入普通表单字段，再写入文件字段，兼容 FastAPI 的 Form 参数。
        form_body = b""
        for name, value in (form_fields or {}).items():
            form_body += (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        body = form_body + (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
            f"Content-Type: {file_type}\r\n\r\n"
        ).encode("utf-8") + source_path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
        request = self._build_request(
            "POST",
            path,
            data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        return self._request_json(request, timeout)

    def _request_bytes(self, path: str, fallback_filename: str, timeout: int = 10) -> tuple[bytes, str]:
        """读取文件响应，并统一解析下载文件名。"""
        request = self._build_request("GET", path)
        content, content_disposition = self._read_response(request, timeout)
        filename = self._extract_filename(content_disposition)
        return content, filename or fallback_filename

    def _build_request(
        self,
        method: str,
        path: str,
        data: bytes | None = None,
        content_type: str | None = None,
    ) -> Request:
        """统一拼接地址、认证头和内容类型。"""
        headers = self._build_auth_headers()
        if content_type:
            headers["Content-Type"] = content_type
        return Request(
            url=f"{self.settings.api_base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

    def _read_response(self, request: Request, timeout: int) -> tuple[bytes, str]:
        """统一读取非流式响应并映射 HTTP、连接错误。"""
        try:
            with urlopen(request, timeout=timeout) as response:
                content = response.read()
                content_disposition = response.headers.get("Content-Disposition", "")
                return content, content_disposition
        except HTTPError as exc:
            message = self._decode_error(exc)
            raise ApiError(message) from exc
        except URLError as exc:
            raise ApiError("无法连接后端服务，请确认 FastAPI 已启动") from exc

    def _build_auth_headers(self) -> dict[str, str]:
        # 需要登录态的请求统一补 Authorization 头，避免各接口重复拼接。
        token = self.token_store.get_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _decode_payload(self, content: str) -> dict:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ApiError("服务返回的不是合法 JSON 数据") from exc

        if data.get("success") is False:
            raise ApiError(str(data.get("message") or "接口调用失败"))

        return data

    def _decode_error(self, exc: HTTPError) -> str:
        try:
            content = exc.read().decode("utf-8")
            data = json.loads(content)
            if isinstance(data, dict):
                return str(data.get("message") or data.get("detail") or f"请求失败：{exc.code}")
        except Exception:
            pass
        return f"请求失败：{exc.code}"

    def _extract_filename(self, content_disposition: str) -> str:
        # 从响应头里解析下载文件名，解析不到时交给调用方使用默认名。
        match = re.search(r'filename="?([^";]+)"?', content_disposition)
        return match.group(1) if match else ""
