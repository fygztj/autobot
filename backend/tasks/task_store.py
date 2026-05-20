"""
任务存储模块 - 持久化任务定义
"""
import json
import os
import threading
from typing import List, Optional, Dict
from datetime import datetime
from loguru import logger

from backend.config import config


class TaskDefinition:
    """任务定义"""

    def __init__(self, task_id: str = None, **kwargs):
        self.task_id = task_id or f"task_{int(datetime.now().timestamp() * 1000)}"
        self.name: str = kwargs.get("name", "")
        self.description: str = kwargs.get("description", "")
        self.app: str = kwargs.get("app", "")  # wechat / douyin / xiaohongshu
        self.actions: List[dict] = kwargs.get("actions", [])
        self.schedule: dict = kwargs.get("schedule", {})  # {} 表示手动执行
        self.target_devices: List[str] = kwargs.get("target_devices", [])
        self.enabled: bool = kwargs.get("enabled", True)
        self.created_at: str = kwargs.get("created_at", datetime.now().isoformat())
        self.updated_at: str = kwargs.get("updated_at", datetime.now().isoformat())
        self.last_run: Optional[str] = kwargs.get("last_run")
        self.run_count: int = kwargs.get("run_count", 0)
        self.success_count: int = kwargs.get("success_count", 0)
        self.fail_count: int = kwargs.get("fail_count", 0)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "description": self.description,
            "app": self.app,
            "actions": self.actions,
            "schedule": self.schedule,
            "target_devices": self.target_devices,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TaskDefinition":
        return cls(**data)


class TaskStore:
    """任务持久化存储（JSON 文件）"""

    def __init__(self):
        self._file = config.TASK_DB
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskDefinition] = {}
        self._load()

    def _load(self):
        """从文件加载"""
        if os.path.exists(self._file):
            try:
                with open(self._file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._tasks = {
                    tid: TaskDefinition.from_dict(t)
                    for tid, t in data.items()
                }
                logger.info(f"加载了 {len(self._tasks)} 个任务")
            except Exception as e:
                logger.error(f"加载任务文件失败: {e}")
                self._tasks = {}

    def _save(self):
        """保存到文件"""
        os.makedirs(os.path.dirname(self._file), exist_ok=True)
        with self._lock:
            data = {tid: t.to_dict() for tid, t in self._tasks.items()}
            with open(self._file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, task: TaskDefinition) -> TaskDefinition:
        with self._lock:
            self._tasks[task.task_id] = task
            self._save()
        return task

    def get(self, task_id: str) -> Optional[TaskDefinition]:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all(self) -> List[TaskDefinition]:
        with self._lock:
            return list(self._tasks.values())

    def update(self, task: TaskDefinition):
        with self._lock:
            task.updated_at = datetime.now().isoformat()
            self._tasks[task.task_id] = task
            self._save()

    def delete(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                self._save()
                return True
            return False

    def record_run(self, task_id: str, success: bool):
        """记录一次任务执行结果"""
        task = self.get(task_id)
        if task:
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            if success:
                task.success_count += 1
            else:
                task.fail_count += 1
            self.update(task)


# 全局单例
task_store = TaskStore()