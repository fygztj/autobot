"""
高级任务配置模型 - 支持主题词浏览、点赞、评论、@等功能
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class AppType(str, Enum):
    """支持的应用类型"""
    WECHAT = "wechat"
    DOUYIN = "douyin"
    XIAOHONGSHU = "xiaohongshu"


@dataclass
class ActionConfig:
    """动作配置（点赞、评论、@）"""
    enabled: bool = False  # 是否启用
    rate: float = 0.0     # 比例 0.0~1.0


@dataclass
class TimeConfig:
    """时间配置"""
    min_sec: float = 1.0   # 最小间隔秒数
    max_sec: float = 3.0   # 最大间隔秒数


@dataclass
class RotationTask:
    """轮换任务配置"""
    task_id: str           # 任务ID
    duration_min: int = 60 # 执行时长（分钟）


@dataclass
class AdvancedTaskConfig:
    """高级任务配置"""
    # 基础配置
    app: str = ""  # 应用类型
    
    # 主题词配置
    topics: List[str] = field(default_factory=list)  # 主题词列表
    
    # 动作配置
    like_config: ActionConfig = field(default_factory=ActionConfig)
    comment_config: ActionConfig = field(default_factory=ActionConfig)
    mention_config: ActionConfig = field(default_factory=ActionConfig)
    
    # 评论配置
    comment_templates: List[str] = field(default_factory=list)  # 自定义评论模板
    mention_users: List[str] = field(default_factory=list)      # @用户列表
    
    # 时间配置
    view_interval: TimeConfig = field(default_factory=TimeConfig)  # 浏览间隔
    like_interval: TimeConfig = field(default_factory=TimeConfig)  # 点赞间隔
    comment_interval: TimeConfig = field(default_factory=TimeConfig)  # 评论间隔
    mention_interval: TimeConfig = field(default_factory=TimeConfig)  # @间隔
    
    # 强制休眠配置
    force_work_min: int = 60  # 强制工作时间（分钟）
    force_sleep_min: int = 30  # 强制休眠时间（分钟）
    
    # 任务轮换配置
    rotation_enabled: bool = False
    rotation_tasks: List[RotationTask] = field(default_factory=list)
    
    # 其他配置
    max_view_count: int = 100  # 最大浏览数，0表示不限制

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "app": self.app,
            "topics": self.topics,
            "like_config": {
                "enabled": self.like_config.enabled,
                "rate": self.like_config.rate,
            },
            "comment_config": {
                "enabled": self.comment_config.enabled,
                "rate": self.comment_config.rate,
            },
            "mention_config": {
                "enabled": self.mention_config.enabled,
                "rate": self.mention_config.rate,
            },
            "comment_templates": self.comment_templates,
            "mention_users": self.mention_users,
            "view_interval": {
                "min_sec": self.view_interval.min_sec,
                "max_sec": self.view_interval.max_sec,
            },
            "like_interval": {
                "min_sec": self.like_interval.min_sec,
                "max_sec": self.like_interval.max_sec,
            },
            "comment_interval": {
                "min_sec": self.comment_interval.min_sec,
                "max_sec": self.comment_interval.max_sec,
            },
            "mention_interval": {
                "min_sec": self.mention_interval.min_sec,
                "max_sec": self.mention_interval.max_sec,
            },
            "force_work_min": self.force_work_min,
            "force_sleep_min": self.force_sleep_min,
            "rotation_enabled": self.rotation_enabled,
            "rotation_tasks": [
                {"task_id": rt.task_id, "duration_min": rt.duration_min}
                for rt in self.rotation_tasks
            ],
            "max_view_count": self.max_view_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdvancedTaskConfig":
        """从字典创建"""
        config = cls()
        config.app = data.get("app", "")
        config.topics = data.get("topics", [])
        
        like_data = data.get("like_config", {})
        config.like_config = ActionConfig(
            enabled=like_data.get("enabled", False),
            rate=like_data.get("rate", 0.0),
        )
        
        comment_data = data.get("comment_config", {})
        config.comment_config = ActionConfig(
            enabled=comment_data.get("enabled", False),
            rate=comment_data.get("rate", 0.0),
        )
        
        mention_data = data.get("mention_config", {})
        config.mention_config = ActionConfig(
            enabled=mention_data.get("enabled", False),
            rate=mention_data.get("rate", 0.0),
        )
        
        config.comment_templates = data.get("comment_templates", [])
        config.mention_users = data.get("mention_users", [])
        
        view_data = data.get("view_interval", {})
        config.view_interval = TimeConfig(
            min_sec=view_data.get("min_sec", 1.0),
            max_sec=view_data.get("max_sec", 3.0),
        )
        
        like_data = data.get("like_interval", {})
        config.like_interval = TimeConfig(
            min_sec=like_data.get("min_sec", 0.5),
            max_sec=like_data.get("max_sec", 2.0),
        )
        
        comment_data = data.get("comment_interval", {})
        config.comment_interval = TimeConfig(
            min_sec=comment_data.get("min_sec", 2.0),
            max_sec=comment_data.get("max_sec", 5.0),
        )
        
        mention_data = data.get("mention_interval", {})
        config.mention_interval = TimeConfig(
            min_sec=mention_data.get("min_sec", 1.0),
            max_sec=mention_data.get("max_sec", 3.0),
        )
        
        config.force_work_min = data.get("force_work_min", 60)
        config.force_sleep_min = data.get("force_sleep_min", 30)
        
        config.rotation_enabled = data.get("rotation_enabled", False)
        rotation_tasks_data = data.get("rotation_tasks", [])
        config.rotation_tasks = [
            RotationTask(task_id=rt.get("task_id", ""), duration_min=rt.get("duration_min", 60))
            for rt in rotation_tasks_data
        ]
        
        config.max_view_count = data.get("max_view_count", 100)
        
        return config
