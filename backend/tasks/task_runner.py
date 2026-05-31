"""
任务执行器 - 解析任务动作列表并执行
支持 Android 和 iOS 双平台，支持高级任务
"""
import time
import threading
from typing import Dict, Optional, Union
from loguru import logger

from backend.actions.touch import TouchController
from backend.vision.element_finder import ElementFinder
from backend.device_manager import device_manager
from backend.apps.advanced_executor import AdvancedTaskExecutor


class TaskRunner:
    """
    任务执行器
    解析 TaskDefinition 中的 actions 列表并执行
    支持普通任务和高级任务两种模式
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

    # 任务状态枚举
    TASK_STATUS_IDLE = "idle"
    TASK_STATUS_RUNNING = "running"
    TASK_STATUS_CANCELLED = "cancelled"
    TASK_STATUS_COMPLETED = "completed"
    TASK_STATUS_FAILED = "failed"

    def __init__(self):
        self._running_tasks: Dict[str, threading.Thread] = {}
        self._cancel_flags: Dict[str, bool] = {}
        self._task_status: Dict[str, str] = {}  # task_id -> status

    def get_status(self, task_id: str) -> str:
        """获取任务执行状态"""
        return self._task_status.get(task_id, self.TASK_STATUS_IDLE)

    def set_status(self, task_id: str, status: str):
        """设置任务执行状态"""
        self._task_status[task_id] = status

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

        device_manager.mark_busy(serial, task.task_id)
        self._cancel_flags[task.task_id] = False

        try:
            logger.info(f"开始执行任务 [{task.name}] 在设备 {device.os_type} {serial}")
            self.set_status(task.task_id, self.TASK_STATUS_RUNNING)
            
            # 判断是否为高级任务
            if task.is_advanced:
                logger.info("执行高级任务模式")
                result = self._execute_advanced_task(task, device)
            else:
                logger.info("执行普通任务模式")
                result = self._execute_normal_task(task, device)
            
            if result:
                self.set_status(task.task_id, self.TASK_STATUS_COMPLETED)
            else:
                self.set_status(task.task_id, self.TASK_STATUS_FAILED)
            return result

        except Exception as e:
            logger.error(f"任务执行异常: {e}")
            self.set_status(task.task_id, self.TASK_STATUS_FAILED)
            return False
        finally:
            device_manager.mark_idle(serial)
            self._cancel_flags.pop(task.task_id, None)
            # 任务结束后延迟清除状态（保留状态显示一段时间）
            import threading
            def clear_status():
                time.sleep(10)
                self._task_status.pop(task.task_id, None)
            threading.Thread(target=clear_status, daemon=True).start()

    def _execute_normal_task(self, task, device) -> bool:
        """执行普通任务（基于动作列表）"""
        client = device.client
        touch = TouchController(client)
        finder = ElementFinder(client)
        
        actions = task.actions or []

        if task.app:
            self._start_app_for_task(task.app, device)

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
                getattr(self, handler)(touch, finder, client, action.get("params", {}), device.os_type)
            except Exception as e:
                logger.error(f"步骤 {i+1} 执行失败: {e}")
                return False

        logger.info(f"任务 [{task.name}] 执行完成")
        return True

    def _execute_advanced_task(self, task, device) -> bool:
        """执行高级任务（主题词浏览+互动）"""
        try:
            executor = AdvancedTaskExecutor(device, task.advanced_config)
            executor.execute()
            logger.info(f"高级任务 [{task.name}] 执行完成")
            return True
        except Exception as e:
            logger.error(f"高级任务 [{task.name}] 执行失败: {e}")
            return False

    def cancel(self, task_id: str):
        """取消正在执行的任务"""
        self._cancel_flags[task_id] = True
        self.set_status(task_id, self.TASK_STATUS_CANCELLED)

    # ================== 动作处理方法 ==================

    def _do_tap(self, touch: TouchController, finder, client, params, os_type):
        x, y = params.get("x", 0.5), params.get("y", 0.5)
        human = params.get("human_like", True)
        touch.tap(x, y, human)

    def _do_tap_text(self, touch: TouchController, finder, client, params, os_type):
        keyword = params["text"]
        timeout = params.get("timeout", None)
        finder.click_text(keyword, timeout)

    def _do_tap_image(self, touch: TouchController, finder, client, params, os_type):
        template = params["template"]
        timeout = params.get("timeout", None)
        finder.click_image(template, timeout)

    def _do_swipe(self, touch: TouchController, finder, client, params, os_type):
        fx, fy = params.get("from_x", 0.5), params.get("from_y", 0.7)
        tx, ty = params.get("to_x", 0.5), params.get("to_y", 0.3)
        human = params.get("human_like", True)
        touch.swipe(fx, fy, tx, ty, human)

    def _do_swipe_up(self, touch: TouchController, finder, client, params, os_type):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_up(distance, human)

    def _do_swipe_down(self, touch: TouchController, finder, client, params, os_type):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_down(distance, human)

    def _do_swipe_left(self, touch: TouchController, finder, client, params, os_type):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_left(distance, human)

    def _do_swipe_right(self, touch: TouchController, finder, client, params, os_type):
        distance = params.get("distance", 0.5)
        human = params.get("human_like", True)
        touch.swipe_right(distance, human)

    def _do_long_press(self, touch: TouchController, finder, client, params, os_type):
        x, y = params.get("x", 0.5), params.get("y", 0.5)
        duration = params.get("duration_ms", 1000)
        touch.long_press(x, y, duration)

    def _do_type(self, touch: TouchController, finder, client, params, os_type):
        text = params.get("text", "")
        human = params.get("human_like", True)
        touch.type_text(text, human)

    def _do_press_back(self, touch: TouchController, finder, client, params, os_type):
        touch.press_back()

    def _do_press_home(self, touch: TouchController, finder, client, params, os_type):
        touch.press_home()

    def _do_press_enter(self, touch: TouchController, finder, client, params, os_type):
        touch.press_enter()

    def _do_wait(self, touch: TouchController, finder, client, params, os_type):
        seconds = params.get("seconds", 1.0)
        touch.wait(seconds)

    def _do_random_wait(self, touch: TouchController, finder, client, params, os_type):
        min_sec = params.get("min", 0.5)
        max_sec = params.get("max", 2.0)
        touch.random_wait(min_sec, max_sec)

    def _do_start_app(self, touch: TouchController, finder, client, params, os_type):
        if os_type == "Android":
            package = params["package"]
            activity = params.get("activity")
            client.start_app(package, activity)
        else:  # iOS
            bundle_id = params.get("bundle_id", params.get("package"))
            client.start_app(bundle_id)
        touch.wait(2.0)  # 等待应用启动

    def _do_stop_app(self, touch: TouchController, finder, client, params, os_type):
        if os_type == "Android":
            package = params["package"]
            client.stop_app(package)
        else:  # iOS
            bundle_id = params.get("bundle_id", params.get("package"))
            client.stop_app(bundle_id)

    def _do_wait_text(self, touch: TouchController, finder, client, params, os_type):
        keyword = params["text"]
        timeout = params.get("timeout", None)
        result = finder.wait_text(keyword, timeout)
        if result is None:
            raise TimeoutError(f"超时等待文字: {keyword}")

    def _do_wait_image(self, touch: TouchController, finder, client, params, os_type):
        template = params["template"]
        timeout = params.get("timeout", None)
        result = finder.find_image(template, timeout)
        if result is None:
            raise TimeoutError(f"超时等待图片: {template}")

    def _do_scroll_until_text(self, touch: TouchController, finder, client, params, os_type):
        keyword = params["text"]
        direction = params.get("direction", "up")
        max_scrolls = params.get("max_scrolls", 10)
        result = finder.scroll_until_find_text(keyword, direction, max_scrolls)
        if result is None:
            raise TimeoutError(f"滚动未找到文字: {keyword}")

    def _do_swipe_up_multiple(self, touch: TouchController, finder, client, params, os_type):
        count = params.get("count", 3)
        interval = params.get("interval", 1.0)
        touch.swipe_up_multiple(count, interval)

    def _do_screenshot(self, touch: TouchController, finder, client, params, os_type):
        from backend.actions.screenshot import Screenshot
        ss = Screenshot(client)
        ss.capture()
        logger.info(f"截图保存到: {ss.path}")

    def _do_swipe_to_refresh(self, touch: TouchController, finder, client, params, os_type):
        touch.swipe_to_refresh()


    def _start_app_for_task(self, app_name: str, device):
        """根据应用名称启动对应的应用"""
        from backend.config import config
        
        package_map = config.APP_PACKAGES
        package = package_map.get(app_name)
        
        if not package:
            logger.warning(f"未知应用: {app_name}，无法启动")
            return
        
        logger.info(f"启动应用: {app_name} ({package})")
        
        client = device.client
        os_type = device.os_type
        
        if os_type == "Android":
            client.start_app(package)
        else:  # iOS
            bundle_id = package
            logger.info(f"iOS 设备，尝试启动应用: {bundle_id}")
            # 检查客户端是否有返回值
            result = client.start_app(bundle_id)
            if result is not None:
                ok, out = result
                logger.info(f"启动应用结果: ok={ok}, output={out}")
                if not ok:
                    logger.error(f"启动应用失败: {out}")
        
        # 等待应用启动
        from backend.actions.touch import TouchController
        touch = TouchController(client)
        touch.wait(3.0)


# 全局单例
task_runner = TaskRunner()