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
            logger.debug(f"找到 tidevice: {tidevice_path}")
            return tidevice_path
        
        # 根据不同系统查找常见位置
        system = platform.system()
        if system == "Windows":
            # Windows 常见位置
            user_profile = os.environ.get("USERPROFILE", "")
            python_versions = ["Python313", "Python312", "Python311", "Python310", "Python39", "Python38"]
            common_paths = []
            for py_ver in python_versions:
                common_paths.append(os.path.join(user_profile, "AppData", "Roaming", "Python", py_ver, "Scripts", "tidevice.exe"))
                common_paths.append(os.path.join(user_profile, "AppData", "Local", "Programs", "Python", py_ver, "Scripts", "tidevice.exe"))
            # 检查 PATH 中的 Python Scripts 目录
            path_env = os.environ.get("PATH", "")
            for path in path_env.split(os.pathsep):
                if "Scripts" in path and os.path.exists(path):
                    common_paths.append(os.path.join(path, "tidevice.exe"))
        elif system == "Darwin":  # macOS
            common_paths = [
                "/Users/gzt/Library/Python/3.8/bin/tidevice",
                "/usr/local/bin/tidevice",
                "/opt/homebrew/bin/tidevice",
                os.path.join(os.path.expanduser("~"), "Library", "Python", "3.8", "bin", "tidevice"),
                os.path.join(os.path.expanduser("~"), "Library", "Python", "3.9", "bin", "tidevice"),
                os.path.join(os.path.expanduser("~"), "Library", "Python", "3.10", "bin", "tidevice"),
            ]
        else:  # Linux
            common_paths = [
                "/usr/local/bin/tidevice",
                os.path.join(os.path.expanduser("~"), ".local", "bin", "tidevice"),
            ]
        
        for path in common_paths:
            if os.path.exists(path):
                logger.debug(f"找到 tidevice: {path}")
                return path
        
        # 如果都没找到，返回默认值（让系统查找）
        logger.debug("未找到 tidevice，将使用系统 PATH 查找")
        return "tidevice"

    def _run(self, *args, timeout: int = 10) -> Tuple[bool, str]:
        """执行 tidevice 命令，返回 (成功, 输出)"""
        import shutil
        python_path = shutil.which("python") or shutil.which("python3")
        if not python_path:
            return False, "未找到 Python 可执行文件"
        
        cmd = [python_path, "-m", "tidevice", "-u", self.udid, *args]
        logger.debug(f"tidevice: {' '.join(cmd)}")
        try:
            # 设置 TIDEVICE_HOME 环境变量，让 tidevice 使用我们指定的目录
            env = os.environ.copy()
            env['TIDEVICE_HOME'] = config.TIDEVICE_DIR
            env['REQUESTS_CA_BUNDLE'] = ''
            env['CURL_CA_BUNDLE'] = ''
            env['PYTHONIOENCODING'] = 'utf-8'
            
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
            # 使用 info 命令检查设备连接状态
            ok, _ = self._run("info", timeout=3)
            self.connected = ok
            return ok
        except Exception as e:
            logger.debug(f"检查设备连接状态失败: {e}")
        
        self.connected = False
        return False

    def tap(self, x: int, y: int):
        """点击屏幕坐标 - 使用 tidevice ui 命令"""
        self._run("ui", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动 - 使用 tidevice ui 命令"""
        duration_s = duration_ms / 1000
        self._run("ui", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_s))

    def long_press(self, x: int, y: int, duration_ms: int = 1000):
        """长按 - 使用 tidevice ui 命令"""
        duration_s = duration_ms / 1000
        self._run("ui", "swipe", str(x), str(y), str(x), str(y), str(duration_s))

    def input_text(self, text: str):
        """输入文本"""
        self._run("ui", "text", text)

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
        self._run("ui", "press", keycode)

    def screenshot(self, save_path: str) -> bool:
        """截图并保存到指定路径"""
        ok, out = self._run("screenshot", save_path)
        return ok

    def start_app(self, bundle_id: str):
        """启动应用（需要 Bundle ID）"""
        logger.info(f"iOSClient.start_app: bundle_id={bundle_id}")
        
        # 首先检查应用是否已经在前台
        if self.is_app_foreground(bundle_id):
            logger.info(f"应用 {bundle_id} 已在前台")
            return True, "应用已在前台"
        
        # 尝试使用 tidevice launch
        success, output = self._try_start_app_with_tidevice(bundle_id)
        if success:
            return True, output
        
        # 如果失败是因为缺少开发者镜像，给出明确提示
        if "18.5" in output or "device-support" in output:
            logger.warning(f"需要 iOS 开发者镜像，请手动在设备上启动应用: {bundle_id}")
            # 等待用户手动启动应用
            for _ in range(10):
                if self.is_app_foreground(bundle_id):
                    logger.info(f"检测到应用已启动")
                    return True, "应用已启动（手动）"
                time.sleep(1)
        
        logger.warning(f"无法自动启动应用，请手动在设备上打开: {bundle_id}")
        return False, f"无法自动启动应用，请手动在设备上打开: {bundle_id}"
    
    def _try_start_app_with_tidevice(self, bundle_id: str):
        """使用 tidevice 启动应用"""
        import shutil
        python_path = shutil.which("python") or shutil.which("python3")
        if not python_path:
            return False, "未找到 Python 可执行文件"
        
        cmd = [python_path, "-m", "tidevice", "-u", self.udid, "launch", bundle_id]
        logger.debug(f"尝试 tidevice 启动: {' '.join(cmd)}")
        
        env = os.environ.copy()
        env['TIDEVICE_HOME'] = config.TIDEVICE_DIR
        env['REQUESTS_CA_BUNDLE'] = ''
        env['CURL_CA_BUNDLE'] = ''
        env['PYTHONIOENCODING'] = 'utf-8'
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, encoding="utf-8", errors="replace", env=env)
            output = result.stdout.strip() or result.stderr.strip()
            
            if result.returncode == 0:
                logger.info(f"tidevice 启动成功: {bundle_id}")
                return True, output
            else:
                if "18.5.zip" in output or "device-support" in output:
                    logger.warning(f"tidevice 需要 iOS 18.5 开发者镜像")
                return False, output
        except Exception as e:
            logger.warning(f"tidevice 启动异常: {e}")
            return False, str(e)
    
    def _try_start_app_with_simctl(self, bundle_id: str):
        """使用 xcrun simctl 启动应用（仅适用于模拟器）"""
        cmd = ["xcrun", "simctl", "launch", self.udid, bundle_id]
        logger.debug(f"尝试 simctl 启动: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
            if result.returncode == 0:
                logger.info(f"simctl 启动成功: {bundle_id}")
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except Exception as e:
            logger.warning(f"simctl 启动异常: {e}")
            return False, str(e)
    
    def _try_start_app_with_applescript(self, bundle_id: str):
        """使用 AppleScript 通过 Xcode Devices 窗口启动应用"""
        app_name = self._bundle_id_to_app_name(bundle_id)
        script = f'''
            tell application "Xcode"
                activate
                delay 1
            end tell
            tell application "System Events"
                tell process "Xcode"
                    click menu item "Devices and Simulators" of menu "Window" of menu bar 1
                    delay 2
                end tell
            end tell
        '''
        
        logger.debug(f"尝试 AppleScript 启动应用: {app_name}")
        
        try:
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                logger.info(f"AppleScript 执行成功")
                return True, "Xcode Devices 窗口已打开，请手动选择设备并启动应用"
            return False, result.stderr.strip()
        except Exception as e:
            logger.warning(f"AppleScript 执行异常: {e}")
            return False, str(e)
    
    @staticmethod
    def _bundle_id_to_app_name(bundle_id: str) -> str:
        """根据 Bundle ID 获取应用名称"""
        bundle_map = {
            "com.tencent.mm": "微信",
            "com.ss.android.ugc.aweme": "抖音",
            "com.xingin.discover": "小红书",
        }
        return bundle_map.get(bundle_id, bundle_id)

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