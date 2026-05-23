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

    # ================== 设备发现 ==================

    def _scan_android_devices(self) -> List[str]:
        """扫描 Android 设备"""
        try:
            result = subprocess.run(
                [config.ADB_PATH, "devices"],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.strip().split("\n")[1:]  # 跳过首行 "List of devices"
            serials = []
            for line in lines:
                parts = line.strip().split("\t")
                if len(parts) >= 2 and parts[1] == "device":
                    serials.append(parts[0])
            return serials
        except Exception as e:
            logger.debug(f"扫描 Android 设备失败: {e}")
            return []

    def _scan_ios_devices(self) -> List[str]:
        """扫描 iOS 设备"""
        try:
            import shutil
            import os
            python_path = "/usr/local/bin/python3" if shutil.which("/usr/local/bin/python3") else shutil.which("python3")
            tidevice_module_path = "/Users/gzt/Library/Python/3.8/lib/python/site-packages"
            env = os.environ.copy()
            env["REQUESTS_CA_BUNDLE"] = ""
            env["CURL_CA_BUNDLE"] = ""
            env["HOME"] = "/tmp"
            env["PYTHONPATH"] = tidevice_module_path + os.pathsep + env.get("PYTHONPATH", "")
            result = subprocess.run(
                [python_path, "-m", "tidevice", "list"],
                capture_output=True, text=True, timeout=10,
                env=env
            )
            logger.info(f"tidevice list 返回码: {result.returncode}")
            logger.info(f"tidevice list 标准输出: {repr(result.stdout)}")
            logger.info(f"tidevice list 错误输出: {repr(result.stderr)}")
            lines = result.stdout.strip().split("\n")
            udids = []
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split()
                    if parts and len(parts) >= 2:
                        udid = parts[0]
                        if len(udid) >= 20 and (udid.startswith("0000") or udid.startswith("ffffffff")):
                            udids.append(udid)
            logger.info(f"解析到的 iOS 设备 UDID: {udids}")
            return udids
        except Exception as e:
            logger.error(f"扫描 iOS 设备失败: {e}")
            import traceback
            logger.error(f"异常堆栈: {traceback.format_exc()}")
            return []

    def scan_devices(self) -> List[Dict[str, str]]:
        """扫描当前连接的所有设备，返回 [{id, os_type}] 列表"""
        devices = []
        android_devices = self._scan_android_devices()
        logger.info(f"Android 设备扫描结果: {len(android_devices)} 台")
        for serial in android_devices:
            devices.append({"id": serial, "os_type": "Android"})
        ios_devices = self._scan_ios_devices()
        logger.info(f"iOS 设备扫描结果: {len(ios_devices)} 台 - {ios_devices}")
        for udid in ios_devices:
            devices.append({"id": udid, "os_type": "iOS"})
        logger.info(f"总设备数: {len(devices)}")
        return devices

    def refresh(self):
        """刷新设备列表，处理连接/断开"""
        current_devices = self.scan_devices()
        current_ids = {d["id"] for d in current_devices}

        with self._lock:
            known_ids = set(self._devices.keys())

            # 新增设备
            for device_info in current_devices:
                dev_id = device_info["id"]
                dev_os = device_info["os_type"]
                if dev_id not in known_ids:
                    logger.info(f"发现新设备: {dev_os} {dev_id}")
                    device = Device(dev_id, dev_os)
                    device.refresh_info()
                    self._devices[dev_id] = device
                    if self._on_device_connected:
                        self._on_device_connected(dev_id)

            # 断开设备
            for dev_id in known_ids - current_ids:
                logger.info(f"设备断开: {dev_id}")
                del self._devices[dev_id]
                if self._on_device_disconnected:
                    self._on_device_disconnected(dev_id)

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