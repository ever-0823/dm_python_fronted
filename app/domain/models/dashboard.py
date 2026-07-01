from dataclasses import dataclass


@dataclass
class DeviceStats:
    total: int = 0
    active: int = 0
    maintenance: int = 0
    inactive: int = 0
    retired: int = 0

    @classmethod
    def from_dict(cls, data: dict | None) -> "DeviceStats":
        source = data or {}
        return cls(
            total=int(source.get("total") or 0),
            active=int(source.get("active") or 0),
            maintenance=int(source.get("maintenance") or 0),
            inactive=int(source.get("inactive") or 0),
            retired=int(source.get("retired") or 0),
        )
