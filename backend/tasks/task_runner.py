"""
任务执行器 - 解析任务动作列表并执行
"""
import time
import threading
from typing import Dict, Optional
from loguru import logger

from backend.adb_client import ADBClient
from backend.actions.touch import TouchController
from backend.vision.element_finder import ElementFinder
from backend.device_manager import device_manager


class TaskRunner:
    """
    任务执行器
    解析 TaskDefinition 中的 actions 列表并执行
    """

    # 支持的动作类型
    ACTION_HANDLERS: Dict[str, str] = {
        "tap": "_do_tap",
        "tap_text": "_do_tap_text",
        "tap_image": "_do_tap_image",
        "swipe": "_do_swipe",
        "swipe_up": "_do_swipe_up",
        "swipe_down": "_do_swipe_down",
        "swipe_left": "_do_swipe_left",
        "swipe_right": "_do_swipe_right",
        "long_press": "_do_long_press",
        "type": "_do_type",
        "press_back": "_do_press_back",
        "press_home": "_do_press_home",
        "press_enter": "_do_press_enter",
        "wait": "_do_wait",
        "random_wait": "_do_random_wait",
        "start_app": "_do_start_app",
        "stop_app": "_do_stop_app",
        "wait_text": "_do_wait_text",
        "wait_image": "_do_wait_image",
        "scroll_until_text": "_do_scroll_until_text",
        "swipe_up_multiple": "_do_swipe_up_multiple",
        "screenshot": "_do_screenshot",
        "swipe_to_refresh": "_do_swipe_to_refresh",
    }

    def __init__(self):
        self._running_tasks: Dict[str, threading.Thread] = {}
        self._cancel_flags: Dict[str, bool] = {}

    def execute(self, task, serial: str) -> bool:
        """
        在指定设备上执行任务
        返回 True/False 表示成功/失败
        """
        device = device_manager.get_device(serial)
        if device is None:
            logger.error(f"设备不存在: {serial}")
            return False

        if device.is_busy:
            logger.warning(f"设备 {serial} 正忙")
            return False

        adb = device.adb
        touch = TouchController(adb)
        finder = ElementFinder(adb)

        device_manager.mark_busy(serial, task.task_id)
        self._cancel_flags[task.task_id] = False

        try:
            logger.info(f"开始执行任务 [{task.name}] 在设备 {serial}")
            actions = task.actions or []

            for i, action in enumerate(actions):
                if self._cancel_flags.get(task.task_id):
                    logger.info(f"任务已取消: {task.name}")
                    return False

                action_type = action.get("type", "")
                handler = self.ACTION_HANDLERS.get(action_type)

                if handler is None:
                    logger.warning(f"未知动作类型: {action_type}")
                    continue

                logger.debug(f"步骤 {i+1}/{len(actions)}: {action_type} {action.get('params', {})}")

                try:
                    getattr(self, handler)(touch, finder, adb, action.get("params", {}))
                except Exception as e:
                    logger.error(f"步骤 {i+1} 执行失败: {e}")
                    return False

            logger.info(f"任务 [{task.name}] 执行完成")
            return True

        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            return False
        finally:
            device_manager.mark_idle(serial)
            self._cancel_flags.pop(task.task_id, None)

    def cancel(self, task_id: str):
        """取消正在执行的任务"""
        self._cancel_flags[task_id] = True

    # ================== 动作处理方法 ==================

    def _do_tap(self, touch: TouchController, finder, adb, params):
        x, y = params.get("x", 0.5), params.get("y", 0.5)
        human = params.get("human_like", True)
        touch.tap(x, y, human)

    def _do_tap_text(self, touch: TouchController, finder, adb, params):
        keyword = params["text"]
        timeout = params.get("timeout", None)
        finder.click_text(keyword, timeout)

    def _do_tap_image(self, touch: TouchController, finder, adb, params):
        template = params["template"]
        timeout = params.get("timeout", None)
        finder.click_image(template, timeout)

    def _do_swipe(self, touch: TouchController, finder, adb, params):
        fx, fy = params.get("from_x", 0.5), params.get("from_y", 0.7)
        tx, ty = params.get("to_x", 0.5), params.get("to_y", 0.3)
        human = params.get("human_like", True)
        touch.swipe(fx, fy, tx, ty, human)

    def _do_swipe_up(self, touch: TouchController, finder, adb, params):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_up(distance, human)

    def _do_swipe_down(self, touch: TouchController, finder, adb, params):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_down(distance, human)

    def _do_swipe_left(self, touch: TouchController, finder, adb, params):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_left(distance, human)

    def _do_swipe_right(self, touch: TouchController, finder, adb, params):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_right(distance, human)

    def _do_long_press(self, touch: TouchController, finder, adb, params):
        x, y = params.get("x", 0.5), params.get("y", 0.5)
        duration = params.get("duration_ms", 1000)
        touch.long_press(x, y, duration)

    def _do_type(self, touch: TouchController, finder, adb, params):
        text = params.get("text", "")
        human = params.get("human_like", True)
        touch.type_text(text, human)

    def _do_press_back(self, touch: TouchController, finder, adb, params):
        touch.press_back()

    def _do_press_home(self, touch: TouchController, finder, adb, params):
        touch.press_home()

    def _do_press_enter(self, touch: TouchController, finder, adb, params):
        touch.press_enter()

    def _do_wait(self, touch: TouchController, finder, adb, params):
        seconds = params.get("seconds", 1.0)
        touch.wait(seconds)

    def _do_random_wait(self, touch: TouchController, finder, adb, params):
        min_sec = params.get("min", 0.5)
        max_sec = params.get("max", 2.0)
        touch.random_wait(min_sec, max_sec)

    def _do_start_app(self, touch: TouchController, finder, adb, params):
        package = params["package"]
        activity = params.get("activity")
        adb.start_app(package, activity)
        touch.wait(2.0)  # 等待应用启动

    def _do_stop_app(self, touch: TouchController, finder, adb, params):
        package = params["package"]
        adb.stop_app(package)

    def _do_wait_text(self, touch: TouchController, finder, adb, params):
        keyword = params["text"]
        timeout = params.get("timeout", None)
        result = finder.wait_text(keyword, timeout)
        if result is None:
            raise TimeoutError(f"超时等待文字: {keyword}")

    def _do_wait_image(self, touch: TouchController, finder, adb, params):
        template = params["template"]
        timeout = params.get("timeout", None)
        result = finder.find_image(template, timeout)
        if result is None:
            raise TimeoutError(f"超时等待图片: {template}")

    def _do_scroll_until_text(self, touch: TouchController, finder, adb, params):
        keyword = params["text"]
        direction = params.get("direction", "up")
        max_scrolls = params.get("max_scrolls", 10)
        result = finder.scroll_until_find_text(keyword, direction, max_scrolls)
        if result is None:
            raise TimeoutError(f"滚动未找到文字: {keyword}")

    def _do_swipe_up_multiple(self, touch: TouchController, finder, adb, params):
        count = params.get("count", 3)
        interval = params.get("interval", 1.0)
        touch.swipe_up_multiple(count, interval)

    def _do_screenshot(self, touch: TouchController, finder, adb, params):
        from backend.actions.screenshot import Screenshot
        ss = Screenshot(adb)
        ss.capture()
        logger.info(f"截图保存到: {ss.path}")

    def _do_swipe_to_refresh(self, touch: TouchController, finder, adb, params):
        touch.swipe_to_refresh()


# 全局单例
task_runner = TaskRunner()