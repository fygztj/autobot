"""
公共工具模块 - 提供随机选择、时间控制等常用功能
可被各平台自动化组件调用
"""
import random
import time
from typing import List, Any, Optional
from loguru import logger


class RandomSelector:
    """随机选择器 - 处理点赞、评论、@等比例选择"""

    def __init__(self):
        pass

    @staticmethod
    def should_do(probability: float) -> bool:
        """
        按概率判断是否执行某个动作
        
        Args:
            probability: 概率值 0.0~1.0，例如 0.1 表示 10% 概率
            
        Returns:
            是否应该执行
        """
        return random.random() < probability

    @staticmethod
    def pick_from_list(items: List[Any], count: int = 1, allow_duplicate: bool = False) -> List[Any]:
        """
        从列表中随机选择指定数量的项
        
        Args:
            items: 待选择的列表
            count: 选择数量
            allow_duplicate: 是否允许重复
            
        Returns:
            选中的项列表
        """
        if not items:
            return []
        
        if allow_duplicate:
            return [random.choice(items) for _ in range(count)]
        else:
            if count >= len(items):
                return items.copy()
            return random.sample(items, count)

    @staticmethod
    def pick_topic(topics: List[str]) -> str:
        """
        从主题词列表中随机选择一个主题
        
        Args:
            topics: 主题词列表
            
        Returns:
            选中的主题词
        """
        if not topics:
            return ""
        return random.choice(topics)


class TimeController:
    """时间控制器 - 处理各种间隔和休眠逻辑"""

    def __init__(self):
        pass

    @staticmethod
    def random_sleep(min_sec: float, max_sec: float, description: str = ""):
        """
        随机休眠一段时间
        
        Args:
            min_sec: 最小秒数
            max_sec: 最大秒数
            description: 日志描述
        """
        sleep_time = random.uniform(min_sec, max_sec)
        if description:
            logger.debug(f"{description}, 休眠 {sleep_time:.2f} 秒")
        else:
            logger.debug(f"休眠 {sleep_time:.2f} 秒")
        time.sleep(sleep_time)

    @staticmethod
    def sleep(seconds: float, description: str = ""):
        """
        精确休眠一段时间
        
        Args:
            seconds: 秒数
            description: 日志描述
        """
        if description:
            logger.debug(f"{description}, 休眠 {seconds:.2f} 秒")
        else:
            logger.debug(f"休眠 {seconds:.2f} 秒")
        time.sleep(seconds)


class CommentGenerator:
    """评论生成器 - 生成简单的评论内容"""

    # 默认评论库（可扩展）
    DEFAULT_COMMENTS = [
        "太棒了！",
        "学到了！",
        "支持支持",
        "666",
        "赞一个",
        "好棒",
        "很有用！",
        "码住了",
        "收藏了",
        "感谢分享",
        "厉害",
        "这个好",
        "已收藏",
        "感谢",
        "学习了",
    ]

    @staticmethod
    def generate(comments: List[str] = None, mention_users: List[str] = None, mention_rate: float = 0.0) -> str:
        """
        生成一条评论
        
        Args:
            comments: 自定义评论库，为空则使用默认
            mention_users: @用户列表
            mention_rate: @概率 0.0~1.0
            
        Returns:
            生成的评论文本
        """
        # 选择评论内容
        comment_list = comments or CommentGenerator.DEFAULT_COMMENTS
        comment = random.choice(comment_list)
        
        # 是否添加 @
        if mention_users and RandomSelector.should_do(mention_rate):
            mention_user = random.choice(mention_users)
            comment = f"@{mention_user} {comment}"
        
        return comment


class ActionCounter:
    """动作计数器 - 用于统计点赞、评论、@次数，控制比例"""

    def __init__(self):
        self.view_count = 0          # 浏览数
        self.like_count = 0          # 点赞数
        self.comment_count = 0       # 评论数
        self.mention_count = 0       # @数

    def reset(self):
        """重置计数器"""
        self.view_count = 0
        self.like_count = 0
        self.comment_count = 0
        self.mention_count = 0

    def increment_view(self) -> int:
        """记录一次浏览，返回当前浏览数"""
        self.view_count += 1
        return self.view_count

    def increment_like(self) -> int:
        """记录一次点赞，返回当前点赞数"""
        self.like_count += 1
        return self.like_count

    def increment_comment(self) -> int:
        """记录一次评论，返回当前评论数"""
        self.comment_count += 1
        return self.comment_count

    def increment_mention(self) -> int:
        """记录一次@，返回当前@数"""
        self.mention_count += 1
        return self.mention_count

    def get_current_rates(self) -> dict:
        """
        获取当前各动作的实际比例
        
        Returns:
            包含各比例的字典
        """
        if self.view_count == 0:
            return {
                "like_rate": 0.0,
                "comment_rate": 0.0,
                "mention_rate": 0.0,
            }
        return {
            "like_rate": self.like_count / self.view_count,
            "comment_rate": self.comment_count / self.view_count,
            "mention_rate": self.mention_count / self.view_count,
        }

    def should_like(self, target_rate: float, tolerance: float = 0.05) -> bool:
        """
        基于目标比例和当前统计，判断是否应该点赞
        
        Args:
            target_rate: 目标点赞率
            tolerance: 允许的误差范围
            
        Returns:
            是否应该点赞
        """
        if self.view_count == 0:
            return RandomSelector.should_do(target_rate)
        
        current_rate = self.like_count / self.view_count
        if current_rate < target_rate - tolerance:
            # 当前比例偏低，增加点赞概率
            adjust_rate = min(target_rate + (target_rate - current_rate), 1.0)
            return RandomSelector.should_do(adjust_rate)
        elif current_rate > target_rate + tolerance:
            # 当前比例偏高，减少点赞概率
            adjust_rate = max(target_rate - (current_rate - target_rate), 0.0)
            return RandomSelector.should_do(adjust_rate)
        else:
            # 在正常范围内，使用目标概率
            return RandomSelector.should_do(target_rate)

    def should_comment(self, target_rate: float, tolerance: float = 0.05) -> bool:
        """基于目标比例判断是否应该评论（类似 should_like）"""
        if self.view_count == 0:
            return RandomSelector.should_do(target_rate)
        
        current_rate = self.comment_count / self.view_count
        if current_rate < target_rate - tolerance:
            adjust_rate = min(target_rate + (target_rate - current_rate), 1.0)
            return RandomSelector.should_do(adjust_rate)
        elif current_rate > target_rate + tolerance:
            adjust_rate = max(target_rate - (current_rate - target_rate), 0.0)
            return RandomSelector.should_do(adjust_rate)
        else:
            return RandomSelector.should_do(target_rate)

    def should_mention(self, target_rate: float, tolerance: float = 0.05) -> bool:
        """基于目标比例判断是否应该@（类似 should_like）"""
        if self.view_count == 0:
            return RandomSelector.should_do(target_rate)
        
        current_rate = self.mention_count / self.view_count
        if current_rate < target_rate - tolerance:
            adjust_rate = min(target_rate + (target_rate - current_rate), 1.0)
            return RandomSelector.should_do(adjust_rate)
        elif current_rate > target_rate + tolerance:
            adjust_rate = max(target_rate - (current_rate - target_rate), 0.0)
            return RandomSelector.should_do(adjust_rate)
        else:
            return RandomSelector.should_do(target_rate)


# 全局单例实例
random_selector = RandomSelector()
time_controller = TimeController()
comment_generator = CommentGenerator()
