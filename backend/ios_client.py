"""
iOS 设备客户端封装 - 基于 tidevice
"""
import subprocess
import time
import random
import os
import platform
from typing import Optional, Tuple
from loguru import logger

from backend.config import config


class iOSClient:
    """封装 tidevice 命令，以设备 UDID 为操作单元"""

    def __init__(self, device_udid: str):
        self.udid = device_udid
        self.serial = device_udid  # 与 Android ADBClient 使用 serial，iOS 使用 udid，保持接口一致
        self.connected = False
        self._ensure_tidevice_dirs()
        self._check_connection()

    def _ensure_tidevice_dirs(self):
        """确保 tidevice 所需目录存在"""
        tidevice_dir = config.TIDEVICE_DIR
        ssl_dir = os.path.join(tidevice_dir, "ssl")
        device_support_dir = os.path.join(tidevice_dir, "device-support")
        os.makedirs(ssl_dir, exist_ok=True)
        os.makedirs(device_support_dir, exist_ok=True)
        logger.info(f"确保 tidevice 目录存在: {tidevice_dir}")

    @staticmethod
    def _get_tidevice_path() -> str:
        """获取 tidevice 命令路径（跨平台支持）"""
        import shutil
        
        # 首先尝试在系统 PATH 中查找
        tidevice_path = shutil.which("tidevice")
        if tidevice_path:
            return tidevice_path
        
        # 根据不同系统查找常见位置
        system = platform.system()
        if system == "Windows":
            # Windows 常见位置
            common_paths = [
                os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Roaming", "Python", "Scripts", "tidevice.exe"),
                os.path.join("C:\\", "Python38", "Scripts", "tidevice.exe"),
            ]
        elif system == "Darwin":  # macOS
            common_paths = [
                "/Users/gzt/Library/Python/3.8/bin/tidevice",
                "/usr/local/bin/tidevice",
                "/opt/homebrew/bin/tidevice",
                os.path.join(os.path.expanduser("~"), "Library", "Python", "3.8", "bin", "tidevice"),
            ]
        else:  # Linux
            common_paths = [
                "/usr/local/bin/tidevice",
                os.path.join(os.path.expanduser("~"), ".local", "bin", "tidevice"),
            ]
        
        for path in common_paths:
            if os.path.exists(path):
                return path
        
        # 如果都没找到，返回默认值
        return "tidevice"

    def _run(self, *args, timeout: int = 10) -> Tuple[bool, str]:
        """执行 tidevice 命令，返回 (成功, 输出)"""
        tidevice_path = self._get_tidevice_path()
        cmd = [tidevice_path, "-u", self.udid, *args]
        logger.debug(f"tidevice: {' '.join(cmd)}")
        try:
            # 设置 TIDEVICE_HOME 环境变量，让 tidevice 使用我们指定的目录
            env = os.environ.copy()
            env['TIDEVICE_HOME'] = config.TIDEVICE_DIR
            env['REQUESTS_CA_BUNDLE'] = ''
            env['CURL_CA_BUNDLE'] = ''
            
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
                env=env
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def _check_connection(self) -> bool:
        """检查设备是否连接"""
        ok, out = self._run("info", timeout=5)
        if ok:
            self.connected = True
        else:
            self.connected = False
        return ok

    def get_info(self) -> dict:
        """获取设备基本信息"""
        ok, out = self._run("info", timeout=10)
        info = {
            "udid": self.udid,
            "serial": self.udid,
            "model": "iOS Device",
            "os_type": "iOS",
            "os_version": "Unknown",
            "screen_width": 0,
            "screen_height": 0,
            "connected": self.is_connected(),
        }
        if ok:
            try:
                import json
                device_info = json.loads(out)
                info["model"] = device_info.get("DeviceName", "iPhone")
                info["os_version"] = device_info.get("ProductVersion", "Unknown")
            except Exception as e:
                logger.debug(f"解析设备信息失败: {e}")
        return info

    def is_connected(self) -> bool:
        """检查设备是否真正连接"""
        try:
            # 先尝试简单的设备列表扫描
            import shutil
            import os
            python_path = shutil.which("python3") or "/usr/local/bin/python3"
            tidevice_module_path = "/Users/gzt/Library/Python/3.8/lib/python/site-packages"
            env = os.environ.copy()
            env["REQUESTS_CA_BUNDLE"] = ""
            env["CURL_CA_BUNDLE"] = ""
            env["PYTHONPATH"] = tidevice_module_path + os.pathsep + env.get("PYTHONPATH", "")
            
            result = subprocess.run(
                [python_path, "-m", "tidevice", "list"],
                capture_output=True, text=True, timeout=5,
                env=env
            )
            
            if result.returncode == 0:
                # 检查输出中是否包含该设备
                if self.udid in result.stdout:
                    self.connected = True
                    return True
        except Exception as e:
            logger.debug(f"检查设备连接状态失败: {e}")
        
        # 如果上面的方法失败，尝试 info 命令
        ok, _ = self._run("info", timeout=3)
        self.connected = ok
        return ok

    def tap(self, x: int, y: int):
        """点击屏幕坐标"""
        self._run("xctest", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动"""
        duration_s = duration_ms / 1000
        self._run("xctest", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_s))

    def long_press(self, x: int, y: int, duration_ms: int = 1000):
        """长按"""
        duration_s = duration_ms / 1000
        self._run("xctest", "swipe", str(x), str(y), str(x), str(y), str(duration_s))

    def input_text(self, text: str):
        """输入文本"""
        self._run("xctest", "text", text)

    def input_keyevent(self, key):
        """发送按键（兼容字符串和数字）"""
        key_str = str(key)
        # iOS 常用按键映射
        key_map = {
            "home": "1",
            "volumeUp": "2",
            "volumeDown": "3",
            "power": "4",
            "back": "1",  # iOS 没有返回键，映射到 Home
            "enter": "1",
            "del": "1",
            "menu": "1",
            "app_switch": "1",
            "1": "1",
            "2": "2",
            "3": "3",
            "4": "4",
        }
        keycode = key_map.get(key_str, key_str)
        self._run("xctest", "press", keycode)

    def screenshot(self, save_path: str) -> bool:
        """截图并保存到指定路径"""
        ok, out = self._run("screenshot", save_path)
        if not ok:
            logger.warning(f"直接截图失败，尝试 xctest 截图...")
            # 备用方案：先保存到设备再 pull
            temp_path = f"/tmp/autobot_{int(time.time())}.png"
            ok, out = self._run("xctest", "screenshot", temp_path)
            if ok:
                ok, out = self._run("pull", temp_path, save_path)
        return ok

    def start_app(self, bundle_id: str):
        """启动应用（需要 Bundle ID）"""
        logger.info(f"iOSClient.start_app: bundle_id={bundle_id}")
        
        tidevice_path = self._get_tidevice_path()
        cmd = [tidevice_path, "-u", self.udid, "launch", bundle_id]
        logger.info(f"启动应用命令: {' '.join(cmd)}")
        
        env = os.environ.copy()
        env['TIDEVICE_HOME'] = config.TIDEVICE_DIR
        env['REQUESTS_CA_BUNDLE'] = ''
        env['CURL_CA_BUNDLE'] = ''
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace", env=env)
            output = result.stdout.strip() or result.stderr.strip()
            logger.info(f"启动应用结果: returncode={result.returncode}, output={output[:500]}")
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            logger.error("启动应用超时")
            return False, "timeout"
        except Exception as e:
            logger.error(f"启动应用异常: {e}")
            return False, str(e)

    def stop_app(self, bundle_id: str):
        """强制停止应用"""
        self._run("xctest", "terminate", bundle_id)

    def get_current_activity(self) -> str:
        """获取当前前台应用"""
        ok, out = self._run("xctest", "current_app")
        if ok:
            return out.strip()
        return ""

    def is_app_foreground(self, bundle_id: str) -> bool:
        """判断指定应用是否在前台"""
        current = self.get_current_activity()
        return bundle_id in current

    def human_tap(self, x: int, y: int):
        """模拟人类点击（带随机坐标偏移和延迟）"""
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
            self.input_text(ch)
            time.sleep(config.TYPING_INTERVAL)

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕宽高（iOS 需要截图后获取）"""
        from PIL import Image
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
        if self.screenshot(temp_path):
            try:
                img = Image.open(temp_path)
                w, h = img.size
                return w, h
            except Exception as e:
                logger.debug(f"获取屏幕尺寸失败: {e}")
            finally:
                try:
                    import os
                    os.unlink(temp_path)
                except:
                    pass
        return (0, 0)