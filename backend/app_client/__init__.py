"""
iOS 助手 App 客户端管理
通过 WebSocket 接收 PC 端指令，控制 App 执行自动化操作
"""

from backend.app_client.manager import AppDeviceManager
from backend.app_client.models import AppCommand, AppCommandResult, AppDeviceInfo

app_device_manager = AppDeviceManager()

__all__ = [
    "app_device_manager",
    "AppCommand",
    "AppCommandResult",
    "AppDeviceInfo",
]
