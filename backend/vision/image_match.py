"""
图像匹配模块 - 基于 OpenCV 模板匹配
"""
import os
from typing import Tuple, Optional, List
import cv2
import numpy as np
from PIL import Image
from loguru import logger

from backend.config import config


class ImageMatcher:
    """图像模板匹配器"""

    def __init__(self):
        self.template_cache: dict = {}

    def _load_image(self, path: str) -> np.ndarray:
        """加载图片为 OpenCV 格式"""
        if isinstance(path, np.ndarray):
            return path
        if isinstance(path, Image.Image):
            return cv2.cvtColor(np.array(path), cv2.COLOR_RGB2BGR)
        if path in self.template_cache:
            return self.template_cache[path]
        img = cv2.imread(path)
        if img is not None:
            self.template_cache[path] = img
        return img

    def match_template(self,
                       screen: np.ndarray,
                       template: np.ndarray,
                       threshold: float = None) -> Optional[Tuple[int, int, float]]:
        """
        在屏幕截图中查找模板图片位置
        返回: (center_x, center_y, confidence) 或 None
        """
        if threshold is None:
            threshold = config.IMAGE_MATCH_THRESHOLD

        screen_img = self._load_image(screen)
        template_img = self._load_image(template)

        if screen_img is None or template_img is None:
            logger.error("图片加载失败")
            return None

        th, tw = template_img.shape[:2]
        sh, sw = screen_img.shape[:2]

        if tw > sw or th > sh:
            logger.warning("模板图片大于屏幕截图")
            return None

        # 多尺度匹配以提高准确性
        scales = [0.9, 0.95, 1.0, 1.05, 1.1]
        best_match = None
        best_val = 0

        for scale in scales:
            resized = cv2.resize(template_img, None, fx=scale, fy=scale)
            rh, rw = resized.shape[:2]
            if rw > sw or rh > sh:
                continue

            result = cv2.matchTemplate(screen_img, resized, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val = max_val
                best_match = (max_loc[0] + rw // 2, max_loc[1] + rh // 2, max_val)

        if best_match and best_match[2] >= threshold:
            return best_match
        return None

    def match_template_file(self,
                            screen: np.ndarray,
                            template_path: str,
                            threshold: float = None) -> Optional[Tuple[int, int, float]]:
        """通过模板文件路径进行匹配"""
        template = self._load_image(template_path)
        if template is None:
            logger.error(f"模板文件加载失败: {template_path}")
            return None
        return self.match_template(screen, template, threshold)

    def find_all_matches(self,
                         screen: np.ndarray,
                         template: np.ndarray,
                         threshold: float = None) -> List[Tuple[int, int, float]]:
        """查找所有匹配位置"""
        if threshold is None:
            threshold = config.IMAGE_MATCH_THRESHOLD

        screen_img = self._load_image(screen)
        template_img = self._load_image(template)

        if screen_img is None or template_img is None:
            return []

        th, tw = template_img.shape[:2]

        result = cv2.matchTemplate(screen_img, template_img, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        matches = []
        for y, x in zip(*locations):
            matches.append((x + tw // 2, y + th // 2, result[y, x]))
        return matches

    def wait_for_template(self,
                          adb_client,
                          template_path: str,
                          timeout: int = None,
                          threshold: float = None,
                          interval: float = None) -> Optional[Tuple[int, int, float]]:
        """
        等待模板图片出现在屏幕上
        """
        import time
        if timeout is None:
            timeout = config.DEFAULT_WAIT_TIMEOUT
        if interval is None:
            interval = config.RETRY_INTERVAL

        start = time.time()
        while time.time() - start < timeout:
            from backend.actions.screenshot import Screenshot
            ss = Screenshot(adb_client)
            screen = ss.capture()
            if screen is not None:
                result = self.match_template_file(
                    np.array(screen), template_path, threshold
                )
                if result:
                    return result
            time.sleep(interval)
        return None


# 全局单例
image_matcher = ImageMatcher()