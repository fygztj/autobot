"""
小红书自动化模块
"""
from loguru import logger
from backend.config import config
from backend.apps.base import BaseApp


class XiaohongshuApp(BaseApp):
    package = config.APP_PACKAGES["xiaohongshu"]
    name = "小红书"

    _ACTIONS_SCHEMA = [
        {"type": "start_app", "label": "启动小红书",
         "params": {"package": "com.xingin.xhs"}},
        {"type": "swipe_up", "label": "下一个笔记",
         "params": {"distance": 0.65}},
        {"type": "swipe_up_multiple", "label": "连续浏览笔记",
         "params": {"count": 10, "interval": 3.0}},
        {"type": "tap", "label": "点赞笔记",
         "params": {"x": 0.88, "y": 0.45}},
        {"type": "type", "label": "输入评论",
         "params": {"text": "评论内容"}},
        {"type": "wait", "label": "等待",
         "params": {"seconds": 3.0}},
        {"type": "press_back", "label": "返回", "params": {}},
    ]

    def browse_notes(self, count: int = 15, interval: float = 3.0):
        """
        浏览笔记（推荐流中向上滑动）
        """
        self.ensure_foreground()
        for i in range(count):
            logger.debug(f"浏览笔记 {i+1}/{count}")
            self.touch.swipe_up(distance=0.65)
            self.touch.wait(interval)

    def like_note(self):
        """点赞当前笔记"""
        # 双击屏幕中心偏右
        self.touch.tap(0.88, 0.45)
        self.touch.wait(0.1)
        self.touch.tap(0.88, 0.45)

    def comment_on_note(self, text: str):
        """评论当前笔记"""
        # 点击评论图标
        self.touch.tap(0.88, 0.55)
        self.touch.wait(0.5)
        # 输入评论
        self.touch.tap(0.5, 0.9)
        self.touch.wait(0.3)
        self.touch.type_text(text)
        self.touch.wait(0.2)
        # 发送
        self.touch.tap(0.92, 0.9)
        logger.info(f"已评论: {text}")

    def search_and_browse(self, keyword: str, browse_count: int = 10):
        """搜索关键词并浏览笔记"""
        self.ensure_foreground()
        # 点击搜索
        self.touch.tap(0.92, 0.06)
        self.touch.wait(0.5)
        self.touch.type_text(keyword)
        self.touch.wait(0.5)
        self.touch.press_enter()
        self.touch.wait(1.0)
        self.browse_notes(browse_count)

    def browse_topic(self, topic_name: str, browse_count: int = 10):
        """浏览指定话题"""
        self.search_and_browse(topic_name, browse_count)

    def get_actions_schema(self) -> dict:
        return self.get_actions_schema_static()