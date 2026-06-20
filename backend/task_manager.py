"""
任务模板管理与定时调度系统

功能：
1. 任务模板 CRUD（保存/加载/删除，支持全局和设备级）
2. 定时任务调度器（一次性/每日循环/间隔执行）
3. 设备-任务分配 + 间隔控制 + 休息时间
"""

import json
import os
import uuid
import asyncio
from datetime import datetime, timedelta, time as dtime
from typing import Dict, List, Optional, Any
from loguru import logger

from backend.config import config

# 延迟导入以避免循环依赖
async def _send_log(message: str, level: str = 'info'):
    from backend.api.routes import send_log_to_frontend
    await send_log_to_frontend(message, level)

async def _send_event(message: str):
    from backend.api.routes import send_schedule_event
    await send_schedule_event(message)


# ============================================================
# 操作统计类
# ============================================================

class TaskStatistics:
    """任务操作统计"""
    
    def __init__(self):
        self.stats = {}  # device_id -> task_id -> {counts}
    
    def record_action(self, device_id: str, task_id: str, action: str):
        """记录操作"""
        if device_id not in self.stats:
            self.stats[device_id] = {}
        if task_id not in self.stats[device_id]:
            self.stats[device_id][task_id] = {
                'total_runs': 0,
                'notes_viewed': 0,
                'likes': 0,
                'comments': 0,
                'follows': 0,
                'mentions': 0,
                'videos_skipped': 0,
                'last_run_time': None,
                'total_duration': 0
            }
        
        if action == 'task_start':
            self.stats[device_id][task_id]['total_runs'] += 1
            self.stats[device_id][task_id]['last_run_time'] = datetime.now().isoformat()
        elif action == 'note_view':
            self.stats[device_id][task_id]['notes_viewed'] += 1
        elif action == 'like':
            self.stats[device_id][task_id]['likes'] += 1
        elif action == 'comment':
            self.stats[device_id][task_id]['comments'] += 1
        elif action == 'follow':
            self.stats[device_id][task_id]['follows'] += 1
        elif action == 'mention':
            self.stats[device_id][task_id]['mentions'] += 1
        elif action == 'video_skip':
            self.stats[device_id][task_id]['videos_skipped'] += 1
        elif action.startswith('duration_'):
            try:
                duration = float(action.split('_')[1])
                self.stats[device_id][task_id]['total_duration'] += duration
            except:
                pass
    
    def get_stats(self, device_id: str = None, task_id: str = None):
        """获取统计信息"""
        if device_id and task_id:
            return self.stats.get(device_id, {}).get(task_id, {})
        elif device_id:
            return self.stats.get(device_id, {})
        return self.stats


task_statistics = TaskStatistics()


# ============================================================
# 数据存储路径
# ============================================================

DATA_DIR = os.path.join(config.BASE_DIR, "data")
TEMPLATES_FILE = os.path.join(DATA_DIR, "task_templates.json")
SCHEDULES_FILE = os.path.join(DATA_DIR, "schedules.json")
ACTIONS_LOG_FILE = os.path.join(DATA_DIR, "action_logs.json")


def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_json(path: str, default: Any = None) -> Any:
    _ensure_data_dir()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"加载 {path} 失败: {e}")
    return default if default is not None else {}


def _save_json(path: str, data: Any):
    _ensure_data_dir()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 任务模板管理
# ============================================================

class TaskTemplateManager:
    """管理任务模板（全局 + 设备级）"""

    def __init__(self):
        self._templates: Dict[str, dict] = {}  # id -> template dict
        self._load()

    def _load(self):
        data = _load_json(TEMPLATES_FILE, {})
        self._templates = data.get("templates", {})

    def _save(self):
        _save_json(TEMPLATES_FILE, {"templates": self._templates})

    def list_templates(self, scope: str = "all") -> List[dict]:
        """
        scope: "all" | "global" | "device:{device_id}"
        """
        result = []
        for tid, t in self._templates.items():
            t_scope = t.get("scope", "global")
            if scope == "all" or t_scope == scope or (scope.startswith("device:") and t_scope == scope):
                result.append({**t, "id": tid})
        # 按更新时间倒序
        result.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return result

    def save_template(
        self,
        name: str,
        task_config: dict,
        scope: str = "global",
        device_id: Optional[str] = None,
        template_id: Optional[str] = None,
    ) -> dict:
        """保存或更新模板"""
        now = datetime.now().isoformat()

        if template_id and template_id in self._templates:
            # 更新现有模板
            tpl = self._templates[template_id]
            tpl["name"] = name
            tpl["config"] = task_config
            tpl["updated_at"] = now
            tid = template_id
        else:
            # 新建模板
            tid = template_id or str(uuid.uuid4())[:8]
            actual_scope = scope
            if actual_scope == "device" and device_id:
                actual_scope = f"device:{device_id}"

            self._templates[tid] = {
                "name": name,
                "scope": actual_scope,
                "device_id": device_id if actual_scope.startswith("device:") else None,
                "config": task_config,
                "created_at": now,
                "updated_at": now,
            }

        self._save()
        return {**self._templates[tid], "id": tid}

    def get_template(self, template_id: str) -> Optional[dict]:
        tpl = self._templates.get(template_id)
        if tpl:
            return {**tpl, "id": template_id}
        return None

    def delete_template(self, template_id: str) -> bool:
        if template_id in self._templates:
            del self._templates[template_id]
            self._save()
            return True
        return False

    def copy_to_device(self, template_id: str, device_id: str) -> Optional[dict]:
        """将全局模板挂载到指定设备"""
        tpl = self._templates.get(template_id)
        if not tpl:
            return None
        return self.save_template(
            name=f"{tpl['name']} (设备挂载)",
            task_config=tpl["config"],
            scope="device",
            device_id=device_id,
        )


# ============================================================
# 定时任务调度器
# ============================================================

class ScheduleJob:
    """单个定时任务"""

    def __init__(self, job_data: dict):
        self.id = job_data.get("id", "")
        self.name = job_data.get("name", "")
        self.enabled = job_data.get("enabled", True)

        # 调度类型: once / daily / interval
        self.schedule_type = job_data.get("schedule_type", "once")

        # 一次性: start_time 为 ISO 格式时间
        self.start_time = job_data.get("start_time")

        # 每日模式: 每天在指定时间点执行
        self.daily_times = job_data.get("daily_times", [])  # ["09:00", "14:00"]

        # 间隔模式: 时间范围（每 N~M 分钟重复一次）
        # 兼容旧数据: 如果只有 interval_minutes，则 min 和 max 都设为该值
        self.interval_min_minutes = job_data.get("interval_min_minutes", job_data.get("interval_minutes", 60))
        self.interval_max_minutes = job_data.get("interval_max_minutes", job_data.get("interval_minutes", 60))

        # 最大执行次数 (0 = 无限)
        self.max_executions = job_data.get("max_executions", 0)

        # 已执行次数
        self.execution_count = job_data.get("execution_count", 0)

        # ===== 任务分配列表 =====
        # 每个 assignment 决定: 哪个设备 → 执行哪个模板 → 执行顺序 → 间隔/休息
        self.assignments: List[dict] = job_data.get("assignments", [])

        # 元数据
        self.created_at = job_data.get("created_at", datetime.now().isoformat())
        self.updated_at = job_data.get("updated_at", datetime.now().isoformat())
        self.last_executed_at = job_data.get("last_executed_at")
        self.status = job_data.get("status", "idle")  # idle / running / waiting / completed / error / pending
        self.last_execution_result = job_data.get("last_execution_result", "")
        self.current_device_id = job_data.get("current_device_id", "")
        self.current_template_id = job_data.get("current_template_id", "")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "schedule_type": self.schedule_type,
            "start_time": self.start_time,
            "daily_times": self.daily_times,
            "interval_min_minutes": self.interval_min_minutes,
            "interval_max_minutes": self.interval_max_minutes,
            "max_executions": self.max_executions,
            "execution_count": self.execution_count,
            "assignments": self.assignments,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_executed_at": self.last_executed_at,
            "status": self.status,
            "last_execution_result": self.last_execution_result,
            "current_device_id": self.current_device_id,
            "current_template_id": self.current_template_id,
        }


class TaskScheduler:
    """定时任务调度器 — 管理所有定时任务的触发"""

    def __init__(self, template_manager: TaskTemplateManager, command_sender=None):
        self.template_manager = template_manager
        self.command_sender = command_sender  # 回调函数: async fn(device_id, action, platform, params) -> result
        self._jobs: Dict[str, ScheduleJob] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._load()

    def _load(self):
        data = _load_json(SCHEDULES_FILE, {"jobs": {}})
        for jid, jd in data.get("jobs", {}).items():
            self._jobs[jid] = ScheduleJob(jd)

    def _save(self):
        data = {"jobs": {jid: job.to_dict() for jid, job in self._jobs.items()}}
        _save_json(SCHEDULES_FILE, data)

    # ---- Job CRUD ----

    def list_jobs(self) -> List[dict]:
        result = []
        for jid, job in self._jobs.items():
            d = job.to_dict()
            # 计算下次执行时间
            d["next_run"] = self._calc_next_run(job)
            result.append(d)
        result.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return result

    def get_job(self, job_id: str) -> Optional[dict]:
        job = self._jobs.get(job_id)
        if job:
            d = job.to_dict()
            d["next_run"] = self._calc_next_run(job)
            return d
        return None

    def save_job(self, job_data: dict) -> dict:
        now = datetime.now().isoformat()
        job_id = job_data.get("id") or str(uuid.uuid4())[:8]

        if job_id in self._jobs:
            # 更新
            job = self._jobs[job_id]
            for k, v in job_data.items():
                if k != "id" and hasattr(job, k):
                    setattr(job, k, v)
            job.updated_at = now
        else:
            # 新建
            job_data["created_at"] = now
            job_data["execution_count"] = 0
            job_data["status"] = "idle"
            self._jobs[job_id] = ScheduleJob(job_data)

        self._save()
        return self._jobs[job_id].to_dict()

    def delete_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False

    def toggle_job(self, job_id: str, enabled: bool) -> Optional[dict]:
        job = self._jobs.get(job_id)
        if job:
            job.enabled = enabled
            job.updated_at = datetime.now().isoformat()
            self._save()
            return job.to_dict()
        return None

    # ---- 下次执行时间计算 ----

    def _calc_next_run(self, job: ScheduleJob) -> Optional[str]:
        """计算该 job 的下次执行时间，返回 ISO 字符串或 None"""
        if not job.enabled:
            return None

        # 检查是否已达最大执行次数
        if job.max_executions > 0 and job.execution_count >= job.max_executions:
            return None

        now = datetime.now()

        try:
            if job.schedule_type == "once":
                if job.start_time:
                    st = datetime.fromisoformat(job.start_time)
                    if st > now:
                        return st.isoformat()
                return None

            elif job.schedule_type == "daily":
                if job.daily_times:
                    for dt_str in sorted(job.daily_times):
                        h, m = map(int, dt_str.split(":"))
                        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if target > now:
                            return target.isoformat()
                    # 今天的时间都过了，取明天第一个
                    h, m = map(int, sorted(job.daily_times)[0].split(":"))
                    tomorrow = now + timedelta(days=1)
                    target = tomorrow.replace(hour=h, minute=m, second=0, microsecond=0)
                    return target.isoformat()

            elif job.schedule_type == "interval":
                if job.last_executed_at:
                    last = datetime.fromisoformat(job.last_executed_at)
                    # 使用最小间隔计算下次执行时间
                    next_time = last + timedelta(minutes=job.interval_min_minutes)
                    if next_time > now:
                        return next_time.isoformat()
                    else:
                        # 已过期，立即执行
                        return now.isoformat()
                else:
                    # 从未执行过，立即执行
                    return now.isoformat()
        except Exception as e:
            logger.warning(f"计算下次执行时间失败: {e}")

        return None

    # ---- 调度循环 ----

    async def start(self):
        """启动调度器后台循环"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("📅 定时任务调度器已启动")

    async def stop(self):
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("📅 定时任务调度器已停止")

    async def _loop(self):
        """主调度循环：每 30 秒检查一次是否有任务需要触发"""
        while self._running:
            try:
                await self._check_and_execute()
            except Exception as e:
                logger.error(f"调度器循环异常: {e}")
            await asyncio.sleep(30)  # 每 30 秒检查一次

    async def _check_and_execute(self):
        """检查所有 job，触发到期任务"""
        now = datetime.now()

        for jid, job in list(self._jobs.items()):
            if not job.enabled:
                continue

            # 检查最大执行次数
            if job.max_executions > 0 and job.execution_count >= job.max_executions:
                continue

            should_execute = False

            try:
                if job.schedule_type == "once":
                    if job.start_time:
                        st = datetime.fromisoformat(job.start_time)
                        # 在目标时间的 ±30s 窗口内触发
                        if abs((now - st).total_seconds()) < 60 and job.execution_count == 0:
                            should_execute = True

                elif job.schedule_type == "daily":
                    if job.daily_times:
                        now_time_str = now.strftime("%H:%M")
                        # 在目标时间的 ±30s 窗口内触发，且今天还没执行过
                        today_date = now.strftime("%Y-%m-%d")
                        last_date = ""
                        if job.last_executed_at:
                            last_date = job.last_executed_at[:10]

                        for dt in job.daily_times:
                            # 检查是否在时间窗口内
                            target_h, target_m = map(int, dt.split(":"))
                            diff_minutes = (now.hour * 60 + now.minute) - (target_h * 60 + target_m)
                            if abs(diff_minutes) <= 1 and last_date != today_date:
                                should_execute = True
                                break

                elif job.schedule_type == "interval":
                    if job.last_executed_at:
                        last = datetime.fromisoformat(job.last_executed_at)
                        elapsed = (now - last).total_seconds() / 60
                        # 使用最小间隔判断是否应该执行
                        if elapsed >= job.interval_min_minutes:
                            should_execute = True
                    else:
                        # 首次执行
                        should_execute = True

            except Exception as e:
                logger.warning(f"判断任务 {jid} 是否应执行时出错: {e}")
                continue

            if should_execute:
                logger.info(f"📅 触发定时任务 [{job.name}] (id={jid})")
                await self._execute_job(job)

    async def _execute_job(self, job: ScheduleJob):
        """执行一个定时任务的所有 assignments"""
        job.status = "running"
        job.last_executed_at = datetime.now().isoformat()
        job.last_execution_result = ""
        self._save()

        await _send_event(f"⏰ 定时任务 [{job.name}] 开始执行")
        # 记录任务开始（设备ID在循环中逐个记录）

        try:
            for idx, assign in enumerate(job.assignments):
                device_id = assign.get("device_id", "")
                template_id = assign.get("template_id", "")

                if not device_id or not template_id:
                    logger.warning(f"Assignment {idx} 缺少 device_id 或 template_id，跳过")
                    await _send_log(f"⚠️ Assignment {idx} 缺少 device_id 或 template_id，跳过", "error")
                    continue

                # 获取模板配置
                tpl = self.template_manager.get_template(template_id)
                if not tpl:
                    logger.warning(f"模板 {template_id} 不存在，跳过")
                    await _send_log(f"⚠️ 模板 {template_id} 不存在，跳过", "error")
                    continue

                # 更新当前执行状态
                job.current_device_id = device_id
                job.current_template_id = template_id
                job.status = "waiting"
                self._save()

                await _send_log(f"📱 设备 [{device_id[:8]}] 准备执行任务: {tpl['name']}", "action")

                # 执行前休息
                rest_before_min = assign.get("rest_before_min", 5)
                rest_before_max = assign.get("rest_before_max", 15)
                import random
                rest_sec = random.randint(rest_before_min, rest_before_max)
                logger.info(f"   ⏳ 设备 {device_id[:8]}... 休息 {rest_sec}s 后开始")
                await asyncio.sleep(rest_sec)

                # 发送指令给设备
                if self.command_sender:
                    task_config = tpl.get("config", {})
                    platform = task_config.get("platform", "xiaohongshu")

                    full_config = {
                        "mode": task_config.get("mode", "work"),
                        "platform": platform,
                        "nurture": task_config.get("nurture", {
                            "searchKeywords": [],
                            "useSearch": True,
                            "likeRate": 0.7,
                            "durationRange": {"min": 120, "max": 300},
                            "viewTimeRange": {"min": 3, "max": 8},
                            "restRange": {"min": 2, "max": 5},
                            "keywordRestRange": {"min": 5, "max": 15}
                        }),
                        "work": task_config.get("work", {
                            "mainLine": {
                                "name": "主线",
                                "keywords": [],
                                "topics": [],
                                "probabilities": None,
                                "mentionAccounts": [],
                                "mentionProbability": 0.3,
                                "defaultReplies": ["学到了！感谢分享", "太有用了，已收藏"],
                                "keywordReplies": {},
                                "notesPerRound": 3
                            },
                            "secondaryLine": {
                                "name": "次线",
                                "keywords": [],
                                "topics": [],
                                "probabilities": None,
                                "mentionAccounts": [],
                                "mentionProbability": 0.0,
                                "defaultReplies": ["不错哦", "挺好的"],
                                "keywordReplies": {},
                                "notesPerRound": 2
                            },
                            "alternation": {
                                "mainRounds": 3,
                                "secondaryRounds": 2,
                                "startWith": "main"
                            },
                            "defaultProbabilities": {
                                "likeRate": 0.65,
                                "commentRate": 0.25,
                                "replyRate": 0.15,
                                "collectRate": 0.08,
                                "followRate": 0.03
                            },
                            "viewTimeRange": {"min": 5, "max": 15},
                            "restBetweenNotes": {"min": 3, "max": 8},
                            "restBetweenLines": {"min": 15, "max": 40},
                            "totalDurationMinutes": 0,
                            "browseComments": True,
                            "commentScrollCount": 2
                        })
                    }

                    # 更新状态为正在执行
                    job.status = "running"
                    self._save()

                    logger.info(f"   🚀 向设备 {device_id[:8]} 发送任务: {tpl['name']}")
                    logger.info(f"   📋 platform: {platform}")
                    import json
                    logger.info(f"   📋 完整任务配置JSON: {json.dumps(full_config)}")
                    
                    result = await self.command_sender(
                        device_id=device_id,
                        action="run_task_v3",
                        platform=platform,
                        params={"config": full_config},
                    )

                    if result and hasattr(result, 'success') and result.success:
                        logger.info(f"   ✅ 设备 {device_id[:8]} 任务发送成功")
                        job.last_execution_result = "success"
                        await _send_log(f"✅ 设备 [{device_id[:8]}] 任务发送成功，正在执行...", "success")
                        # 记录动作日志
                        action_logger.log_action(
                            device_id=device_id,
                            task_id=job.id,
                            task_name=job.name,
                            action="task_executed",
                            action_detail=f"模板: {tpl['name']}, 平台: {platform}",
                            success=True,
                            message="任务执行成功"
                        )
                        # 记录搜索关键词日志
                        keywords = full_config.get("nurture", {}).get("searchKeywords", [])
                        if keywords:
                            await _send_log(f"🔍 搜索关键词: {', '.join(keywords)}", "action")
                            action_logger.log_action(
                                device_id=device_id,
                                task_id=job.id,
                                task_name=job.name,
                                action="search_start",
                                action_detail=f"搜索关键词: {', '.join(keywords)}",
                                success=True,
                                message="开始搜索模式"
                            )
                    else:
                        msg = result.message if hasattr(result, 'message') else str(result)
                        logger.warning(f"   ⚠️ 设备 {device_id[:8]} 任务发送失败: {msg}")
                        job.last_execution_result = f"failed: {msg}"
                        # 记录动作日志
                        action_logger.log_action(
                            device_id=device_id,
                            task_id=job.id,
                            task_name=job.name,
                            action="task_executed",
                            action_detail=f"模板: {tpl['name']}, 平台: {platform}",
                            success=False,
                            message=msg
                        )

                # 执行后间隔
                interval_after_min = assign.get("interval_after_min", 0)
                interval_after_max = assign.get("interval_after_max", 0)
                if interval_after_max > 0:
                    interval_sec = random.randint(interval_after_min, interval_after_max)
                    logger.info(f"   😴 任务间间隔 {interval_sec}s")
                    await asyncio.sleep(interval_sec)

            job.execution_count += 1
            job.status = "idle"
            job.current_device_id = ""
            job.current_template_id = ""

            # 检查是否完成
            if job.max_executions > 0 and job.execution_count >= job.max_executions:
                job.status = "completed"
                logger.info(f"✅ 定时任务 [{job.name}] 已完成全部 {job.max_executions} 次执行")

        except Exception as e:
            job.status = "error"
            job.last_execution_result = f"exception: {str(e)}"
            job.current_device_id = ""
            job.current_template_id = ""
            logger.error(f"❌ 定时任务 [{job.name}] 执行异常: {e}")
        finally:
            job.updated_at = datetime.now().isoformat()
            self._save()

    # 手动立即触发
    async def trigger_now(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job:
            return False
        await self._execute_job(job)
        return True


# ============================================================
# 动作日志记录系统
# ============================================================

class ActionLogger:
    """记录每个设备每个任务的所有动作日志"""
    
    def __init__(self):
        self.logs = []
        self._load_logs()
    
    def _load_logs(self):
        try:
            self.logs = _load_json(ACTIONS_LOG_FILE, [])
        except Exception as e:
            logger.warning(f"加载动作日志失败: {e}")
            self.logs = []
    
    def _save_logs(self):
        try:
            _ensure_data_dir()
            with open(ACTIONS_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.logs[-10000:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存动作日志失败: {e}")
    
    def log_action(self, device_id: str, task_id: str, task_name: str, 
                   action: str, action_detail: str = "", success: bool = True, 
                   message: str = ""):
        """
        记录动作日志
        :param device_id: 设备ID
        :param task_id: 任务ID
        :param task_name: 任务名称
        :param action: 动作类型（如：click_note, like, comment, scroll等）
        :param action_detail: 动作详情
        :param success: 是否成功
        :param message: 附加消息
        """
        log_entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "device_id": device_id,
            "task_id": task_id,
            "task_name": task_name,
            "action": action,
            "action_detail": action_detail,
            "success": success,
            "message": message
        }
        self.logs.append(log_entry)
        self._save_logs()
        logger.info(f"📝 动作日志: [{device_id[:8]}] [{task_id}] {action} - {action_detail}")
    
    def get_logs_by_device(self, device_id: str, limit: int = 100) -> list:
        """获取指定设备的动作日志"""
        device_logs = [log for log in self.logs if log["device_id"] == device_id]
        return device_logs[-limit:]
    
    def get_logs_by_task(self, task_id: str, limit: int = 100) -> list:
        """获取指定任务的动作日志"""
        task_logs = [log for log in self.logs if log["task_id"] == task_id]
        return task_logs[-limit:]
    
    def get_all_logs(self, limit: int = 100) -> list:
        """获取所有动作日志"""
        return self.logs[-limit:]
    
    def clear_logs(self):
        """清空所有日志"""
        self.logs = []
        self._save_logs()


# ============================================================
# 全局单例
# ============================================================

template_manager = TaskTemplateManager()
scheduler = TaskScheduler(template_manager)
action_logger = ActionLogger()
