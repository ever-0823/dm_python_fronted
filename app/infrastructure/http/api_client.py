import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.infrastructure.config import AppSettings
from app.infrastructure.storage.token_store import TokenStore


class ApiError(Exception):
    pass


class ApiClient:
    def __init__(self, settings: AppSettings, token_store: TokenStore) -> None:
        self.settings = settings
        self.token_store = token_store

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
        # 上传附件时手动构造 multipart/form-data，请求体里包含文件名和二进制内容。
        boundary = "----CodexDeviceUploadBoundary"
        source_path = Path(file_path)
        file_bytes = source_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{source_path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        request = Request(
            url=f"{self.settings.api_base_url}/devices/{device_id}/upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **self._build_auth_headers(),
            },
            method="POST",
        )
        return self._request_json(request)

    def download_device_attachment(self, device_id: str) -> tuple[bytes, str]:
        # 下载接口返回文件流，界面层再决定保存到哪个本地路径。
        request = Request(
            url=f"{self.settings.api_base_url}/devices/{device_id}/download",
            headers=self._build_auth_headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read()
                filename = self._extract_filename(response.headers.get("Content-Disposition", ""))
                return content, filename or f"{device_id}_attachment"
        except HTTPError as exc:
            message = self._decode_error(exc)
            raise ApiError(message) from exc
        except URLError as exc:
            raise ApiError("无法连接后端服务，请确认 FastAPI 已启动") from exc

    def delete_device_attachment(self, device_id: str) -> dict:
        # 删除附件复用后端现有接口。
        return self.request_json("POST", f"/devices/{device_id}/delete")

    def export_devices_csv(self) -> tuple[bytes, str]:
        # 导出接口直接返回 CSV 文件流，界面层负责让用户选择保存位置。
        request = Request(
            url=f"{self.settings.api_base_url}/devices/export",
            headers=self._build_auth_headers(),
            method="GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read()
                filename = self._extract_filename(response.headers.get("Content-Disposition", ""))
                return content, filename or "devices.csv"
        except HTTPError as exc:
            message = self._decode_error(exc)
            raise ApiError(message) from exc
        except URLError as exc:
            raise ApiError("无法连接后端服务，请确认 FastAPI 已启动") from exc

    def import_devices_csv(self, file_path: str) -> dict:
        # CSV 导入也走 multipart/form-data，请求体里只携带一个上传文件。
        boundary = "----CodexDeviceImportBoundary"
        source_path = Path(file_path)
        file_bytes = source_path.read_bytes()
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{source_path.name}"\r\n'
            "Content-Type: text/csv\r\n\r\n"
        ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        request = Request(
            url=f"{self.settings.api_base_url}/devices/import",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **self._build_auth_headers(),
            },
            method="POST",
        )
        return self._request_json(request)

    def request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.settings.api_base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            **self._build_auth_headers(),
        }

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(url=url, data=body, headers=headers, method=method)
        return self._request_json(request)

    def _request_json(self, request: Request) -> dict:
        # 所有 JSON 接口统一走这里，保持鉴权和错误处理方式一致。
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read().decode("utf-8")
                return self._decode_payload(content)
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
