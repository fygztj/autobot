"""
UI 元素查找器 - 结合 OCR 和图像匹配的复合查找
"""
import time
from typing import Optional, Tuple, List
from PIL import Image
from loguru import logger

from backend.config import config
from backend.adb_client import ADBClient
from backend.vision.ocr import ocr_engine, OCRResult
from backend.vision.image_match import image_matcher
from backend.actions.screenshot import Screenshot


class ElementFinder:
    """
    统一的 UI 元素查找器
    先尝试 OCR 识别文字点击，再尝试图像匹配
    """

    def __init__(self, adb: ADBClient):
        self.adb = adb
        self.screenshot = Screenshot(adb)

    # ================== 文字查找 ==================

    def find_text(self, keyword: str, timeout: int = None) -> Optional[OCRResult]:
        """在当前屏幕上查找文字，返回第一个匹配"""
        timeout = timeout or config.DEFAULT_WAIT_TIMEOUT
        start = time.time()

        while time.time() - start < timeout:
            img = self.screenshot.capture()
            if img is None:
                time.sleep(config.RETRY_INTERVAL)
                continue

            results = ocr_engine.find_text(img, keyword)
            if results:
                # 按置信度排序，返回最高的
                results.sort(key=lambda r: r.confidence, reverse=True)
                return results[0]

            time.sleep(config.RETRY_INTERVAL)
        return None

    def find_all_text(self, keyword: str) -> List[OCRResult]:
        """查找所有匹配的文字"""
        img = self.screenshot.capture()
        if img is None:
            return []
        return ocr_engine.find_text(img, keyword)

    def wait_text(self, keyword: str, timeout: int = None) -> Optional[OCRResult]:
        """等待文字出现（同 find_text）"""
        return self.find_text(keyword, timeout)

    # ================== 图像查找 ==================

    def find_image(self, template_path: str, timeout: int = None) -> Optional[Tuple[int, int, float]]:
        """在当前屏幕上查找模板图片位置"""
        timeout = timeout or config.DEFAULT_WAIT_TIMEOUT
        return image_matcher.wait_for_template(
            self.adb, template_path, timeout=timeout
        )

    # ================== 复合点击方法 ==================

    def click_text(self, keyword: str, timeout: int = None) -> bool:
        """查找文字并点击"""
        result = self.find_text(keyword, timeout)
        if result:
            cx, cy = result.center
            logger.info(f"点击文字 '{result.text}' @ ({cx}, {cy})")
            self.adb.human_tap(cx, cy)
            return True
        logger.warning(f"未找到文字: {keyword}")
        return False

    def click_image(self, template_path: str, timeout: int = None) -> bool:
        """查找图片并点击"""
        result = self.find_image(template_path, timeout)
        if result:
            cx, cy, conf = result
            logger.info(f"点击图片 {template_path} @ ({cx}, {cy}), conf={conf:.2f}")
            self.adb.human_tap(cx, cy)
            return True
        logger.warning(f"未找到图片: {template_path}")
        return False

    def wait_and_click_text(self, keyword: str, timeout: int = None) -> bool:
        """等待文字出现后点击"""
        return self.click_text(keyword, timeout)

    def wait_and_click_image(self, template_path: str, timeout: int = None) -> bool:
        """等待图片出现后点击"""
        return self.click_image(template_path, timeout)

    def has_text(self, keyword: str) -> bool:
        """判断屏幕上是否出现指定文字"""
        img = self.screenshot.capture()
        if img is None:
            return False
        results = ocr_engine.find_text(img, keyword)
        return len(results) > 0

    def get_all_texts(self) -> List[str]:
        """获取屏幕上所有文字"""
        img = self.screenshot.capture()
        if img is None:
            return []
        results = ocr_engine.recognize(img)
        return [r.text for r in results]

    # ================== 滚动查找 ==================

    def scroll_until_find_text(self, keyword: str,
                                direction: str = "up",
                                max_scrolls: int = 10,
                                timeout: int = None) -> Optional[OCRResult]:
        """滚动直到找到指定文字"""
        timeout = timeout or config.DEFAULT_WAIT_TIMEOUT
        start = time.time()
        screen_w, screen_h = self.adb.get_screen_size()

        scrolls = 0
        while scrolls < max_scrolls and time.time() - start < timeout:
            # 先查找
            result = self.find_text(keyword, timeout=1)
            if result:
                return result

            # 滚动
            mid_x = screen_w // 2
            if direction == "up":
                self.adb.human_swipe(mid_x, screen_h * 3 // 4, mid_x, screen_h // 4)
            elif direction == "down":
                self.adb.human_swipe(mid_x, screen_h // 4, mid_x, screen_h * 3 // 4)
            scrolls += 1
            time.sleep(0.5)

        return None