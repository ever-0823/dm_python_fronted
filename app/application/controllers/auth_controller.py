from app.domain.models.session import SessionUser
from app.infrastructure.http.api_client import ApiClient, ApiError
from app.infrastructure.storage.token_store import TokenStore


class AuthController:
    def __init__(self, api_client: ApiClient, token_store: TokenStore) -> None:
        self.api_client = api_client
        self.token_store = token_store

    def login(self, username: str, password: str) -> SessionUser:
        response = self.api_client.login(username, password)
        data = response.get("data") or {}
        access_token = data.get("access_token")
        user = data.get("user") or {}

        if not access_token:
            raise ApiError("登录成功但没有拿到 access_token")

        self.token_store.set_token(access_token)
        return SessionUser.from_dict(user)

    def logout(self) -> None:
        try:
            self.api_client.logout()
        finally:
            self.token_store.clear()
