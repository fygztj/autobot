"""
OCR 文字识别模块 - 基于 PaddleOCR
"""
from typing import List, Tuple, Optional
from loguru import logger
import numpy as np
from PIL import Image

from backend.config import config

# 延迟加载 PaddleOCR（首次使用时初始化）
_ocr = None


def _get_ocr():
    global _ocr
    if _ocr is None:
        try:
            from paddleocr import PaddleOCR
            _ocr = PaddleOCR(lang=config.OCR_LANG, use_angle_cls=True)
            logger.info("PaddleOCR 初始化成功")
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise
    return _ocr


class OCRResult:
    """单个 OCR 识别结果"""

    def __init__(self, text: str, confidence: float,
                 bbox: List[Tuple[int, int]],
                 center: Tuple[int, int]):
        self.text = text
        self.confidence = confidence
        self.bbox = bbox  # 四个角点坐标
        self.center = center  # 中心点坐标

    def __repr__(self):
        return f"OCRResult(text={self.text!r}, conf={self.confidence:.2f}, center={self.center})"


class OCREngine:
    """OCR 识别引擎"""

    def __init__(self):
        self.ocr = None

    def initialize(self):
        self.ocr = _get_ocr()

    def recognize(self, image: Image.Image) -> List[OCRResult]:
        """识别图片中的所有文字，返回 OCRResult 列表"""
        if self.ocr is None:
            self.initialize()

        # 转为 numpy array
        img_array = np.array(image)

        try:
            results = self.ocr.ocr(img_array, cls=True)
        except Exception as e:
            logger.error(f"OCR 识别出错: {e}")
            return []

        ocr_results = []
        if results and results[0]:
            for item in results[0]:
                bbox, (text, confidence) = item
                # bbox 是四个点 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                points = [(int(p[0]), int(p[1])) for p in bbox]
                # 计算中心点
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                center = (sum(xs) // 4, sum(ys) // 4)
                ocr_results.append(OCRResult(text, confidence, points, center))

        return ocr_results

    def find_text(self, image: Image.Image, keyword: str) -> List[OCRResult]:
        """在图片中查找包含指定关键词的文字区域"""
        results = self.recognize(image)
        return [r for r in results if keyword in r.text]

    def find_text_exact(self, image: Image.Image, keyword: str) -> List[OCRResult]:
        """精确匹配"""
        results = self.recognize(image)
        return [r for r in results if r.text == keyword]

    def get_text_at_point(self, image: Image.Image,
                           x: int, y: int) -> Optional[OCRResult]:
        """获取指定坐标附近的文字"""
        results = self.recognize(image)
        for r in results:
            # 判断坐标是否在 bbox 内部
            xs = [p[0] for p in r.bbox]
            ys = [p[1] for p in r.bbox]
            if min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys):
                return r
        return None


# 全局单例
ocr_engine = OCREngine()