"""
高级任务执行器 - 支持主题词浏览、点赞、评论、@等功能
"""
import time
import random
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
        self.is_running = True
        
        # 根据应用类型选择对应的App执行器
        self.app_executor = None
        if config.app == "xiaohongshu":
            self.app_executor = XiaohongshuApp(device.serial)
        elif config.app == "douyin":
            self.app_executor = DouyinApp(device.serial)
        elif config.app == "wechat":
            from backend.apps.wechat import WechatApp
            self.app_executor = WechatApp(device.serial)

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
        try:
            # 点击搜索图标（右上角放大镜）
            self.touch.tap(0.92, 0.06)
            time_controller.random_sleep(0.5, 1.0)
            
            # 输入主题词
            self.touch.type_text(topic)
            time_controller.random_sleep(0.5, 1.0)
            
            # 点击搜索按钮或回车
            self.touch.press_enter()
            time_controller.random_sleep(1.0, 2.0)
            
            # 随机选择一个搜索结果（第1-5个）
            result_index = random_selector.pick_from_list([0, 1, 2, 3, 4], count=1)[0]
            y_pos = 0.25 + result_index * 0.18  # 每个结果大约占0.18高度
            logger.debug(f"选择第 {result_index + 1} 个搜索结果，位置: {y_pos}")
            
            # 点击选中的搜索结果进入详情
            self.touch.tap(0.5, min(y_pos, 0.85))
            time_controller.random_sleep(1.0, 2.0)
            
            logger.info(f"小红书搜索完成: {topic}")
        except Exception as e:
            logger.error(f"小红书搜索失败: {e}")

    def _search_douyin(self, topic: str):
        """搜索抖音"""
        logger.info(f"抖音搜索: {topic}")
        try:
            # 点击搜索图标（右上角放大镜）
            self.touch.tap(0.92, 0.06)
            time_controller.random_sleep(0.5, 1.0)
            
            # 输入主题词
            self.touch.type_text(topic)
            time_controller.random_sleep(0.5, 1.0)
            
            # 点击搜索按钮或回车
            self.touch.press_enter()
            time_controller.random_sleep(1.0, 2.0)
            
            # 随机选择一个搜索结果（第1-5个）
            result_index = random_selector.pick_from_list([0, 1, 2, 3, 4], count=1)[0]
            y_pos = 0.3 + result_index * 0.16  # 每个视频卡片大约占0.16高度
            logger.debug(f"选择第 {result_index + 1} 个搜索结果，位置: {y_pos}")
            
            # 点击选中的视频进入播放
            self.touch.tap(0.5, min(y_pos, 0.85))
            time_controller.random_sleep(1.0, 2.0)
            
            logger.info(f"抖音搜索完成: {topic}")
        except Exception as e:
            logger.error(f"抖音搜索失败: {e}")

    def _search_wechat(self, topic: str):
        """搜索微信"""
        logger.info(f"微信搜索: {topic}")
        try:
            # 点击搜索框（顶部搜索栏）
            self.touch.tap(0.5, 0.08)
            time_controller.random_sleep(0.5, 1.0)
            
            # 输入主题词
            self.touch.type_text(topic)
            time_controller.random_sleep(0.5, 1.0)
            
            # 点击搜索
            self.touch.tap(0.92, 0.08)
            time_controller.random_sleep(1.0, 2.0)
            
            # 随机选择一个搜索结果（第1-4个）
            result_index = random_selector.pick_from_list([0, 1, 2, 3], count=1)[0]
            y_pos = 0.18 + result_index * 0.12  # 每个搜索结果大约占0.12高度
            self.touch.tap(0.5, min(y_pos, 0.6))
            time_controller.random_sleep(0.5, 1.0)
            
            logger.info(f"微信搜索完成: {topic}")
        except Exception as e:
            logger.error(f"微信搜索失败: {e}")

    def _view_and_interact_loop(self):
        """浏览和互动循环"""
        start_time = time.time()
        force_work_seconds = self.config.force_work_min * 60
        force_sleep_seconds = self.config.force_sleep_min * 60
        topic_switch_interval = random_selector.pick_from_list([8, 10, 12, 15], count=1)[0]  # 随机主题切换间隔
        
        while self.is_running:
            # 检查是否达到最大浏览数
            if self.config.max_view_count > 0 and self.counter.view_count >= self.config.max_view_count:
                logger.info(f"已达到最大浏览数 {self.config.max_view_count}，停止任务")
                break
            
            # 检查强制工作/休眠逻辑
            elapsed = time.time() - start_time
            if elapsed >= force_work_seconds:
                logger.info(f"已工作 {self.config.force_work_min} 分钟，强制休眠 {self.config.force_sleep_min} 分钟")
                self._force_sleep(force_sleep_seconds)
                start_time = time.time()
                continue
            
            # 定期切换主题（每浏览一定数量后）
            if self.config.topics and self.counter.view_count % topic_switch_interval == 0:
                self._search_topic()
            
            # 浏览一条内容（随机选择浏览模式）
            self._view_one_item()
            
            # 根据配置执行互动
            self._interact()
            
            # 随机更换主题词（概率10%-20%）
            if self.config.topics and random_selector.random_prob(random.uniform(0.1, 0.2)):
                self._search_topic()
            
            # 随机点击相关推荐（概率15%）
            if random_selector.random_prob(0.15):
                self._click_related_content()
            
            # 浏览间隔（根据内容类型动态调整）
            view_duration = self._calculate_view_duration()
            time_controller.random_sleep(
                view_duration['min'],
                view_duration['max'],
                "浏览间隔"
            )
        
        logger.info(f"任务结束，统计: 浏览 {self.counter.view_count} 条, 点赞 {self.counter.like_count} 次, 评论 {self.counter.comment_count} 次, @ {self.counter.mention_count} 次")

    def _calculate_view_duration(self):
        """根据当前浏览情况计算浏览间隔"""
        base_min = self.config.view_interval.min_sec
        base_max = self.config.view_interval.max_sec
        
        # 如果点赞或评论了，增加停留时间
        if self.counter.like_count > 0 or self.counter.comment_count > 0:
            return {
                'min': base_min * 1.2,
                'max': base_max * 1.5
            }
        
        # 随机增加一些波动
        return {
            'min': base_min * random.uniform(0.8, 1.2),
            'max': base_max * random.uniform(0.8, 1.3)
        }

    def _click_related_content(self):
        """随机点击相关推荐内容"""
        logger.debug("尝试点击相关推荐内容")
        try:
            if self.config.app == "xiaohongshu":
                # 小红书：点击底部相关推荐或话题标签
                positions = [
                    (0.25, 0.9), (0.5, 0.9), (0.75, 0.9),  # 底部推荐
                    (0.15, 0.15), (0.35, 0.15), (0.55, 0.15)  # 顶部话题标签
                ]
                x, y = random.choice(positions)
                self.touch.tap(x, y)
                time_controller.random_sleep(1.0, 2.0)
                logger.debug(f"点击小红书相关内容: ({x}, {y})")
            
            elif self.config.app == "douyin":
                # 抖音：点击评论区推荐或相关视频
                positions = [
                    (0.15, 0.25), (0.15, 0.4), (0.15, 0.55),  # 右侧头像
                ]
                x, y = random.choice(positions)
                self.touch.tap(x, y)
                time_controller.random_sleep(1.0, 2.0)
                logger.debug(f"点击抖音相关内容: ({x}, {y})")
                
        except Exception as e:
            logger.debug(f"点击相关内容失败（可能页面没有相关推荐）: {e}")

    def _force_sleep(self, seconds: float):
        """强制休眠"""
        logger.info(f"开始强制休眠 {seconds/60:.1f} 分钟")
        time_controller.sleep(seconds, "强制休眠")
        # 休眠结束后重新启动应用
        self._start_app()

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
        
        try:
            if self.config.app == "xiaohongshu":
                # 小红书双击屏幕右侧点赞
                self.touch.tap(0.88, 0.45)
                time_controller.random_sleep(0.1, 0.2)
                self.touch.tap(0.88, 0.45)
                logger.debug("小红书点赞完成")
            elif self.config.app == "douyin":
                # 抖音双击屏幕右侧点赞（爱心位置）
                self.touch.tap(0.85, 0.55)
                time_controller.random_sleep(0.1, 0.2)
                self.touch.tap(0.85, 0.55)
                logger.debug("抖音点赞完成")
            elif self.config.app == "wechat":
                # 微信点赞（朋友圈）
                self.touch.tap(0.9, 0.8)
                time_controller.random_sleep(0.3, 0.5)
                self.touch.tap(0.5, 0.4)
                logger.debug("微信点赞完成")
        except Exception as e:
            logger.error(f"点赞失败: {e}")

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
        try:
            # 1. 点击评论按钮（底部右侧评论图标）
            self.touch.tap(0.88, 0.85)
            time_controller.random_sleep(0.5, 1.0)
            
            # 2. 点击输入框
            self.touch.tap(0.3, 0.9)
            time_controller.random_sleep(0.3, 0.5)
            
            # 3. 输入评论
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            
            # 4. 点击发送按钮
            self.touch.tap(0.92, 0.9)
            time_controller.random_sleep(0.5, 1.0)
            
            logger.debug(f"小红书评论完成: {comment}")
        except Exception as e:
            logger.error(f"小红书评论失败: {e}")

    def _comment_douyin(self, comment: str):
        """抖音评论"""
        try:
            # 1. 点击评论按钮（右侧评论图标）
            self.touch.tap(0.85, 0.72)
            time_controller.random_sleep(0.5, 1.0)
            
            # 2. 点击输入框
            self.touch.tap(0.3, 0.92)
            time_controller.random_sleep(0.3, 0.5)
            
            # 3. 输入评论
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            
            # 4. 点击发送按钮
            self.touch.tap(0.92, 0.92)
            time_controller.random_sleep(0.5, 1.0)
            
            logger.debug(f"抖音评论完成: {comment}")
        except Exception as e:
            logger.error(f"抖音评论失败: {e}")

    def _comment_wechat(self, comment: str):
        """微信评论"""
        try:
            # 1. 点击评论按钮
            self.touch.tap(0.85, 0.85)
            time_controller.random_sleep(0.3, 0.5)
            
            # 2. 点击输入框
            self.touch.tap(0.3, 0.95)
            time_controller.random_sleep(0.3, 0.5)
            
            # 3. 输入评论
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            
            # 4. 点击发送按钮
            self.touch.tap(0.92, 0.95)
            time_controller.random_sleep(0.3, 0.5)
            
            logger.debug(f"微信评论完成: {comment}")
        except Exception as e:
            logger.error(f"微信评论失败: {e}")

    def stop(self):
        """停止任务执行"""
        self.is_running = False
        logger.info("高级任务已停止")
