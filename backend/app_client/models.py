"""
App 客户端数据模型
"""
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class AppDeviceInfo:
    """App 设备信息"""
    device_id: str          # 设备唯一标识（IDFV）
    device_name: str        # 设备名称（如：iPhone 15 Pro）
    system_version: str     # iOS 版本
    app_version: str        # App 版本
    model: str              # 设备型号
    screen_width: int = 0
    screen_height: int = 0
    status: str = "idle"    # idle | running | paused | error
    current_platform: str = ""  # 当前打开的平台 xiaohongshu | douyin | ...
    connected_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)


@dataclass
class AppCommand:
    """下发给 App 的指令"""
    command_id: str
    action: str             # like | comment | follow | message | scroll | open_platform | custom_js
    platform: str           # xiaohongshu | douyin | weibo | ...
    params: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "type": "command",
            "command_id": self.command_id,
            "action": self.action,
            "platform": self.platform,
            "params": self.params,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class AppCommandResult:
    """App 指令执行结果"""
    command_id: str
    success: bool
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, d: dict) -> "AppCommandResult":
        return cls(
            command_id=d.get("command_id", ""),
            success=d.get("success", False),
            message=d.get("message", ""),
            data=d.get("data", {})
        )
