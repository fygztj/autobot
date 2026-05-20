"""
autobot 全局配置
"""
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # --- 存储路径 ---
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    SCREENSHOT_DIR: str = os.path.join(DATA_DIR, "screenshots")
    TEMPLATE_DIR: str = os.path.join(DATA_DIR, "templates")
    TASK_DB: str = os.path.join(DATA_DIR, "tasks.json")

    # --- ADB / 设备 ---
    ADB_PATH: str = "adb"  # 系统 PATH 中有 adb 时用 "adb"，否则写完整路径
    ADB_CONNECT_TIMEOUT: int = 10
    DEVICE_SCAN_INTERVAL: int = 5  # 扫描新设备间隔（秒）

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
        "xiaohongshu": "com.xingin.xhs",
    })

    def ensure_dirs(self):
        """确保必要目录存在"""
        for d in [self.DATA_DIR, self.SCREENSHOT_DIR, self.TEMPLATE_DIR]:
            os.makedirs(d, exist_ok=True)


config = Config()