"""
任务调度引擎 - 定时任务调度
"""
import threading
from datetime import datetime
from typing import Optional, List
from loguru import logger

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from backend.tasks.task_store import task_store, TaskDefinition
from backend.tasks.task_runner import task_runner
from backend.device_manager import device_manager


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self):
        self._scheduler = BackgroundScheduler()
        self._job_map: dict = {}  # task_id -> job_id
        self._running = False

    def start(self):
        """启动调度器"""
        if self._running:
            return
        self._scheduler.start()
        self._running = True
        # 加载所有启用的定时任务
        self._load_scheduled_tasks()
        logger.info("任务调度器已启动")

    def stop(self):
        """停止调度器"""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("任务调度器已停止")

    def _load_scheduled_tasks(self):
        """从存储中加载所有已启用的定时任务"""
        tasks = task_store.get_all()
        for task in tasks:
            if task.enabled and task.schedule:
                self._schedule_task(task)

    def _schedule_task(self, task: TaskDefinition):
        """为一个任务添加定时调度"""
        schedule = task.schedule
        trigger = self._build_trigger(schedule)
        if trigger is None:
            return

        # 移除旧的任务调度
        self._unschedule_task(task.task_id)

        job = self._scheduler.add_job(
            func=self._execute_scheduled_task,
            trigger=trigger,
            args=[task.task_id],
            id=f"job_{task.task_id}",
            replace_existing=True,
        )
        self._job_map[task.task_id] = job.id
        logger.info(f"已调度任务 [{task.name}], 触发规则: {schedule}")

    def _unschedule_task(self, task_id: str):
        """移除任务的定时调度"""
        job_id = self._job_map.pop(task_id, None)
        if job_id and self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    def _build_trigger(self, schedule: dict):
        """
        根据调度配置构建触发器
        支持:
        - cron: {"type": "cron", "hour": 9, "minute": 0}
        - interval: {"type": "interval", "minutes": 30}
        - date: {"type": "date", "run_date": "2024-01-01T12:00:00"}
        """
        stype = schedule.get("type", "")
        try:
            if stype == "cron":
                return CronTrigger(
                    hour=schedule.get("hour", "*"),
                    minute=schedule.get("minute", "0"),
                    second=schedule.get("second", "0"),
                    day_of_week=schedule.get("day_of_week", "*"),
                    day=schedule.get("day", "*"),
                    month=schedule.get("month", "*"),
                )
            elif stype == "interval":
                return None  # APScheduler 的 interval 需要特殊处理
            elif stype == "date":
                return DateTrigger(run_date=schedule.get("run_date"))
        except Exception as e:
            logger.error(f"构建触发器失败: {e}")
        return None

    def _execute_scheduled_task(self, task_id: str):
        """执行定时触发的任务"""
        task = task_store.get(task_id)
        if task is None or not task.enabled:
            self._unschedule_task(task_id)
            return

        logger.info(f"定时触发任务: [{task.name}]")

        # 获取目标设备
        if task.target_devices:
            devices = task.target_devices
        else:
            # 没有指定设备则使用第一台空闲设备
            idle = device_manager.get_idle_device()
            devices = [idle.serial] if idle else []

        if not devices:
            logger.warning(f"没有可用设备执行任务: [{task.name}]")
            return

        # 在每台目标设备上执行
        for serial in devices:
            thread = threading.Thread(
                target=self._run_task_on_device,
                args=(task, serial),
                daemon=True
            )
            thread.start()

    def _run_task_on_device(self, task: TaskDefinition, serial: str):
        """在指定设备上执行任务并记录结果"""
        success = task_runner.execute(task, serial)
        task_store.record_run(task.task_id, success)

    def run_now(self, task_id: str, serial: str = None) -> bool:
        """立即执行一次任务"""
        task = task_store.get(task_id)
        if task is None:
            return False

        if serial is None:
            device = device_manager.get_idle_device()
            if device is None:
                logger.warning("没有空闲设备")
                return False
            serial = device.serial

        logger.info(f"手动执行任务: [{task.name}] 在设备 {serial}")
        thread = threading.Thread(
            target=self._run_task_on_device,
            args=(task, serial),
            daemon=True
        )
        thread.start()
        return True

    def run_on_all(self, task_id: str) -> bool:
        """在所有空闲设备上执行任务"""
        task = task_store.get(task_id)
        if task is None:
            return False

        devices = device_manager.get_idle_devices()
        if not devices:
            logger.warning("没有空闲设备")
            return False

        logger.info(f"在所有空闲设备上执行任务: [{task.name}] ({len(devices)}台)")
        for device in devices:
            thread = threading.Thread(
                target=self._run_task_on_device,
                args=(task, device.serial),
                daemon=True
            )
            thread.start()
        return True

    def refresh_task(self, task_id: str):
        """刷新单个任务的调度（启用/禁用/修改触发规则后调用）"""
        self._unschedule_task(task_id)
        task = task_store.get(task_id)
        if task and task.enabled and task.schedule:
            self._schedule_task(task)

    def get_jobs(self) -> list:
        """获取所有活跃的调度 job"""
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })
        return jobs


# 全局单例
task_scheduler = TaskScheduler()