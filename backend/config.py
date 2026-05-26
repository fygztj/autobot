"""
autobot 全局配置
"""
import os
import platform
from dataclasses import dataclass, field
from typing import List


def get_app_data_dir():
    """获取跨平台的应用数据目录（使用项目目录下的 data 目录，避免权限问题）"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "data", "app_data")


@dataclass
class Config:
    # --- 存储路径 ---
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    APP_DATA_DIR: str = get_app_data_dir()
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    SCREENSHOT_DIR: str = os.path.join(DATA_DIR, "screenshots")
    TEMPLATE_DIR: str = os.path.join(DATA_DIR, "templates")
    TASK_DB: str = os.path.join(BASE_DIR, "data", "tasks.json")
    # 跨平台临时目录（用于存储 tidevice SSL 证书等）
    TIDEVICE_DIR: str = os.path.join(APP_DATA_DIR, "tidevice")

    # --- ADB / 设备 ---
    ADB_PATH: str = ""  # 空字符串表示自动查找
    ADB_CONNECT_TIMEOUT: int = 10
    DEVICE_SCAN_INTERVAL: int = 15  # 扫描新设备间隔（秒），增加到15秒减少卡顿
    DEVICE_INFO_REFRESH_INTERVAL: int = 60  # 设备信息刷新间隔（秒）
    ENABLE_IOS_SCAN: bool = True  # 是否启用 iOS 设备扫描

    # --- 视觉识别 ---
    OCR_LANG: str = "ch"  # PaddleOCR 语言
    IMAGE_MATCH_THRESHOLD: float = 0.85  # 模板匹配阈值
    DEFAULT_WAIT_TIMEOUT: int = 10  # 等待元素出现的默认超时（秒）
    RETRY_INTERVAL: float = 0.5  # 重试间隔（秒）

    # --- 操作延迟（模拟人类） ---
    CLICK_MIN_DELAY: float = 0.05
    CLICK_MAX_DELAY: float = 0.15
    SWIPE_DURATION_MIN: float = 0.2
    SWIPE_DURATION_MAX: float = 0.6
    TYPING_INTERVAL: float = 0.08  # 每个字符输入间隔

    # --- 任务调度 ---
    MAX_CONCURRENT_TASKS: int = 10
    TASK_RETRY_COUNT: int = 2
    TASK_RETRY_DELAY: int = 3

    # --- Web 服务 ---
    WEB_HOST: str = "0.0.0.0"
    WEB_PORT: int = 8550

    # --- 应用包名 ---
    APP_PACKAGES: dict = field(default_factory=lambda: {
        "wechat": "com.tencent.mm",
        "douyin": "com.ss.android.ugc.aweme",
        "xiaohongshu": "com.xingin.discover",
    })

    def ensure_dirs(self):
        """确保必要目录存在"""
        for d in [self.DATA_DIR, self.SCREENSHOT_DIR, self.TEMPLATE_DIR, self.APP_DATA_DIR, self.TIDEVICE_DIR]:
            os.makedirs(d, exist_ok=True)


config = Config()