"""
autobot - 移动端自动化机器人

用法:
    python -m backend.main          # 启动完整服务
    python backend/main.py          # 同上

前置条件:
    1. 安装 ADB 并确保 `adb devices` 可以看到设备
    2. 安装 Python 依赖: pip install -r requirements.txt
    3. 手机开启 USB 调试模式并授权

功能:
    - Web 管理面板: http://localhost:8550
    - REST API: http://localhost:8550/api/
    - 支持多设备同时操作
    - 支持定时任务调度
    - OCR 文字识别 + 图像模板匹配
    - 微信/抖音/小红书自动化操作
"""