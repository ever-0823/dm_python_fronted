# PySide6 前端骨架

这是基于 `PySide6` 的桌面前端第一版骨架，已经包含：

- 登录窗口
- 企业风格主窗口
- 左侧菜单树
- 仪表盘页面
- 设备列表页面
- 基础接口封装
- 本地 token 存储

## 1. 安装依赖

建议先在项目根目录创建虚拟环境：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r frontend\requirements.txt
```

## 2. 启动后端

确保你的 FastAPI 服务先启动：

```powershell
cd server
python main.py
```

默认地址为 `http://127.0.0.1:8000`。

## 3. 启动前端

回到项目根目录执行：

```powershell
python frontend\main.py
```

## 4. 当前目录结构

```text
frontend/
  app/
    application/
      controllers/
    domain/
      models/
    infrastructure/
      http/
      storage/
    ui/
      pages/
      widgets/
      windows/
  main.py
```

## 5. 你现在可以重点看什么

如果你是第一次做 PySide6，建议按这个顺序看代码：

1. `frontend/main.py`
2. `frontend/app/bootstrap.py`
3. `frontend/app/ui/windows/login_window.py`
4. `frontend/app/ui/windows/main_window.py`
5. `frontend/app/ui/pages/dashboard_page.py`
6. `frontend/app/ui/pages/devices_page.py`
7. `frontend/app/infrastructure/http/api_client.py`

## 6. 当前阶段说明

这版骨架已经可以作为后续正式开发的起点。下一步我们可以继续做：

1. 接入真实登录联调
2. 完成新建设备弹窗
3. 完成编辑设备弹窗
4. 完成设备详情页
5. 完成附件上传下载
