"""
高级任务执行器 - 支持主题词浏览、点赞、评论、@等功能
"""
import time
from typing import Optional
from loguru import logger

from backend.apps.advanced_config import AdvancedTaskConfig
from backend.utils.common import (
    random_selector,
    time_controller,
    comment_generator,
    ActionCounter,
)
from backend.actions.touch import TouchController
from backend.vision.element_finder import ElementFinder
from backend.device_manager import Device
from backend.apps.xiaohongshu import XiaohongshuApp
from backend.apps.douyin import DouyinApp


class AdvancedTaskExecutor:
    """高级任务执行器"""

    def __init__(self, device: Device, config: AdvancedTaskConfig):
        """
        初始化执行器
        
        Args:
            device: 设备对象
            config: 高级任务配置
        """
        self.device = device
        self.config = config
        self.client = device.client
        self.touch = TouchController(self.client)
        self.finder = ElementFinder(self.client)
        self.counter = ActionCounter()
        
        # 根据应用类型选择对应的App执行器
        self.app_executor = None
        if config.app == "xiaohongshu":
            self.app_executor = XiaohongshuApp(device.serial)
        elif config.app == "douyin":
            self.app_executor = DouyinApp(device.serial)
        # TODO: 添加微信支持

    def execute(self):
        """执行高级任务"""
        logger.info(f"开始执行高级任务: {self.config.app}")
        self.counter.reset()
        
        try:
            # 启动应用
            self._start_app()
            
            # 搜索主题
            if self.config.topics:
                self._search_topic()
            
            # 浏览和互动循环
            self._view_and_interact_loop()
            
        except Exception as e:
            logger.error(f"执行高级任务时出错: {e}")
            raise

    def _start_app(self):
        """启动应用"""
        from backend.config import config
        
        logger.info(f"启动应用: {self.config.app}")
        
        package_map = config.APP_PACKAGES
        package = package_map.get(self.config.app)
        
        if not package:
            logger.warning(f"未知应用: {self.config.app}，无法启动")
            return
        
        os_type = self.device.os_type
        
        if os_type == "Android":
            self.client.start_app(package)
        else:  # iOS
            bundle_id = package
            self.client.start_app(bundle_id)
        
        time_controller.random_sleep(3, 5, "等待应用启动")

    def _search_topic(self):
        """搜索主题词"""
        topic = random_selector.pick_topic(self.config.topics)
        if not topic:
            return
        
        logger.info(f"搜索主题: {topic}")
        
        # 根据不同应用执行不同搜索逻辑
        if self.config.app == "xiaohongshu":
            self._search_xiaohongshu(topic)
        elif self.config.app == "douyin":
            self._search_douyin(topic)
        elif self.config.app == "wechat":
            self._search_wechat(topic)

    def _search_xiaohongshu(self, topic: str):
        """搜索小红书"""
        logger.info(f"小红书搜索: {topic}")
        # TODO: 实现小红书搜索逻辑
        # 1. 点击搜索框
        # 2. 输入主题词
        # 3. 点击搜索按钮
        # 4. 等待结果
        time_controller.random_sleep(2, 4)

    def _search_douyin(self, topic: str):
        """搜索抖音"""
        logger.info(f"抖音搜索: {topic}")
        # TODO: 实现抖音搜索逻辑
        time_controller.random_sleep(2, 4)

    def _search_wechat(self, topic: str):
        """搜索微信"""
        logger.info(f"微信搜索: {topic}")
        # TODO: 实现微信搜索逻辑
        time_controller.random_sleep(2, 4)

    def _view_and_interact_loop(self):
        """浏览和互动循环"""
        start_time = time.time()
        force_work_seconds = self.config.force_work_min * 60
        force_sleep_seconds = self.config.force_sleep_min * 60
        
        while True:
            # 检查是否达到最大浏览数
            if self.config.max_view_count > 0 and self.counter.view_count >= self.config.max_view_count:
                logger.info(f"已达到最大浏览数 {self.config.max_view_count}，停止任务")
                break
            
            # 检查强制工作/休眠逻辑
            elapsed = time.time() - start_time
            if elapsed >= force_work_seconds:
                logger.info(f"已工作 {self.config.force_work_min} 分钟，强制休眠 {self.config.force_sleep_min} 分钟")
                time_controller.sleep(force_sleep_seconds, "强制休眠")
                start_time = time.time()
                continue
            
            # 浏览一条内容
            self._view_one_item()
            
            # 根据配置执行互动
            self._interact()
            
            # 浏览间隔
            time_controller.random_sleep(
                self.config.view_interval.min_sec,
                self.config.view_interval.max_sec,
                "浏览间隔"
            )

    def _view_one_item(self):
        """浏览一条内容"""
        logger.debug("浏览一条内容")
        self.counter.increment_view()
        
        # 根据应用执行不同浏览逻辑
        if self.config.app == "xiaohongshu":
            self._view_xiaohongshu_item()
        elif self.config.app == "douyin":
            self._view_douyin_item()
        elif self.config.app == "wechat":
            self._view_wechat_item()

    def _view_xiaohongshu_item(self):
        """浏览小红书单条内容"""
        # 滑动到下一条
        self.touch.swipe_up()

    def _view_douyin_item(self):
        """浏览抖音单条内容"""
        # 滑动到下一条视频
        self.touch.swipe_up()

    def _view_wechat_item(self):
        """浏览微信单条内容"""
        # TODO: 实现微信浏览逻辑
        self.touch.swipe_up()

    def _interact(self):
        """执行互动（点赞、评论、@）"""
        # 点赞
        if self.config.like_config.enabled:
            if self.counter.should_like(self.config.like_config.rate):
                self._do_like()
                time_controller.random_sleep(
                    self.config.like_interval.min_sec,
                    self.config.like_interval.max_sec,
                    "点赞间隔"
                )
        
        # 评论
        if self.config.comment_config.enabled:
            if self.counter.should_comment(self.config.comment_config.rate):
                self._do_comment()
                time_controller.random_sleep(
                    self.config.comment_interval.min_sec,
                    self.config.comment_interval.max_sec,
                    "评论间隔"
                )
        
        # @（包含在评论中）
        if self.config.mention_config.enabled:
            # @是通过评论实现的，这里不需要单独处理
            pass

    def _do_like(self):
        """执行点赞"""
        logger.debug("执行点赞")
        self.counter.increment_like()
        
        if self.config.app == "xiaohongshu":
            # 点击小红书点赞按钮（通常右下角或底部）
            self.touch.tap(0.9, 0.75)  # 相对坐标，可能需要调整
        elif self.config.app == "douyin":
            # 点击抖音点赞按钮（右侧爱心）
            self.touch.tap(0.9, 0.35)  # 相对坐标，可能需要调整
        elif self.config.app == "wechat":
            # TODO: 微信点赞
            pass

    def _do_comment(self):
        """执行评论"""
        logger.debug("执行评论")
        self.counter.increment_comment()
        
        # 生成评论
        comment = comment_generator.generate(
            comments=self.config.comment_templates,
            mention_users=self.config.mention_users,
            mention_rate=self.config.mention_config.rate if self.config.mention_config.enabled else 0.0
        )
        
        if "@" in comment:
            self.counter.increment_mention()
        
        logger.debug(f"评论内容: {comment}")
        
        # 根据应用执行评论
        if self.config.app == "xiaohongshu":
            self._comment_xiaohongshu(comment)
        elif self.config.app == "douyin":
            self._comment_douyin(comment)
        elif self.config.app == "wechat":
            self._comment_wechat(comment)

    def _comment_xiaohongshu(self, comment: str):
        """小红书评论"""
        # 1. 点击评论按钮
        self.touch.tap(0.9, 0.85)
        time_controller.random_sleep(1, 2)
        # 2. 点击输入框
        self.touch.tap(0.5, 0.9)
        time_controller.random_sleep(0.5, 1)
        # 3. 输入评论
        self.touch.type_text(comment)
        time_controller.random_sleep(0.5, 1)
        # 4. 点击发送
        self.touch.tap(0.9, 0.9)

    def _comment_douyin(self, comment: str):
        """抖音评论"""
        # 1. 点击评论按钮
        self.touch.tap(0.9, 0.45)
        time_controller.random_sleep(1, 2)
        # 2. 点击输入框
        self.touch.tap(0.5, 0.9)
        time_controller.random_sleep(0.5, 1)
        # 3. 输入评论
        self.touch.type_text(comment)
        time_controller.random_sleep(0.5, 1)
        # 4. 点击发送
        self.touch.tap(0.9, 0.9)

    def _comment_wechat(self, comment: str):
        """微信评论"""
        # TODO: 实现微信评论
        pass
