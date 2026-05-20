"""
微信自动化模块
"""
from loguru import logger
from backend.config import config
from backend.apps.base import BaseApp


class WeChatApp(BaseApp):
    package = config.APP_PACKAGES["wechat"]
    name = "微信"

    _ACTIONS_SCHEMA = [
        {"type": "start_app", "label": "启动微信",
         "params": {"package": "com.tencent.mm"}},
        {"type": "tap_text", "label": "打开聊天",
         "params": {"text": "联系人名称"}},
        {"type": "type", "label": "发送消息",
         "params": {"text": "消息内容"}},
        {"type": "swipe_up", "label": "向上滑动(浏览)",
         "params": {"distance": 0.5}},
        {"type": "swipe_up_multiple", "label": "连续滑动",
         "params": {"count": 10, "interval": 2.0}},
        {"type": "swipe_to_refresh", "label": "下拉刷新", "params": {}},
        {"type": "press_back", "label": "返回", "params": {}},
        {"type": "wait", "label": "等待",
         "params": {"seconds": 2.0}},
        {"type": "random_wait", "label": "随机等待",
         "params": {"min": 0.5, "max": 2.0}},
    ]

    # ================== 核心操作 ==================

    def open_chat(self, contact_name: str) -> bool:
        """打开与指定联系人的聊天"""
        self.ensure_foreground()
        # 尝试在聊天列表中找到联系人
        if self.finder.click_text(contact_name, timeout=5):
            logger.info(f"已打开与 {contact_name} 的聊天")
            return True
        # 如果没找到，尝试搜索
        if self._search_and_open(contact_name):
            return True
        logger.warning(f"未找到联系人: {contact_name}")
        return False

    def send_message(self, text: str):
        """在当前聊天中发送消息"""
        # 点击输入框（通常位于屏幕底部）
        self.touch.tap(0.5, 0.92)
        self.touch.wait(0.3)
        self.touch.type_text(text)
        self.touch.wait(0.2)
        # 点击发送按钮
        self.touch.tap(0.92, 0.92)
        logger.info(f"已发送消息: {text}")

    def open_moments(self) -> bool:
        """打开朋友圈"""
        self.ensure_foreground()
        # 点击发现 tab
        if self.finder.click_text("发现", timeout=5):
            self.touch.wait(0.5)
            # 点击朋友圈
            if self.finder.click_text("朋友圈", timeout=3):
                return True
        return False

    def browse_moments(self, swipe_count: int = 10, interval: float = 2.0):
        """浏览朋友圈"""
        self.ensure_foreground()
        if not self.open_moments():
            return
        for i in range(swipe_count):
            logger.debug(f"浏览朋友圈 {i+1}/{swipe_count}")
            self.touch.swipe_up(distance=0.6)
            self.touch.wait(interval)

    def send_image(self):
        """在聊天中发送图片（需要先打开聊天）"""
        # 点击 + 号
        self.touch.tap(0.92, 0.92)
        self.touch.wait(0.5)
        # 点击相册
        if self.finder.click_text("相册", timeout=3):
            self.touch.wait(0.5)
            # 点击第一张图片
            self.touch.tap(0.1, 0.25)
            self.touch.wait(0.3)
            # 点击发送
            self.touch.tap(0.92, 0.92)
            logger.info("已发送图片")

    # ================== 辅助方法 ==================

    def _search_and_open(self, keyword: str) -> bool:
        """通过搜索打开联系人/群聊"""
        # 点击顶部搜索
        self.touch.tap(0.92, 0.06)
        self.touch.wait(0.5)
        self.touch.type_text(keyword)
        self.touch.wait(1.0)
        # 点击搜索结果
        self.touch.tap(0.5, 0.18)
        self.touch.wait(0.5)
        return True

    def get_actions_schema(self) -> dict:
        return self.get_actions_schema_static()