import json
from pathlib import Path


class TokenStore:
    def __init__(self, session_file: Path) -> None:
        self.session_file = session_file

    def get_token(self) -> str:
        if not self.session_file.exists():
            return ""
        try:
            content = json.loads(self.session_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return ""
        return str(content.get("access_token") or "")

    def set_token(self, token: str) -> None:
        self.session_file.write_text(
            json.dumps({"access_token": token}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.session_file.exists():
            self.session_file.unlink()
