"""
高级任务执行器 - 支持主题词浏览、点赞、评论、@等功能
所有操作均为真实执行，无模拟
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
    """高级任务执行器 - 所有操作真实执行"""

    def __init__(self, device: Device, config: AdvancedTaskConfig):
        self.device = device
        self.config = config
        self.client = device.client
        self.touch = TouchController(self.client)
        self.finder = ElementFinder(self.client)
        self.counter = ActionCounter()
        self.is_running = True

        # 应用执行器
        self.app_executor = None
        if config.app == "xiaohongshu":
            self.app_executor = XiaohongshuApp(device.client)
        elif config.app == "douyin":
            self.app_executor = DouyinApp(device.client)
        elif config.app == "wechat":
            from backend.apps.wechat import WechatApp
            self.app_executor = WechatApp(device.client)

    def execute(self):
        """执行高级任务"""
        logger.info(f"=" * 40)
        logger.info(f"开始执行高级任务: {self.config.app}")
        self.counter.reset()

        # 检查设备是否可以控制
        if self.device.os_type == "iOS":
            if hasattr(self.client, 'ensure_wda_ready'):
                # 先尝试准备 WDA
                if self.client.ensure_wda_ready():
                    self._wda_ready = True
                    logger.info("✅ WDA 环境准备完成")
                else:
                    logger.warning("⚠️  WDA 未就绪，将尝试基本操作（启动应用）")
                    logger.warning("提示：要执行点击、滑动等 UI 操作，请先安装 WebDriverAgent")
                    self._wda_ready = False
            else:
                self._wda_ready = True
        else:
            self._wda_ready = True

        try:
            self._start_app()
            
            # 如果 WDA 未就绪，尝试启动应用
            if not self._wda_ready:
                # 检查应用是否启动成功
                if hasattr(self, '_app_started') and self._app_started:
                    logger.info("WDA 未就绪，已成功启动应用，任务完成（无 UI 操作）")
                else:
                    logger.error("WDA 未就绪且应用启动失败，请检查设备配置")
                    raise RuntimeError("应用启动失败，请检查设备配置")
                return
            
            if self.config.topics:
                self._search_topic()
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
            self._app_started = False
            return

        os_type = self.device.os_type
        result = False
        
        if os_type == "Android":
            result = self.client.start_app(package)
        else:
            result = self.client.start_app(package)
        
        # 检查返回值（iOS客户端返回tuple，Android可能返回bool或None）
        if isinstance(result, tuple):
            self._app_started = result[0]
        else:
            self._app_started = result is not False
        
        if self._app_started:
            logger.info(f"✅ 应用启动成功: {self.config.app}")
        else:
            logger.error(f"❌ 应用启动失败: {self.config.app}")

        time_controller.random_sleep(3, 5, "等待应用启动")

    def _search_topic(self):
        """搜索主题词"""
        topic = random_selector.pick_topic(self.config.topics)
        if not topic:
            return

        logger.info(f"搜索主题: {topic}")

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

            # 点击搜索按钮
            self.touch.press_enter()
            time_controller.random_sleep(1.0, 2.0)

            # 随机选择一个搜索结果
            result_index = random_selector.pick_from_list([0, 1, 2, 3, 4], count=1)[0]
            y_pos = 0.25 + result_index * 0.18
            logger.info(f"选择第 {result_index + 1} 个搜索结果")

            self.touch.tap(0.5, min(y_pos, 0.85))
            time_controller.random_sleep(1.0, 2.0)

            logger.info(f"小红书搜索完成: {topic}")
        except Exception as e:
            logger.error(f"小红书搜索失败: {e}")

    def _search_douyin(self, topic: str):
        """搜索抖音"""
        logger.info(f"抖音搜索: {topic}")
        try:
            self.touch.tap(0.92, 0.06)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.type_text(topic)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.press_enter()
            time_controller.random_sleep(1.0, 2.0)

            result_index = random_selector.pick_from_list([0, 1, 2, 3, 4], count=1)[0]
            y_pos = 0.3 + result_index * 0.16
            logger.info(f"选择第 {result_index + 1} 个视频")

            self.touch.tap(0.5, min(y_pos, 0.85))
            time_controller.random_sleep(1.0, 2.0)
            logger.info(f"抖音搜索完成: {topic}")
        except Exception as e:
            logger.error(f"抖音搜索失败: {e}")

    def _search_wechat(self, topic: str):
        """搜索微信"""
        logger.info(f"微信搜索: {topic}")
        try:
            self.touch.tap(0.5, 0.08)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.type_text(topic)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.92, 0.08)
            time_controller.random_sleep(1.0, 2.0)

            result_index = random_selector.pick_from_list([0, 1, 2, 3], count=1)[0]
            y_pos = 0.18 + result_index * 0.12
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
        topic_switch_interval = random_selector.pick_from_list([8, 10, 12, 15], count=1)[0]

        logger.info(f"开始浏览循环 (最大浏览: {self.config.max_view_count or '无限制'}, 工作: {self.config.force_work_min}分钟)")

        while self.is_running:
            # 检查最大浏览数
            if self.config.max_view_count > 0 and self.counter.view_count >= self.config.max_view_count:
                logger.info(f"达到最大浏览数 {self.config.max_view_count}，停止任务")
                break

            # 检查强制工作/休眠
            elapsed = time.time() - start_time
            if force_work_seconds > 0 and elapsed >= force_work_seconds:
                logger.info(f"已工作 {elapsed/60:.1f} 分钟，强制休眠 {force_sleep_seconds/60:.1f} 分钟")
                self._force_sleep(force_sleep_seconds)
                start_time = time.time()
                continue

            # 定期切换主题
            if self.config.topics and self.counter.view_count > 0 and self.counter.view_count % topic_switch_interval == 0:
                logger.info(f"已浏览 {self.counter.view_count} 条，切换主题")
                self._search_topic()

            # 浏览一条内容
            logger.info(f"[{self.counter.view_count + 1}] 浏览内容...")
            self._view_one_item()

            # 互动操作
            self._interact()

            # 随机更换主题词
            if self.config.topics and random_selector.should_do(random.uniform(0.1, 0.2)):
                logger.info("随机更换主题词")
                self._search_topic()

            # 随机点击相关推荐
            if random_selector.should_do(0.15):
                self._click_related_content()

            # 浏览间隔
            view_duration = self._calculate_view_duration()
            time_controller.random_sleep(
                view_duration['min'], view_duration['max'], "浏览间隔"
            )

        logger.info(f"=" * 40)
        logger.info(f"任务结束 - 浏览: {self.counter.view_count}, 点赞: {self.counter.like_count}, 评论: {self.counter.comment_count}, @: {self.counter.mention_count}")

    def _calculate_view_duration(self):
        """计算浏览间隔"""
        base_min = self.config.view_interval.min_sec
        base_max = self.config.view_interval.max_sec
        if self.counter.like_count > 0 or self.counter.comment_count > 0:
            return {'min': base_min * 1.2, 'max': base_max * 1.5}
        return {'min': base_min * random.uniform(0.8, 1.2), 'max': base_max * random.uniform(0.8, 1.3)}

    def _click_related_content(self):
        """随机点击相关推荐内容"""
        try:
            if self.config.app == "xiaohongshu":
                positions = [(0.25, 0.9), (0.5, 0.9), (0.75, 0.9), (0.15, 0.15), (0.35, 0.15), (0.55, 0.15)]
                x, y = random.choice(positions)
                self.touch.tap(x, y)
                time_controller.random_sleep(1.0, 2.0)
            elif self.config.app == "douyin":
                positions = [(0.15, 0.25), (0.15, 0.4), (0.15, 0.55)]
                x, y = random.choice(positions)
                self.touch.tap(x, y)
                time_controller.random_sleep(1.0, 2.0)
        except Exception as e:
            logger.debug(f"点击相关内容失败: {e}")

    def _force_sleep(self, seconds: float):
        """强制休眠"""
        logger.info(f"强制休眠 {seconds/60:.1f} 分钟")
        time_controller.sleep(seconds, "强制休眠")
        self._start_app()

    def _view_one_item(self):
        """浏览一条内容"""
        self.counter.increment_view()
        self.touch.swipe_up()

    def _interact(self):
        """执行互动（点赞、评论）"""
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

    def _do_like(self):
        """执行点赞"""
        logger.info(f"点赞 (累计: {self.counter.like_count + 1})")
        self.counter.increment_like()

        try:
            if self.config.app == "xiaohongshu":
                # 双击右侧屏幕点赞
                self.touch.tap(0.88, 0.45)
                time_controller.random_sleep(0.1, 0.2)
                self.touch.tap(0.88, 0.45)
                logger.info("小红书点赞完成")
            elif self.config.app == "douyin":
                self.touch.tap(0.85, 0.55)
                time_controller.random_sleep(0.1, 0.2)
                self.touch.tap(0.85, 0.55)
                logger.info("抖音点赞完成")
            elif self.config.app == "wechat":
                self.touch.tap(0.9, 0.8)
                time_controller.random_sleep(0.3, 0.5)
                self.touch.tap(0.5, 0.4)
                logger.info("微信点赞完成")
        except Exception as e:
            logger.error(f"点赞失败: {e}")

    def _do_comment(self):
        """执行评论"""
        logger.info(f"评论 (累计: {self.counter.comment_count + 1})")
        self.counter.increment_comment()

        comment = comment_generator.generate(
            comments=self.config.comment_templates,
            mention_users=self.config.mention_users,
            mention_rate=self.config.mention_config.rate if self.config.mention_config.enabled else 0.0
        )

        if "@" in comment:
            self.counter.increment_mention()

        logger.info(f"评论内容: {comment}")

        if self.config.app == "xiaohongshu":
            self._comment_xiaohongshu(comment)
        elif self.config.app == "douyin":
            self._comment_douyin(comment)
        elif self.config.app == "wechat":
            self._comment_wechat(comment)

    def _comment_xiaohongshu(self, comment: str):
        """小红书评论"""
        try:
            self.touch.tap(0.88, 0.85)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.3, 0.9)
            time_controller.random_sleep(0.3, 0.5)
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.92, 0.9)
            time_controller.random_sleep(0.5, 1.0)
            logger.info("小红书评论完成")
        except Exception as e:
            logger.error(f"小红书评论失败: {e}")

    def _comment_douyin(self, comment: str):
        """抖音评论"""
        try:
            self.touch.tap(0.85, 0.72)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.3, 0.92)
            time_controller.random_sleep(0.3, 0.5)
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.92, 0.92)
            time_controller.random_sleep(0.5, 1.0)
            logger.info("抖音评论完成")
        except Exception as e:
            logger.error(f"抖音评论失败: {e}")

    def _comment_wechat(self, comment: str):
        """微信评论"""
        try:
            self.touch.tap(0.85, 0.85)
            time_controller.random_sleep(0.3, 0.5)
            self.touch.tap(0.3, 0.95)
            time_controller.random_sleep(0.3, 0.5)
            self.touch.type_text(comment)
            time_controller.random_sleep(0.5, 1.0)
            self.touch.tap(0.92, 0.95)
            time_controller.random_sleep(0.3, 0.5)
            logger.info("微信评论完成")
        except Exception as e:
            logger.error(f"微信评论失败: {e}")

    def stop(self):
        """停止任务执行"""
        self.is_running = False
        logger.info("高级任务已停止")