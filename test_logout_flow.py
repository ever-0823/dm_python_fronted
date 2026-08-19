from types import SimpleNamespace

import app.ui.windows.main_window as main_window_module


def main() -> None:
    calls: list[str] = []

    # 自检只验证退出流程，不打开真实消息弹窗。
    main_window_module.QMessageBox.information = staticmethod(lambda *_args, **_kwargs: None)

    fake_window = SimpleNamespace(
        auth_controller=SimpleNamespace(logout=lambda: calls.append("logout")),
        logout_completed=SimpleNamespace(emit=lambda: calls.append("emit")),
        close=lambda: calls.append("close"),
    )

    main_window_module.MainWindow.handle_logout(fake_window)
    assert calls == ["logout", "emit", "close"]


if __name__ == "__main__":
    main()
