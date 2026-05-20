"""
应用自动化基类
"""
from abc import ABC, abstractmethod
from backend.adb_client import ADBClient
from backend.actions.touch import TouchController
from backend.vision.element_finder import ElementFinder
from backend.config import config


class BaseApp(ABC):
    """应用自动化基类，子类实现具体应用逻辑"""

    package: str = ""
    name: str = ""

    def __init__(self, adb: ADBClient):
        self.adb = adb
        self.touch = TouchController(adb)
        self.finder = ElementFinder(adb)
        self.screen_w, self.screen_h = adb.get_screen_size()

    def start(self):
        """启动应用"""
        self.adb.start_app(self.package)
        self.touch.wait(2.0)

    def stop(self):
        """强制停止应用"""
        self.adb.stop_app(self.package)

    def is_foreground(self) -> bool:
        """判断应用是否在前台"""
        return self.adb.is_app_foreground(self.package)

    def ensure_foreground(self):
        """确保应用在前台，否则启动"""
        if not self.is_foreground():
            self.start()

    @abstractmethod
    def get_actions_schema(self) -> dict:
        """返回应用支持的动作定义，供前端注册任务使用"""
        pass

    @classmethod
    def get_actions_schema_static(cls) -> dict:
        """类级别的动作定义获取（不需要实例化）"""
        return {
            "app": cls.__name__.replace("App", "").lower(),
            "name": getattr(cls, "name", cls.__name__),
            "actions": getattr(cls, "_ACTIONS_SCHEMA", []),
        }