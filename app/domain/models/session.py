from dataclasses import dataclass


@dataclass
class SessionUser:
    username: str = ""
    role: str = ""
    created_at: str = ""

    @classmethod
    def from_dict(cls, data: dict | None) -> "SessionUser":
        source = data or {}
        return cls(
            username=str(source.get("username") or ""),
            role=str(source.get("role") or ""),
            created_at=str(source.get("created_at") or ""),
        )
