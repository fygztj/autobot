"""
ADB 客户端封装 - 底层 ADB 命令执行
"""
import subprocess
import time
import random
from typing import Optional, Tuple
from loguru import logger

from backend.config import config


class ADBClient:
    """封装 ADB 命令，以设备序列号为操作单元"""

    def __init__(self, device_serial: str):
        self.serial = device_serial
        # 尝试查找 adb 命令
        import shutil
        import os
        adb_path = shutil.which(config.ADB_PATH)
        if not adb_path:
            common_adb_paths = [
                "adb",
                "/usr/local/bin/adb",
                "/opt/homebrew/bin/adb",
                os.path.expanduser("~/Library/Android/sdk/platform-tools/adb"),
            ]
            for path in common_adb_paths:
                if shutil.which(path):
                    adb_path = shutil.which(path)
                    break
        if not adb_path:
            logger.warning(f"未找到 adb 命令，使用默认: {config.ADB_PATH}")
            adb_path = config.ADB_PATH
        
        self._adb_path = adb_path
        self._adb_base = [adb_path, "-s", device_serial]

    def _run(self, *args, timeout: int = 10) -> Tuple[bool, str]:
        """执行 ADB 命令，返回 (成功, 输出)"""
        cmd = self._adb_base + list(args)
        logger.debug(f"ADB: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace"
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    # ================== 设备信息 ==================

    def get_info(self) -> dict:
        """获取设备基本信息"""
        info = {"serial": self.serial, "connected": False}
        ok, out = self._run("shell", "getprop", "ro.product.model")
        if ok:
            info["model"] = out.strip()
            info["connected"] = True
        ok, out = self._run("shell", "getprop", "ro.build.version.release")
        if ok:
            info["android_version"] = out.strip()
        ok, out = self._run("shell", "wm", "size")
        if ok:
            # 输出格式: Physical size: 1080x2340
            size = out.strip().split(":")[-1].strip()
            parts = size.split("x")
            if len(parts) == 2:
                info["screen_width"] = int(parts[0])
                info["screen_height"] = int(parts[1])
        return info

    def is_connected(self) -> bool:
        ok, _ = self._run("shell", "echo", "alive", timeout=3)
        return ok

    # ================== 触控操作 ==================

    def tap(self, x: int, y: int):
        """点击屏幕坐标"""
        self._run("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动"""
        self._run("shell", "input", "swipe",
                   str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def long_press(self, x: int, y: int, duration_ms: int = 1000):
        """长按"""
        self._run("shell", "input", "swipe",
                   str(x), str(y), str(x), str(y), str(duration_ms))

    def input_text(self, text: str):
        """输入文本（ASCII 字符用 input text，中文用 am broadcast）"""
        # 转义特殊字符
        text = text.replace(" ", "%s").replace("&", "\\&")
        # 尝试直接输入
        ok, _ = self._run("shell", "input", "text", text)
        if not ok:
            # 中文等复杂文本通过 ADBKeyboard 或 app_process 方式
            self._input_text_broadcast(text)

    def _input_text_broadcast(self, text: str):
        """通过 broadcast 方式输入中文文本"""
        # 使用 ADBKeyBoard 如果安装了的话
        ok, _ = self._run("shell", "am", "broadcast",
                           "-a", "ADB_INPUT_TEXT",
                           "--es", "msg", text)
        if not ok:
            # 回退到逐字符输入
            for ch in text:
                self._run("shell", "input", "text", ch)

    def input_keyevent(self, keycode: int):
        """发送按键事件（如 KEYCODE_BACK=4, KEYCODE_HOME=3）"""
        self._run("shell", "input", "keyevent", str(keycode))

    # ================== 屏幕截图 ==================

    def screenshot(self, save_path: str) -> bool:
        """截图并保存到指定路径"""
        ok, _ = self._run("shell", "screencap", "-p", "/sdcard/autobot_screenshot.png")
        if not ok:
            return False
        ok, _ = self._run("pull", "/sdcard/autobot_screenshot.png", save_path)
        return ok

    # ================== 应用管理 ==================

    def start_app(self, package: str, activity: str = None):
        """启动应用"""
        if activity:
            self._run("shell", "am", "start", "-n", f"{package}/{activity}")
        else:
            self._run("shell", "monkey", "-p", package,
                       "-c", "android.intent.category.LAUNCHER", "1")

    def stop_app(self, package: str):
        """强制停止应用"""
        self._run("shell", "am", "force-stop", package)

    def get_current_activity(self) -> str:
        """获取当前前台 Activity"""
        ok, out = self._run("shell", "dumpsys", "activity", "activities")
        if ok:
            for line in out.split("\n"):
                if "mResumedActivity" in line or "mFocusedApp" in line:
                    return line.strip()
        return ""

    def is_app_foreground(self, package: str) -> bool:
        """判断指定应用是否在前台"""
        activity = self.get_current_activity()
        return package in activity

    # ================== 模拟人类操作的包装方法 ==================

    def human_tap(self, x: int, y: int):
        """模拟人类点击（带随机位置偏移和延迟）"""
        ox = random.randint(-3, 3)
        oy = random.randint(-3, 3)
        delay = random.uniform(config.CLICK_MIN_DELAY, config.CLICK_MAX_DELAY)
        time.sleep(delay)
        self.tap(x + ox, y + oy)

    def human_swipe(self, x1: int, y1: int, x2: int, y2: int):
        """模拟人类滑动（带随机持续时间）"""
        duration = random.uniform(config.SWIPE_DURATION_MIN, config.SWIPE_DURATION_MAX)
        duration_ms = int(duration * 1000)
        ox1 = random.randint(-5, 5)
        oy1 = random.randint(-5, 5)
        ox2 = random.randint(-5, 5)
        oy2 = random.randint(-5, 5)
        self.swipe(x1 + ox1, y1 + oy1, x2 + ox2, y2 + oy2, duration_ms)

    def human_type(self, text: str):
        """模拟人类逐字符输入"""
        for ch in text:
            self._run("shell", "input", "text", ch)
            time.sleep(config.TYPING_INTERVAL)

    # ================== 屏幕尺寸辅助 ==================

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕宽高"""
        info = self.get_info()
        return info.get("screen_width", 1080), info.get("screen_height", 1920)