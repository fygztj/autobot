"""
iOS 设备客户端封装 - 基于 WDA (WebDriverAgent) + tidevice
实现完整的 UI 自动化控制：点击、滑动、输入、启动 App、截图等
遵循 Apple 官方 XCUITest/WDA 通道，不依赖开发者镜像
"""
import subprocess
import time
import random
import os
import json
import urllib.request
import urllib.error
import base64
import shutil
from typing import Optional, Tuple, Dict, Any, List
from loguru import logger

from backend.config import config


class iOSClient:
    """
    iOS 设备客户端 - 支持 WDA HTTP API 进行完整 UI 自动化
    
    核心功能：
    - WDA 自动安装与启动（免 Mac）
    - 点击、滑动、长按等触摸操作
    - 文本输入
    - App 启动/停止
    - 截图与 OCR
    - 元素定位与操作
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
        self._wda_bundle_id: Optional[str] = None
        self._relay_process: Optional[subprocess.Popen] = None
        self._wda_process: Optional[subprocess.Popen] = None
        self._screen_w = 0
        self._screen_h = 0

        # 设置全局 TIDEVICE_HOME 环境变量，确保所有子进程都能继承
        self._setup_tidevice_env()
        self._ensure_tidevice_dirs()
        self._check_connection()
        self._init_screen_size()

    def _setup_tidevice_env(self):
        """设置 tidevice 环境变量，避免权限问题"""
        tidevice_home = config.TIDEVICE_DIR
        os.makedirs(tidevice_home, exist_ok=True)
        os.makedirs(os.path.join(tidevice_home, "ssl"), exist_ok=True)
        os.environ['TIDEVICE_HOME'] = tidevice_home
        logger.info(f"设置 TIDEVICE_HOME 环境变量: {tidevice_home}")

    # ========== 设备连接与信息 ==========

    def _ensure_tidevice_dirs(self):
        """确保 tidevice 所需目录存在（跨平台支持）"""
        tidevice_dir = config.TIDEVICE_DIR
        ssl_dir = os.path.join(tidevice_dir, "ssl")
        device_support_dir = os.path.join(tidevice_dir, "device-support")
        os.makedirs(ssl_dir, exist_ok=True)
        os.makedirs(device_support_dir, exist_ok=True)

    def _get_tidevice_cmd(self) -> List[str]:
        """获取 tidevice 命令路径"""
        tidevice_path = shutil.which("tidevice") or "/Users/gzt/Library/Python/3.8/bin/tidevice"
        return [tidevice_path, "-u", self.udid]

    def _run(self, args: List[str], timeout: int = 10, env: Dict[str, str] = None) -> Tuple[bool, str]:
        """执行 tidevice 命令"""
        cmd = self._get_tidevice_cmd() + args
        
        try:
            process_env = os.environ.copy()
            # 强制设置 TIDEVICE_HOME 到项目目录，避免权限问题
            tidevice_home = config.TIDEVICE_DIR
            os.makedirs(tidevice_home, exist_ok=True)
            os.makedirs(os.path.join(tidevice_home, "ssl"), exist_ok=True)
            os.makedirs(os.path.join(tidevice_home, "device-support"), exist_ok=True)
            process_env['TIDEVICE_HOME'] = tidevice_home
            # 移除可能存在的旧环境变量
            if 'HOME' in process_env:
                # 通过修改 tidevice 源码路径来强制使用新目录
                import tidevice._device as device_module
                original_ssl_path = device_module.Device.ssl_pemfile_path.fget
                def patched_ssl_path(self):
                    ssl_dir = os.path.join(tidevice_home, "ssl")
                    os.makedirs(ssl_dir, exist_ok=True)
                    return os.path.join(ssl_dir, f"{self.udid}-{self._hash}.pem")
                device_module.Device.ssl_pemfile_path = property(patched_ssl_path)
            
            process_env['PYTHONIOENCODING'] = 'utf-8'
            if env:
                process_env.update(env)

            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
                env=process_env
            )
            output = result.stdout.strip() or result.stderr.strip()
            return result.returncode == 0, output
        except subprocess.TimeoutExpired:
            return False, "timeout"
        except Exception as e:
            return False, str(e)

    def _check_connection(self) -> bool:
        """检查设备是否连接"""
        ok, out = self._run(["info"], timeout=5)
        self.connected = ok
        return ok

    def get_info(self) -> dict:
        """获取设备基本信息"""
        ok, out = self._run(["info"], timeout=10)
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
            ok, _ = self._run(["info"], timeout=3)
            self.connected = ok
            return ok
        except Exception:
            pass
        self.connected = False
        return False

    def _init_screen_size(self):
        """初始化屏幕尺寸"""
        try:
            ok, out = self._run(["info"], timeout=3)
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

    def ensure_wda_ready(self) -> bool:
        """确保 WDA 已准备就绪（启动 wdaproxy）"""
        if self._wda_ready:
            return True

        logger.info(f"正在准备 WDA 环境...")
        
        # 步骤1：检查 WDA 是否已安装
        if not self._is_wda_installed():
            logger.error("❌ WDA 未安装在设备上！")
            logger.error("请使用以下方法之一安装 WDA：")
            logger.error("1. 使用 Mac + Xcode 编译并安装 WDA")
            logger.error("2. 使用已签名的 WDA.ipa 文件安装")
            logger.error("   命令: tidevice install /path/to/WebDriverAgentRunner.ipa")
            return False

        # 步骤2：启动 WDA 服务（使用 wdaproxy）
        if not self._start_wda():
            logger.error("WDA 启动失败")
            return False

        # 步骤3：创建 session
        if not self._create_wda_session():
            logger.error("WDA Session 创建失败")
            return False

        logger.info("WDA 环境准备完成")
        return True

    def _is_wda_installed(self) -> bool:
        """检查 WDA 是否已安装（支持多种 Bundle ID）"""
        ok, out = self._run(["applist"], timeout=10)
        if ok and out:
            try:
                apps = json.loads(out)
                for app in apps:
                    bundle_id = app.get("bundle_id", "")
                    # 检查是否为 WDA（支持多种签名方式）
                    if "WebDriverAgent" in bundle_id and ("xctrunner" in bundle_id.lower() or "Runner" in bundle_id):
                        self._wda_bundle_id = bundle_id
                        logger.info(f"发现 WDA 已安装: {bundle_id}")
                        return True
            except Exception:
                pass
        return False

    def _install_wda(self) -> bool:
        """自动安装 WDA（使用 tidevice）"""
        logger.info("使用 tidevice 安装 WDA...")
        ok, out = self._run(["wda", "install"], timeout=60)
        if ok:
            logger.info("WDA 安装成功")
            return True
        logger.warning(f"WDA 安装失败: {out}")
        return False

    def _start_relay(self):
        """启动 USB 端口转发"""
        if self._relay_process:
            try:
                self._relay_process.terminate()
                self._relay_process.wait(timeout=3)
            except Exception:
                pass

        try:
            cmd = self._get_tidevice_cmd() + ["relay", str(self.WDA_PORT), str(self.WDA_PORT)]
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'

            self._relay_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env
            )
            logger.info(f"WDA 端口转发已启动: {self.WDA_PORT}")
        except Exception as e:
            logger.warning(f"启动端口转发失败: {e}")

    def _start_wda(self) -> bool:
        """启动 WDA 服务（使用 wdaproxy，支持指定 Bundle ID）"""
        if self._wda_process:
            try:
                self._wda_process.terminate()
                self._wda_process.wait(timeout=3)
            except Exception:
                pass

        try:
            # 构建命令（支持指定 WDA Bundle ID）
            cmd = self._get_tidevice_cmd() + ["wdaproxy", "-p", str(self.WDA_PORT)]
            if self._wda_bundle_id:
                cmd += ["-B", self._wda_bundle_id]
            
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            # 设置 TIDEVICE_HOME 避免权限问题
            env['TIDEVICE_HOME'] = config.TIDEVICE_DIR

            self._wda_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True
            )

            logger.info(f"启动 WDA 命令: {' '.join(cmd)}")

            # 等待 WDA 启动
            for i in range(15):
                if self._check_wda_status():
                    logger.info("WDA 服务已启动")
                    return True
                time.sleep(2)
                if self._wda_process.poll() is not None:
                    stdout, stderr = self._wda_process.communicate()
                    logger.error(f"WDA 进程异常退出")
                    if stdout:
                        logger.error(f"STDOUT: {stdout}")
                    if stderr:
                        logger.error(f"STDERR: {stderr}")
                    return False

            return False
        except Exception as e:
            logger.error(f"启动 WDA 失败: {e}")
            return False

    def _check_wda_status(self) -> bool:
        """检查 WDA 是否就绪"""
        try:
            req = urllib.request.Request(
                f"{self._wda_url}/status",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return True
        except Exception:
            return False

    def _create_wda_session(self) -> bool:
        """创建 WDA Session"""
        for i in range(5):
            try:
                req_body = json.dumps({
                    "capabilities": {
                        "platformName": "iOS",
                        "automationName": "XCUITest",
                        "udid": self.udid,
                        "noReset": True
                    }
                }).encode()
                req = urllib.request.Request(
                    f"{self._wda_url}/session",
                    data=req_body,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
                    session_id = data.get("sessionId")
                    if session_id:
                        self._wda_session_id = session_id
                        self._wda_ready = True
                        logger.info(f"WDA Session 已创建: {session_id[:8]}...")
                        return True
            except urllib.error.HTTPError as e:
                if e.code == 400:
                    # Session 可能已存在，尝试获取
                    return self._get_existing_session()
            except Exception as e:
                logger.debug(f"创建 Session 失败 ({i+1}/5): {e}")
            time.sleep(2)
        return False

    def _get_existing_session(self) -> bool:
        """获取已存在的 Session"""
        try:
            req = urllib.request.Request(f"{self._wda_url}/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                session_id = data.get("sessionId")
                if session_id:
                    self._wda_session_id = session_id
                    self._wda_ready = True
                    logger.info(f"使用已存在的 WDA Session: {session_id[:8]}...")
                    return True
        except Exception:
            pass
        return False

    def _wda_request(self, method: str, path: str, data: dict = None) -> Tuple[bool, dict]:
        """发送 WDA HTTP 请求"""
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

    # ========== 元素定位 ==========

    def find_element(self, by: str, value: str) -> Optional[str]:
        """查找元素"""
        locator_map = {
            "id": "id",
            "name": "name",
            "xpath": "xpath",
            "class": "className",
            "accessibility_id": "accessibilityId",
        }
        
        locator_type = locator_map.get(by.lower(), by)
        payload = {
            "using": locator_type,
            "value": value
        }

        ok, result = self._wda_request("POST", "/element", payload)
        if ok and result.get("value"):
            return result["value"].get("ELEMENT")
        return None

    def find_elements(self, by: str, value: str) -> List[str]:
        """查找多个元素"""
        locator_map = {
            "id": "id",
            "name": "name",
            "xpath": "xpath",
            "class": "className",
            "accessibility_id": "accessibilityId",
        }
        
        locator_type = locator_map.get(by.lower(), by)
        payload = {
            "using": locator_type,
            "value": value
        }

        ok, result = self._wda_request("POST", "/elements", payload)
        if ok and result.get("value"):
            return [item.get("ELEMENT") for item in result["value"]]
        return []

    def click_element(self, element_id: str):
        """点击元素"""
        self._wda_request("POST", f"/element/{element_id}/click", {})

    def send_keys_to_element(self, element_id: str, text: str):
        """向元素输入文本"""
        self._wda_request("POST", f"/element/{element_id}/value", {"value": list(text)})

    def get_element_text(self, element_id: str) -> str:
        """获取元素文本"""
        ok, result = self._wda_request("GET", f"/element/{element_id}/text")
        if ok and result.get("value"):
            return result["value"]
        return ""

    # ========== 触摸操作 ==========

    def can_control(self) -> bool:
        """检查是否可以控制设备"""
        if self._wda_ready:
            return True
        
        # 检查 tidevice 是否可用
        try:
            ok, _ = self._run(["version"], timeout=5)
            if ok:
                return True
        except Exception:
            pass
        return False

    def tap(self, x: int, y: int):
        """点击屏幕坐标"""
        if not self.ensure_wda_ready():
            raise RuntimeError("WDA 未就绪，无法执行点击操作")

        ok, _ = self._wda_request("POST", "/wda/tap/0", {"x": x, "y": y})
        if not ok:
            raise RuntimeError(f"iOS 点击失败: ({x}, {y})")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        """滑动"""
        if not self.ensure_wda_ready():
            raise RuntimeError("WDA 未就绪，无法执行滑动操作")

        ok, _ = self._wda_request("POST", "/wda/dragfromtoforduration", {
            "fromX": x1, "fromY": y1, 
            "toX": x2, "toY": y2,
            "duration": duration_ms / 1000.0
        })
        if not ok:
            raise RuntimeError("iOS 滑动失败")

    def long_press(self, x: int, y: int, duration_ms: int = 1000):
        """长按"""
        if not self.ensure_wda_ready():
            raise RuntimeError("WDA 未就绪，无法执行长按操作")

        ok, _ = self._wda_request("POST", "/wda/dragfromtoforduration", {
            "fromX": x, "fromY": y, 
            "toX": x, "toY": y,
            "duration": duration_ms / 1000.0
        })
        if not ok:
            raise RuntimeError("iOS 长按失败")

    # ========== 输入操作 ==========

    def input_text(self, text: str):
        """输入文本"""
        if not self.ensure_wda_ready():
            raise RuntimeError("WDA 未就绪，无法执行输入操作")

        ok, _ = self._wda_request("POST", "/wda/keys", {"value": list(text)})
        if not ok:
            logger.warning("WDA 输入失败，尝试逐个字符输入")
            for ch in text:
                self._wda_request("POST", "/wda/keys", {"value": [ch]})
                time.sleep(0.05)

    def input_keyevent(self, key: str):
        """发送按键事件"""
        if not self.ensure_wda_ready():
            raise RuntimeError("WDA 未就绪，无法执行按键操作")

        key_actions = {
            "home": "/wda/homescreen",
            "lock": "/wda/lock",
            "unlock": "/wda/unlock",
            "volumeUp": "/wda/volumeUp",
            "volumeDown": "/wda/volumeDown",
        }

        action_path = key_actions.get(key.lower())
        if action_path:
            self._wda_request("POST", action_path, {})
        else:
            # 尝试发送字符按键
            self.input_text(key)

    # ========== 截图 ==========

    def screenshot(self, save_path: str) -> bool:
        """截图并保存"""
        if not self.ensure_wda_ready():
            logger.warning("WDA 未就绪，使用 tidevice 截图")
            return self._tidevice_screenshot(save_path)

        try:
            req = urllib.request.Request(f"{self._wda_url}/screenshot")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                img_b64 = data.get("value", "")
                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    with open(save_path, "wb") as f:
                        f.write(img_bytes)
                    return True
        except Exception as e:
            logger.warning(f"WDA 截图失败: {e}")

        return self._tidevice_screenshot(save_path)

    def _tidevice_screenshot(self, save_path: str) -> bool:
        """使用 tidevice 截图"""
        ok, _ = self._run(["screenshot", save_path], timeout=10)
        return ok

    # ========== 应用管理 ==========

    def start_app(self, bundle_id: str):
        """启动应用（使用 WDA 或 tidevice）"""
        app_name = self._bundle_id_to_app_name(bundle_id)
        logger.info(f"启动应用: {app_name} ({bundle_id})")

        # 首先尝试使用 WDA 启动（不需要开发者镜像）
        if self._is_wda_installed():
            logger.info("WDA 已安装，尝试使用 WDA 启动应用")
            # 先启动 WDA
            if self._start_wda():
                # 使用 WDA 启动应用
                ok, result = self._wda_request("POST", "/wda/launchApp", {"bundleId": bundle_id})
                if ok:
                    logger.info(f"应用 {app_name} 已通过 WDA 启动")
                    return True, f"应用 {app_name} 已启动"
                else:
                    logger.warning(f"WDA 启动应用失败，尝试直接使用 WDA HTTP API")
                    # 尝试直接调用 WDA 的 launchApp 接口（不通过 session）
                    try:
                        req_body = json.dumps({"bundleId": bundle_id}).encode()
                        req = urllib.request.Request(
                            f"{self._wda_url}/wda/launchApp",
                            data=req_body,
                            headers={"Content-Type": "application/json"}
                        )
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            logger.info(f"应用 {app_name} 已通过 WDA HTTP API 启动")
                            return True, f"应用 {app_name} 已启动"
                    except Exception as e:
                        logger.warning(f"WDA HTTP API 启动失败: {e}")

        # 回退到 tidevice launch（需要开发者镜像）
        logger.info("回退到 tidevice launch 方式")
        ok, out = self._run(["launch", bundle_id], timeout=15)
        if ok:
            logger.info(f"应用 {app_name} 已通过 tidevice 启动")
            return True, f"应用 {app_name} 已启动"
        
        logger.error(f"❌ 启动失败: {out}")
        logger.error("💡 可能原因：")
        logger.error("   1. 缺少 iOS 18.5 开发者镜像（公开仓库未提供）")
        logger.error("   2. 网络问题无法下载镜像")
        logger.error("   3. 设备未信任电脑")
        logger.error("💡 解决方案：")
        logger.error("   1. 在 Mac 上安装 Xcode 16+，获取开发者镜像")
        logger.error("   2. 将镜像复制到: /Users/gzt/project/autobot/data/app_data/tidevice/device-support/")
        logger.error("   3. 确保 WDA 已正确安装并在设备上运行")
        return False, f"启动失败: {out}"

    def stop_app(self, bundle_id: str):
        """停止应用"""
        app_name = self._bundle_id_to_app_name(bundle_id)
        logger.info(f"停止应用: {app_name}")

        if self._wda_ready:
            self._wda_request("POST", "/wda/terminateApp", {"bundleId": bundle_id})
        else:
            self._run(["kill", bundle_id], timeout=10)

    def get_current_activity(self) -> str:
        """获取当前前台应用"""
        if self._wda_ready:
            ok, result = self._wda_request("GET", "/wda/activeAppInfo")
            if ok and result.get("value"):
                return result["value"].get("bundleId", "")
        return ""

    def is_app_foreground(self, bundle_id: str) -> bool:
        """判断应用是否在前台"""
        current_app = self.get_current_activity()
        return current_app == bundle_id

    # ========== 系统操作 ==========

    def press_home(self):
        """按 Home 键"""
        if self._wda_ready:
            self._wda_request("POST", "/wda/homescreen", {})

    def press_back(self):
        """按返回键（iOS 使用手势返回）"""
        w, h = self.get_screen_size()
        self.swipe(20, h // 2, w - 20, h // 2)

    def press_menu(self):
        """按菜单键（iOS 使用手势）"""
        w, h = self.get_screen_size()
        self.swipe(w // 2, h - 20, w // 2, 20)

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

    # ========== 清理资源 ==========

    def close(self):
        """清理资源"""
        if self._wda_process:
            try:
                self._wda_process.terminate()
                self._wda_process.wait(timeout=3)
            except Exception:
                self._wda_process.kill()
            logger.debug("WDA 进程已关闭")

        if self._relay_process:
            try:
                self._relay_process.terminate()
                self._relay_process.wait(timeout=3)
            except Exception:
                self._relay_process.kill()
            logger.debug("WDA relay 已关闭")

        self._wda_ready = False
        self._wda_session_id = None

    @staticmethod
    def _bundle_id_to_app_name(bundle_id: str) -> str:
        """Bundle ID 转应用名称"""
        bundle_map = {
            "com.tencent.mm": "微信",
            "com.ss.android.ugc.aweme": "抖音",
            "com.xingin.discover": "小红书",
            "com.apple.Preferences": "设置",
            "com.apple.mobilesafari": "Safari",
        }
        return bundle_map.get(bundle_id, bundle_id)