"""
iOS 设备客户端封装 - 基于 WDA (WebDriverAgent) + tidevice
WDA 替代方案：不依赖开发者镜像，通过 HTTP API 控制设备
"""
import subprocess
import time
import random
import os
import platform
import json
import threading
from typing import Optional, Tuple
from loguru import logger

from backend.config import config


class iOSClient:
    """
    iOS 设备客户端
    优先使用 WDA HTTP API 进行触摸操作（不依赖开发者镜像）
    使用 tidevice 进行设备管理和端口转发
    """

    # WDA 默认端口
    WDA_PORT = 8100
    WDA_MJPEG_PORT = 9100

    def __init__(self, device_udid: str):
        self.udid = device_udid
        self.serial = device_udid
        self.connected = False

        # WDA 相关
        self._wda_url = f"http://127.0.0.1:{self.WDA_PORT}"
        self._wda_session_id: Optional[str] = None
        self._wda_ready = False
        self._relay_process: Optional[subprocess.Popen] = None
        self._screen_w = 0
        self._screen_h = 0

        self._ensure_tidevice_dirs()
        self._check_connection()
        self._init_screen_size()

        # 尝试启动 WDA 连接
        self._setup_wda()

    # ========== 设备连接与信息 ==========

    def _ensure_tidevice_dirs(self):
        """确保 tidevice 所需目录存在"""
        tidevice_dir = config.TIDEVICE_DIR
        ssl_dir = os.path.join(tidevice_dir, "ssl")
        device_support_dir = os.path.join(tidevice_dir, "device-support")
        os.makedirs(ssl_dir, exist_ok=True)
        os.makedirs(device_support_dir, exist_ok=True)

    def _get_python_path(self) -> str:
        """获取 Python 可执行文件路径"""
        import shutil
        python_path = shutil.which("python") or shutil.which("python3") or "python"
        return python_path

    def _run(self, *args, timeout: int = 10) -> Tuple[bool, str]:
        """执行 tidevice 命令"""
        python_path = self._get_python_path()
        cmd = [python_path, "-m", "tidevice", "-u", self.udid, *args]

        try:
            env = os.environ.copy()
            env['TIDEVICE_HOME'] = config.TIDEVICE_DIR
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
        self.connected = ok
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
            "screen_width": self._screen_w or 0,
            "screen_height": self._screen_h or 0,
            "connected": self.is_connected(),
        }
        if ok and out:
            try:
                device_info = json.loads(out)
                info["model"] = device_info.get("DeviceName", "iPhone")
                info["os_version"] = device_info.get("ProductVersion", "Unknown")
            except Exception:
                pass
        return info

    def is_connected(self) -> bool:
        """检查设备是否真正连接"""
        try:
            ok, _ = self._run("info", timeout=3)
            self.connected = ok
            return ok
        except Exception:
            pass
        self.connected = False
        return False

    def _init_screen_size(self):
        """初始化屏幕尺寸"""
        try:
            ok, out = self._run("info", timeout=3)
            if ok and out:
                device_info = json.loads(out)
                model = device_info.get("DeviceName", "")
                model_size_map = {
                    "iPhone 15 Pro Max": (1290, 2796),
                    "iPhone 15 Pro": (1179, 2556),
                    "iPhone 15 Plus": (1284, 2778),
                    "iPhone 15": (1179, 2556),
                    "iPhone 14 Pro Max": (1290, 2796),
                    "iPhone 14 Pro": (1179, 2556),
                    "iPhone 14 Plus": (1284, 2778),
                    "iPhone 14": (1170, 2532),
                    "iPhone 13 Pro Max": (1284, 2778),
                    "iPhone 13 Pro": (1170, 2532),
                    "iPhone 13": (1170, 2532),
                    "iPhone 13 mini": (1080, 2340),
                    "iPhone 12 Pro Max": (1284, 2778),
                    "iPhone 12 Pro": (1170, 2532),
                    "iPhone 12": (1170, 2532),
                    "iPhone 12 mini": (1080, 2340),
                    "iPhone 11 Pro Max": (1242, 2688),
                    "iPhone 11 Pro": (1125, 2436),
                    "iPhone 11": (828, 1792),
                    "iPhone XS Max": (1242, 2688),
                    "iPhone XS": (1125, 2436),
                    "iPhone XR": (828, 1792),
                    "iPhone X": (1125, 2436),
                    "iPhone SE (3rd generation)": (750, 1334),
                    "iPhone SE (2nd generation)": (750, 1334),
                }
                self._screen_w, self._screen_h = model_size_map.get(model, (1179, 2556))
        except Exception:
            self._screen_w, self._screen_h = 1179, 2556

    def get_screen_size(self) -> Tuple[int, int]:
        """获取屏幕宽高"""
        return self._screen_w, self._screen_h

    # ========== WDA 设置与通信 ==========

    def _setup_wda(self):
        """设置 WDA 连接（通过 USB 端口转发）"""
        logger.info(f"正在设置 WDA 连接...")

        # 启动 tidevice relay 做端口转发（WDA 8100 端口）
        self._start_relay()

        # 等待几秒让转发建立
        time.sleep(2)

        # 尝试连接 WDA
        self._connect_wda()

    def _start_relay(self):
        """启动 USB 端口转发 (8100 -> device WDA)"""
        try:
            python_path = self._get_python_path()
            cmd = [python_path, "-m", "tidevice", "-u", self.udid, "relay",
                   str(self.WDA_PORT), str(self.WDA_PORT)]

            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            self._relay_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
            logger.info(f"WDA 端口转发已启动: {self.WDA_PORT} -> 设备:{self.WDA_PORT}")
        except Exception as e:
            logger.warning(f"启动端口转发失败: {e}")

    def _connect_wda(self):
        """连接 WDA 并创建 session"""
        import urllib.request
        import urllib.error

        # 尝试获取 WDA 状态
        for i in range(10):
            try:
                req = urllib.request.Request(
                    f"{self._wda_url}/status",
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    session_id = data.get("sessionId")
                    if session_id:
                        self._wda_session_id = session_id
                        self._wda_ready = True
                        logger.info(f"WDA 已连接, session: {session_id[:8]}...")
                        return
            except Exception:
                pass

            # 如果状态检查失败，尝试创建新 session
            try:
                req_body = json.dumps({
                    "capabilities": {
                        "bundleId": "com.apple.Preferences"
                    }
                }).encode()
                req = urllib.request.Request(
                    f"{self._wda_url}/session",
                    data=req_body,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    session_id = data.get("sessionId")
                    if session_id:
                        self._wda_session_id = session_id
                        self._wda_ready = True
                        logger.info(f"WDA session 已创建: {session_id[:8]}...")
                        return
            except Exception:
                pass

            if i % 3 == 0:
                logger.debug(f"等待 WDA 就绪... ({i+1}/10)")
            time.sleep(1)

        logger.warning("WDA 连接失败，将使用 xctest 作为备用方案")

    def _wda_request(self, method: str, path: str, data: dict = None) -> Tuple[bool, dict]:
        """发送 WDA HTTP 请求"""
        import urllib.request
        import urllib.error

        if not self._wda_ready or not self._wda_session_id:
            return False, {"error": "WDA not ready"}

        url = f"{self._wda_url}/session/{self._wda_session_id}{path}"
        req_body = json.dumps(data).encode() if data else None

        try:
            req = urllib.request.Request(
                url, data=req_body,
                headers={"Content-Type": "application/json"},
                method=method
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return True, result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode() if e.fp else str(e)
            return False, {"error": error_body}
        except Exception as e:
            return False, {"error": str(e)}

    # ========== 触摸操作 ==========

    def can_control(self) -> bool:
        """检查是否可以控制设备（WDA 或 xctest 至少一个可用）"""
        if self._wda_ready:
            return True
        ok, out = self._run("xctest", "--help", timeout=5)
        if ok or ("unrecognized arguments" not in out and "error" not in out.lower()):
            return True
        return False

    def tap(self, x: int, y: int):
        """点击屏幕坐标"""
        success = self._do_touch("tap", x, y)
        if not success:
            raise RuntimeError(f"iOS 点击失败：无法控制设备 (坐标: {x}, {y})")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动"""
        success = self._do_touch("swipe", x1, y1, x2, y2, duration_ms)
        if not success:
            raise RuntimeError(f"iOS 滑动失败：无法控制设备")

    def long_press(self, x: int, y: int, duration_ms: int = 1000):
        """长按"""
        success = self._do_touch("long_press", x, y, None, None, duration_ms)
        if not success:
            raise RuntimeError(f"iOS 长按失败：无法控制设备")

    def _do_touch(self, action: str, x1: int, y1: int,
                  x2: int = None, y2: int = None, duration_ms: int = 300) -> bool:
        """统一触摸操作入口 - 返回是否成功"""
        if self._wda_ready:
            if self._wda_touch(action, x1, y1, x2, y2, duration_ms):
                return True
            logger.warning(f"WDA {action} 失败，尝试 xctest")
        
        if self._xctest_touch(action, x1, y1, x2, y2, duration_ms):
            return True
        
        logger.error(f"iOS {action} 操作失败：WDA 和 xctest 均不可用")
        return False

    def _wda_touch(self, action: str, x1: int, y1: int,
                   x2: int = None, y2: int = None, duration_ms: int = 300) -> bool:
        """通过 WDA HTTP API 执行触摸操作"""
        try:
            if action == "tap":
                ok, result = self._wda_request("POST", "/wda/tap/0", {"x": x1, "y": y1})
                return ok
            elif action == "swipe":
                ok, result = self._wda_request("POST", "/wda/dragfromtoforduration", {
                    "fromX": x1, "fromY": y1, "toX": x2, "toY": y2,
                    "duration": duration_ms / 1000.0
                })
                return ok
            elif action == "long_press":
                ok, result = self._wda_request("POST", "/wda/dragfromtoforduration", {
                    "fromX": x1, "fromY": y1, "toX": x1, "toY": y1,
                    "duration": duration_ms / 1000.0
                })
                return ok
        except Exception as e:
            logger.warning(f"WDA {action} 失败: {e}")
        return False

    def _xctest_touch(self, action: str, x1: int, y1: int,
                      x2: int = None, y2: int = None, duration_ms: int = 300) -> bool:
        """通过 tidevice xctest 执行触摸操作 - 返回是否成功"""
        try:
            if action == "tap":
                ok, out = self._run("xctest", "tap", str(x1), str(y1), timeout=10)
                if ok:
                    return True
                logger.error(f"xctest tap 失败: {out}")
                return False
            elif action == "swipe":
                duration_s = duration_ms / 1000.0
                ok, out = self._run("xctest", "swipe",
                                    str(x1), str(y1), str(x2), str(y2), str(duration_s), timeout=10)
                if ok:
                    return True
                logger.error(f"xctest swipe 失败: {out}")
                return False
            elif action == "long_press":
                duration_s = duration_ms / 1000.0
                ok, out = self._run("xctest", "swipe",
                                    str(x1), str(y1), str(x1), str(y1), str(duration_s), timeout=10)
                if ok:
                    return True
                logger.error(f"xctest long_press 失败: {out}")
                return False
        except Exception as e:
            logger.error(f"xctest {action} 异常: {e}")
        return False

    # ========== 输入操作 ==========

    def input_text(self, text: str):
        """输入文本"""
        if self._wda_ready:
            try:
                for ch in text:
                    ok, result = self._wda_request("POST", "/wda/keys", {"value": [ch]})
                    if ok:
                        time.sleep(0.05)
                return
            except Exception:
                pass

        # 备用：使用 xctest
        try:
            ok, out = self._run("xctest", "text", text)
            if not ok and out:
                logger.debug(f"xctest text 失败: {out}")
        except Exception:
            pass

    def input_keyevent(self, key):
        """发送按键"""
        # iOS 没有物理按键事件，通过 WDA 实现 home 键等
        if key in ("home", "1") and self._wda_ready:
            self._wda_request("POST", "/wda/homescreen", {})
            return

        # xctest 备用
        try:
            key_str = str(key)
            keycode = {"home": "1", "back": "1", "enter": "1",
                        "1": "1", "2": "2", "3": "3", "4": "4"}.get(key_str, key_str)
            self._run("xctest", "press", keycode)
        except Exception:
            pass

    # ========== 截图 ==========

    def screenshot(self, save_path: str) -> bool:
        """截图并保存（WDA 或 tidevice 方式）"""
        # 方式1：WDA 截图
        if self._wda_ready:
            try:
                import urllib.request
                import base64
                req = urllib.request.Request(f"{self._wda_url}/screenshot")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    img_b64 = data.get("value", "")
                    if img_b64:
                        img_bytes = base64.b64decode(img_b64)
                        with open(save_path, "wb") as f:
                            f.write(img_bytes)
                        return True
            except Exception:
                pass

        # 方式2：tidevice 截图
        ok, out = self._run("screenshot", save_path, timeout=10)
        return ok

    # ========== 应用管理 ==========

    def start_app(self, bundle_id: str):
        """启动应用"""
        app_name = self._bundle_id_to_app_name(bundle_id)
        logger.info(f"请在 iPhone 上手动打开应用: {app_name}")

        # 等待用户打开应用
        for i in range(30):
            if self.is_connected():
                logger.info("设备已就绪")
                return True, f"应用 {app_name} 已启动（手动）"
            time.sleep(1)
            if i % 15 == 0:
                logger.info(f"等待用户启动应用... ({i}/30秒)")

        return False, f"请手动打开 {app_name}"

    def stop_app(self, bundle_id: str):
        """停止应用 (WDA 方式)"""
        if self._wda_ready:
            try:
                self._wda_request("POST", "/wda/deactivateApp", {"bundleId": bundle_id})
                return
            except Exception:
                pass
        logger.info("请在 iPhone 上手动关闭应用")

    def get_current_activity(self) -> str:
        """获取当前前台应用"""
        return ""

    def is_app_foreground(self, bundle_id: str) -> bool:
        """判断应用是否在前台"""
        return self.is_connected()

    # ========== 人类模拟操作 ==========

    def human_tap(self, x: int, y: int):
        """模拟人类点击（带随机偏移和延迟）"""
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

    def close(self):
        """清理资源"""
        if self._relay_process:
            try:
                self._relay_process.terminate()
                self._relay_process.wait(timeout=3)
            except Exception:
                self._relay_process.kill()
            logger.debug("WDA relay 已关闭")

    @staticmethod
    def _bundle_id_to_app_name(bundle_id: str) -> str:
        """Bundle ID 转应用名称"""
        bundle_map = {
            "com.tencent.mm": "微信",
            "com.ss.android.ugc.aweme": "抖音",
            "com.xingin.discover": "小红书",
        }
        return bundle_map.get(bundle_id, bundle_id)