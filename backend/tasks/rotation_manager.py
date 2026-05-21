"""
任务轮换管理器 - 支持多个任务轮换执行
"""
import time
import threading
from typing import Dict, List, Optional
from loguru import logger

from backend.tasks.task_store import task_store, TaskDefinition
from backend.tasks.task_runner import task_runner
from backend.device_manager import device_manager


class RotationTaskStatus:
    """轮换任务状态"""
    IDLE = "idle"         # 空闲
    RUNNING = "running"   # 运行中
    SLEEPING = "sleeping" # 休眠中


class RotationTask:
    """单个轮换任务"""

    def __init__(self, task_id: str, duration_min: int):
        self.task_id = task_id
        self.duration_min = duration_min
        self.status = RotationTaskStatus.IDLE
        self.last_run_start: Optional[float] = None
        self.run_count = 0


class TaskRotationManager:
    """任务轮换管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._rotation_tasks: Dict[str, RotationTask] = {}  # task_id -> RotationTask
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._current_index = 0
        self._lock = threading.Lock()

    def add_rotation_task(self, task_id: str, duration_min: int):
        """添加轮换任务"""
        with self._lock:
            self._rotation_tasks[task_id] = RotationTask(task_id, duration_min)
            logger.info(f"添加轮换任务: {task_id}, 时长 {duration_min} 分钟")

    def remove_rotation_task(self, task_id: str):
        """移除轮换任务"""
        with self._lock:
            if task_id in self._rotation_tasks:
                del self._rotation_tasks[task_id]
                logger.info(f"移除轮换任务: {task_id}")

    def get_rotation_tasks(self) -> List[RotationTask]:
        """获取所有轮换任务"""
        with self._lock:
            return list(self._rotation_tasks.values())

    def start(self):
        """启动轮换"""
        if self._running:
            logger.warning("轮换已在运行中")
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._rotation_loop, daemon=True)
        self._thread.start()
        logger.info("任务轮换已启动")

    def stop(self):
        """停止轮换"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("任务轮换已停止")

    def _rotation_loop(self):
        """轮换主循环"""
        logger.info("轮换循环开始")
        
        while self._running:
            with self._lock:
                tasks = list(self._rotation_tasks.values())
            
            if not tasks:
                time.sleep(10)
                continue
            
            # 选择当前任务
            current_task = tasks[self._current_index % len(tasks)]
            task_def = task_store.get(current_task.task_id)
            
            if not task_def:
                logger.warning(f"轮换任务不存在: {current_task.task_id}")
                self._current_index += 1
                time.sleep(5)
                continue
            
            # 执行任务
            logger.info(f"轮换执行任务: {task_def.name} ({current_task.duration_min} 分钟)")
            self._execute_rotation_task(task_def, current_task)
            
            # 切换到下一个任务
            self._current_index += 1
            time.sleep(2)

    def _execute_rotation_task(self, task_def: TaskDefinition, rotation_task: RotationTask):
        """执行单个轮换任务"""
        # 找一个空闲设备
        device = None
        for d in device_manager.get_all_devices():
            if not d.is_busy:
                device = d
                break
        
        if not device:
            logger.warning("没有空闲设备可用于轮换任务")
            time.sleep(30)
            return
        
        # 标记任务状态
        rotation_task.status = RotationTaskStatus.RUNNING
        rotation_task.last_run_start = time.time()
        
        # 启动任务
        try:
            # 在后台线程执行任务
            task_thread = threading.Thread(
                target=task_runner.execute,
                args=(task_def, device.serial),
                daemon=True
            )
            task_thread.start()
            
            # 等待指定时长
            duration_sec = rotation_task.duration_min * 60
            logger.info(f"任务 {task_def.name} 预计执行 {duration_sec} 秒")
            
            # 检查是否应该取消
            start_time = time.time()
            while time.time() - start_time < duration_sec and self._running:
                time.sleep(1)
            
            # 取消任务
            task_runner.cancel(task_def.task_id)
            logger.info(f"任务 {task_def.name} 轮换执行结束")
            
            rotation_task.run_count += 1
            
        except Exception as e:
            logger.error(f"轮换任务执行异常: {e}")
        finally:
            rotation_task.status = RotationTaskStatus.IDLE


# 全局单例
task_rotation_manager = TaskRotationManager()
