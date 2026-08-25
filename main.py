import os
import sys

from app.bootstrap import bootstrap


def configure_utf8_console() -> None:
    """让 Python 输出编码与 Windows UTF-8 控制台保持一致。"""
    # 环境变量供当前进程创建的子进程继承，reconfigure 立即修正当前标准流。
    os.environ["PYTHONIOENCODING"] = "utf-8"
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    configure_utf8_console()
    bootstrap()
