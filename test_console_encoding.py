from types import SimpleNamespace
from unittest.mock import patch

import main


def test_configure_utf8_console() -> None:
    """启动入口应同时修正当前标准流，并配置子进程输出编码。"""
    encodings: list[str] = []
    stream = SimpleNamespace(reconfigure=lambda **options: encodings.append(options["encoding"]))
    # 标准库 patch 可让没有安装 pytest 的前端 Conda 环境直接运行本检查。
    with patch.object(main.sys, "stdout", stream), patch.object(main.sys, "stderr", stream):
        main.configure_utf8_console()

    assert encodings == ["utf-8", "utf-8"]
    assert main.os.environ["PYTHONIOENCODING"] == "utf-8"


if __name__ == "__main__":
    test_configure_utf8_console()
