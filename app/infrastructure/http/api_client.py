import json
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

    def request_json(self, method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{self.settings.api_base_url}{path}"
        headers = {"Content-Type": "application/json"}

        token = self.token_store.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(url=url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read().decode("utf-8")
                return self._decode_payload(content)
        except HTTPError as exc:
            message = self._decode_error(exc)
            raise ApiError(message) from exc
        except URLError as exc:
            raise ApiError("无法连接后端服务，请确认 FastAPI 已启动") from exc

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
