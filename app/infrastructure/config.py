from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AppSettings:
    app_name: str = "设备管理控制台"
    api_base_url: str = "http://127.0.0.1:8000/api"
    session_file: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2] / ".session.json")
