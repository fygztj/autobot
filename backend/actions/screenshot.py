"""
屏幕截图模块
"""
import os
import time
from typing import Optional
from PIL import Image
from loguru import logger

from backend.config import config
from backend.adb_client import ADBClient


class Screenshot:
    """设备截图管理器"""

    def __init__(self, adb: ADBClient):
        self.adb = adb
        self._current_image: Optional[Image.Image] = None
        self._current_path: str = ""

    def capture(self) -> Optional[Image.Image]:
        """抓取当前屏幕截图并返回 PIL Image"""
        timestamp = int(time.time() * 1000)
        filename = f"{self.adb.serial}_{timestamp}.png"
        path = os.path.join(config.SCREENSHOT_DIR, filename)

        ok = self.adb.screenshot(path)
        if not ok:
            logger.error(f"[{self.adb.serial}] 截图失败")
            return None

        self._current_path = path
        self._current_image = Image.open(path)
        return self._current_image

    @property
    def image(self) -> Optional[Image.Image]:
        return self._current_image

    @property
    def path(self) -> str:
        return self._current_path

    def get_size(self) -> tuple:
        """获取截图尺寸 (width, height)"""
        if self._current_image:
            return self._current_image.size
        return (0, 0)