"""
抖音自动化模块
"""
from loguru import logger
from backend.config import config
from backend.apps.base import BaseApp


class DouyinApp(BaseApp):
    package = config.APP_PACKAGES["douyin"]
    name = "抖音"

    _ACTIONS_SCHEMA = [
        {"type": "start_app", "label": "启动抖音",
         "params": {"package": "com.ss.android.ugc.aweme"}},
        {"type": "swipe_up", "label": "下一个视频",
         "params": {"distance": 0.7}},
        {"type": "swipe_up_multiple", "label": "连续刷视频",
         "params": {"count": 10, "interval": 3.0}},
        {"type": "tap", "label": "双击点赞",
         "params": {"x": 0.85, "y": 0.55}},
        {"type": "type", "label": "输入评论",
         "params": {"text": "评论内容"}},
        {"type": "wait", "label": "等待",
         "params": {"seconds": 3.0}},
        {"type": "press_back", "label": "返回", "params": {}},
    ]

    def browse_videos(self, count: int = 20, interval: float = 3.0):
        """
        浏览视频（持续向上滑动切换视频）
        """
        self.ensure_foreground()
        for i in range(count):
            logger.debug(f"浏览视频 {i+1}/{count}")
            self.touch.swipe_up(distance=0.7)
            self.touch.wait(interval)

    def like_current_video(self):
        """双击点赞当前视频"""
        self.touch.tap(0.85, 0.55)
        self.touch.wait(0.1)
        self.touch.tap(0.85, 0.55)

    def comment_on_video(self, text: str) -> bool:
        """评论当前视频"""
        # 点击评论按钮（右下角）
        self.touch.tap(0.85, 0.72)
        self.touch.wait(0.5)
        # 点击输入框
        self.touch.tap(0.5, 0.92)
        self.touch.wait(0.3)
        self.touch.type_text(text)
        self.touch.wait(0.2)
        # 发送
        self.touch.tap(0.92, 0.92)
        logger.info(f"已评论: {text}")
        return True

    def search_and_browse(self, keyword: str, browse_count: int = 10):
        """搜索关键词并浏览相关视频"""
        self.ensure_foreground()
        # 点击搜索图标
        self.touch.tap(0.92, 0.06)
        self.touch.wait(0.5)
        # 输入搜索内容
        self.touch.type_text(keyword)
        self.touch.wait(0.5)
        self.touch.press_enter()
        self.touch.wait(1.0)
        # 点击第一个视频
        self.touch.tap(0.5, 0.35)
        self.touch.wait(1.0)
        # 开始浏览
        self.browse_videos(browse_count)

    def open_following_page(self):
        """打开关注页面"""
        self.ensure_foreground()
        self.touch.tap(0.18, 0.06)  # 关注 tab
        self.touch.wait(0.5)

    def browse_live(self, count: int = 5, interval: float = 5.0):
        """浏览直播"""
        self.ensure_foreground()
        # 点击直播 tab (左上第二个)
        self.touch.tap(0.32, 0.06)
        self.touch.wait(1.0)
        for i in range(count):
            self.touch.swipe_up(distance=0.7)
            self.touch.wait(interval)

    def get_actions_schema(self) -> dict:
        return self.get_actions_schema_static()