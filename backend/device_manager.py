"""
设备管理器 - 管理多台设备连接与生命周期
支持 Android 和 iOS 双平台
"""
import subprocess
import threading
import time
from typing import Dict, List, Optional, Callable
from loguru import logger

from backend.config import config
from backend.adb_client import ADBClient
from backend.ios_client import iOSClient


class Device:
    """表示一台被管理的设备"""

    def __init__(self, identifier: str, os_type: str = "Android"):
        self.serial = identifier
        self.os_type = os_type  # "Android" 或 "iOS"

        if os_type == "Android":
            self.client = ADBClient(identifier)
        else:
            self.client = iOSClient(identifier)

        self.info: dict = {}
        self.is_busy: bool = False  # 是否正在执行任务
        self.current_task_id: Optional[str] = None
        self.connected_at: float = time.time()

    def refresh_info(self):
        """刷新设备信息"""
        self.info = self.client.get_info()
        self.info["os_type"] = self.os_type

    def __repr__(self):
        model = self.info.get("model", "unknown")
        return f"Device({self.os_type}:{model} [{self.serial}])"


class DeviceManager:
    """多设备管理器（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._devices: Dict[str, Device] = {}
        self._lock = threading.Lock()
        self._on_device_connected: Optional[Callable] = None
        self._on_device_disconnected: Optional[Callable] = None
        self._scan_thread: Optional[threading.Thread] = None
        self._running = False
        self._last_info_refresh: Dict[str, float] = {}  # 记录设备信息最后刷新时间

    # ================== 设备发现 ==================

    def _scan_android_devices(self) -> List[str]:
        """扫描 Android 设备"""
        try:
            import shutil
            import os
            
            # 尝试查找 adb 命令
            adb_path = None
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
                logger.debug("未找到 adb 命令，无法扫描 Android 设备")
                return []
            
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True, text=True, timeout=5
            )
            
            lines = result.stdout.strip().split("\n")
            serials = []
            if len(lines) > 1:  # 至少有首行
                for line in lines[1:]:  # 跳过首行 "List of devices"
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        status = parts[1]
                        if status == "device":
                            serials.append(parts[0])
                            logger.info(f"发现 Android 设备: {parts[0]}")
            
            # 只有找到设备时才打印日志
            if serials:
                logger.info(f"扫描到 {len(serials)} 台 Android 设备")
            return serials
        except Exception as e:
            logger.error(f"扫描 Android 设备失败: {e}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            return []

    def _scan_ios_devices(self) -> List[str]:
        """扫描 iOS 设备（跨平台支持）"""
        try:
            import shutil
            import os
            import platform
            
            system = platform.system()
            
            # 根据平台获取 Python 路径
            if system == "Windows":
                python_path = shutil.which("python") or shutil.which("python3")
                # Windows 上 tidevice 通常安装在 Scripts 目录
                user_profile = os.environ.get("USERPROFILE", "")
                python_versions = ["Python313", "Python312", "Python311", "Python310", "Python39"]
                tidevice_module_path = ""
                for py_ver in python_versions:
                    path = os.path.join(user_profile, "AppData", "Roaming", "Python", py_ver, "site-packages")
                    if os.path.exists(path):
                        tidevice_module_path = path
                        break
            else:  # macOS/Linux
                # 使用正确的 Python 路径（tidevice 安装在用户目录的 Python 环境中）
                python_path = "/Users/gzt/Library/Python/3.8/bin/python3"
                if not os.path.exists(python_path):
                    python_path = shutil.which("python3") or shutil.which("python") or "python"
                tidevice_module_path = "/Users/gzt/Library/Python/3.8/lib/python/site-packages"
            
            if not python_path:
                logger.error("未找到 Python 可执行文件")
                return []
            
            env = os.environ.copy()
            env["REQUESTS_CA_BUNDLE"] = ""
            env["CURL_CA_BUNDLE"] = ""
            env["PYTHONIOENCODING"] = "utf-8"
            # 设置 TIDEVICE_HOME 到项目目录，避免权限问题
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(backend_dir)
            env["TIDEVICE_HOME"] = os.path.join(project_dir, "data", "app_data", "tidevice")
            # 添加用户 Python 路径到 PATH
            env["PATH"] = "/Users/gzt/Library/Python/3.8/bin:" + env.get("PATH", "")
            # 设置 PYTHONPATH
            env["PYTHONPATH"] = "/Users/gzt/Library/Python/3.8/lib/python/site-packages:" + env.get("PYTHONPATH", "")
            
            if system == "Windows":
                env["HOME"] = os.environ.get("TEMP", "/tmp")
            else:
                env["HOME"] = "/tmp"
            
            # 直接使用 tidevice 命令
            tidevice_path = shutil.which("tidevice") or "/Users/gzt/Library/Python/3.8/bin/tidevice"
            cmd = [tidevice_path, "list"]

            
            # 使用 errors="replace" 处理编码问题
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, timeout=15,
                env=env,
                encoding="utf-8",
                errors="replace"
            )
            
            # 处理可能为 None 的情况
            stdout = result.stdout.strip() if result.stdout else ""
            stderr = result.stderr.strip() if result.stderr else ""

            
            # 处理可能为 None 的情况
            lines = stdout.split("\n") if stdout else []
            udids = []
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split()
                    if parts and len(parts) >= 2:
                        udid = parts[0]
                        if len(udid) >= 20 and (udid.startswith("0000") or udid.startswith("ffffffff")):
                            udids.append(udid)
            
            return udids
        except Exception as e:
            logger.error(f"扫描 iOS 设备失败: {e}")
            return []

    def scan_devices(self) -> List[Dict[str, str]]:
        """扫描当前连接的所有设备，返回 [{id, os_type}] 列表"""
        devices = []
        android_devices = self._scan_android_devices()
        logger.info(f"Android 设备扫描结果: {len(android_devices)} 台")
        for serial in android_devices:
            devices.append({"id": serial, "os_type": "Android"})
        
        if config.ENABLE_IOS_SCAN:
            ios_devices = self._scan_ios_devices()
            logger.info(f"iOS 设备扫描结果: {len(ios_devices)} 台 - {ios_devices}")
            for udid in ios_devices:
                devices.append({"id": udid, "os_type": "iOS"})
        else:
            logger.info("iOS 设备扫描已禁用")
        
        logger.info(f"总设备数: {len(devices)}")
        return devices

    def refresh(self):
        """刷新设备列表，处理连接/断开"""
        current_devices = self.scan_devices()
        current_ids = {d["id"] for d in current_devices}

        with self._lock:
            known_ids = set(self._devices.keys())
            
            # 检测是否有设备状态变化
            has_changes = False
            
            # 新增设备
            for device_info in current_devices:
                dev_id = device_info["id"]
                dev_os = device_info["os_type"]
                if dev_id not in known_ids:
                    has_changes = True
                    logger.info(f"发现新设备: {dev_os} {dev_id}")
                    try:
                        device = Device(dev_id, dev_os)
                        device.refresh_info()
                        self._devices[dev_id] = device
                        if self._on_device_connected:
                            self._on_device_connected(dev_id)
                    except Exception as e:
                        logger.error(f"添加设备 {dev_id} 失败: {e}")
                        import traceback
                        logger.error(f"异常堆栈: {traceback.format_exc()}")

            # 断开设备
            disconnected_devices = known_ids - current_ids
            for dev_id in disconnected_devices:
                # 二次验证设备是否真的断开
                still_connected = False
                try:
                    if dev_id in self._devices:
                        device = self._devices[dev_id]
                        still_connected = device.client.is_connected()
                        if still_connected:
                            logger.debug(f"设备 {dev_id} 仍在连接，保留")
                        else:
                            has_changes = True
                            logger.info(f"设备 {dev_id} 确认断开")
                except Exception as e:
                    logger.warning(f"验证设备 {dev_id} 连接状态时出错: {e}")
                
                if not still_connected:
                    has_changes = True
                    logger.info(f"删除断开的设备: {dev_id}")
                    del self._devices[dev_id]
                    if self._on_device_disconnected:
                        self._on_device_disconnected(dev_id)
            
            # 对仍保留的设备刷新信息（限制刷新频率）
            import time
            current_time = time.time()
            for dev_id, device in self._devices.items():
                last_refresh = self._last_info_refresh.get(dev_id, 0)
                if current_time - last_refresh >= config.DEVICE_INFO_REFRESH_INTERVAL:
                    try:
                        device.refresh_info()
                        self._last_info_refresh[dev_id] = current_time
                    except Exception as e:
                        logger.debug(f"刷新设备 {dev_id} 信息失败: {e}")

    def start_scan(self):
        """启动持续扫描线程"""
        self._running = True
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._scan_thread.start()

    def stop_scan(self):
        """停止扫描"""
        self._running = False

    def _scan_loop(self):
        """后台扫描循环"""
        while self._running:
            self.refresh()
            time.sleep(config.DEVICE_SCAN_INTERVAL)

    # ================== 设备操作 ==================

    def get_device(self, serial: str) -> Optional[Device]:
        with self._lock:
            return self._devices.get(serial)

    def get_all_devices(self) -> List[Device]:
        with self._lock:
            return list(self._devices.values())

    def get_idle_device(self) -> Optional[Device]:
        """获取一台空闲设备"""
        with self._lock:
            for device in self._devices.values():
                if not device.is_busy and device.info.get("connected"):
                    return device
        return None

    def get_idle_devices(self, count: int = None) -> List[Device]:
        """获取多台空闲设备"""
        with self._lock:
            idle = [d for d in self._devices.values()
                    if not d.is_busy and d.info.get("connected")]
            if count:
                return idle[:count]
            return idle

    def mark_busy(self, serial: str, task_id: str):
        """标记设备为忙碌"""
        device = self.get_device(serial)
        if device:
            device.is_busy = True
            device.current_task_id = task_id

    def mark_idle(self, serial: str):
        """标记设备为空闲"""
        device = self.get_device(serial)
        if device:
            device.is_busy = False
            device.current_task_id = None

    def get_device_count(self) -> int:
        with self._lock:
            return len(self._devices)

    # ================== 回调 ==================

    def on_connected(self, callback: Callable):
        self._on_device_connected = callback

    def on_disconnected(self, callback: Callable):
        self._on_device_disconnected = callback


# 全局单例
device_manager = DeviceManager()