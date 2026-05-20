"""
触控操作控制器 - 封装所有设备触控操作
"""
import time
import random
from typing import Tuple
from loguru import logger

from backend.adb_client import ADBClient
from backend.config import config


class TouchController:
    """
    设备触控操作统一入口
    所有坐标操作均为相对坐标（0.0 ~ 1.0），内部自动转为绝对坐标
    """

    # Android 常用按键码
    KEY_BACK = 4
    KEY_HOME = 3
    KEY_MENU = 82
    KEY_APP_SWITCH = 187
    KEY_ENTER = 66
    KEY_DEL = 67
    KEY_VOLUME_UP = 24
    KEY_VOLUME_DOWN = 25
    KEY_POWER = 26

    def __init__(self, adb: ADBClient):
        self.adb = adb
        self._screen_w = 0
        self._screen_h = 0
        self._init_screen_size()

    def _init_screen_size(self):
        self._screen_w, self._screen_h = self.adb.get_screen_size()

    def _to_absolute(self, x: float, y: float) -> Tuple[int, int]:
        """相对坐标转绝对坐标"""
        if 0 <= x <= 1 and 0 <= y <= 1:
            return int(x * self._screen_w), int(y * self._screen_h)
        return int(x), int(y)

    @property
    def screen_size(self) -> Tuple[int, int]:
        return self._screen_w, self._screen_h

    # ================== 点击 ==================

    def tap(self, x: float, y: float, human_like: bool = True):
        """
        点击指定坐标
        x, y: 支持相对坐标(0.0~1.0)或绝对坐标(像素)
        """
        ax, ay = self._to_absolute(x, y)
        if human_like:
            self.adb.human_tap(ax, ay)
        else:
            self.adb.tap(ax, ay)
        logger.debug(f"点击: ({ax}, {ay})")

    def tap_center(self, human_like: bool = True):
        """点击屏幕中心"""
        self.tap(0.5, 0.5, human_like)

    # ================== 长按 ==================

    def long_press(self, x: float, y: float, duration_ms: int = 1000):
        """长按"""
        ax, ay = self._to_absolute(x, y)
        self.adb.long_press(ax, ay, duration_ms)
        logger.debug(f"长按: ({ax}, {ay}) {duration_ms}ms")

    # ================== 滑动 ==================

    def swipe(self, from_x: float, from_y: float,
              to_x: float, to_y: float,
              human_like: bool = True):
        """从 (from_x, from_y) 滑动到 (to_x, to_y)"""
        fx, fy = self._to_absolute(from_x, from_y)
        tx, ty = self._to_absolute(to_x, to_y)
        if human_like:
            self.adb.human_swipe(fx, fy, tx, ty)
        else:
            self.adb.swipe(fx, fy, tx, ty)

    def swipe_up(self, distance: float = 0.5, human_like: bool = True):
        """向上滑动（页面向上滚）"""
        mid_x = 0.5
        self.swipe(mid_x, 0.7, mid_x, 0.7 - distance, human_like)

    def swipe_down(self, distance: float = 0.5, human_like: bool = True):
        """向下滑动（页面向下滚）"""
        mid_x = 0.5
        self.swipe(mid_x, 0.3, mid_x, 0.3 + distance, human_like)

    def swipe_left(self, distance: float = 0.5, human_like: bool = True):
        """向左滑动"""
        mid_y = 0.5
        self.swipe(0.7, mid_y, 0.7 - distance, mid_y, human_like)

    def swipe_right(self, distance: float = 0.5, human_like: bool = True):
        """向右滑动"""
        mid_y = 0.5
        self.swipe(0.3, mid_y, 0.3 + distance, mid_y, human_like)

    # ================== 输入 ==================

    def type_text(self, text: str, human_like: bool = True):
        """输入文本"""
        if human_like:
            self.adb.human_type(text)
        else:
            self.adb.input_text(text)
        logger.debug(f"输入: {text}")

    def clear_text(self, count: int = 50):
        """清空输入框"""
        for _ in range(count):
            self.adb.input_keyevent(self.KEY_DEL)
            time.sleep(0.005)

    # ================== 按键 ==================

    def press_back(self):
        """返回键"""
        self.adb.input_keyevent(self.KEY_BACK)

    def press_home(self):
        """Home 键"""
        self.adb.input_keyevent(self.KEY_HOME)

    def press_enter(self):
        """回车键"""
        self.adb.input_keyevent(self.KEY_ENTER)

    def press_app_switch(self):
        """多任务切换键"""
        self.adb.input_keyevent(self.KEY_APP_SWITCH)

    # ================== 等待 ==================

    def wait(self, seconds: float = 1.0):
        """等待指定秒数"""
        time.sleep(seconds)

    def random_wait(self, min_sec: float = 0.5, max_sec: float = 2.0):
        """随机等待（模拟人类犹豫）"""
        time.sleep(random.uniform(min_sec, max_sec))

    # ================== 组合操作 ==================

    def swipe_up_multiple(self, count: int = 3, interval: float = 1.0):
        """连续向上滑动多次"""
        for _ in range(count):
            self.swipe_up()
            self.wait(interval)

    def swipe_to_refresh(self):
        """下拉刷新"""
        self.swipe(0.5, 0.3, 0.5, 0.7)