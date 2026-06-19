"""
REST API 路由
"""
import json
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.config import config
from backend.device_manager import device_manager
from backend.tasks.task_store import task_store, TaskDefinition
from backend.tasks.task_runner import task_runner
from backend.tasks.scheduler import task_scheduler
from backend.tasks.rotation_manager import task_rotation_manager
from backend.api.websocket import ws_manager


# ================== 请求/响应模型 ==================

class TaskCreateRequest(BaseModel):
    name: str
    description: str = ""
    app: str = ""
    actions: List[dict] = []
    schedule: dict = None
    target_devices: List[str] = []
    is_advanced: bool = False
    advanced_config: dict = None


class TaskUpdateRequest(BaseModel):
    name: str = None
    description: str = None
    app: str = None
    actions: List[dict] = None
    schedule: dict = None
    target_devices: List[str] = None
    enabled: bool = None
    is_advanced: bool = None
    advanced_config: dict = None


class RunTaskRequest(BaseModel):
    serial: str = None  # None 表示自动分配


# ================== FastAPI 应用 ==================

app = FastAPI(title="autobot", description="移动端自动化机器人管理平台")

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
import os
static_dir = os.path.join(os.path.dirname(__file__), "..", "web", "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ================== 首页 ==================

@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = os.path.join(
        os.path.dirname(__file__), "..", "web", "templates", "index.html"
    )
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


# ================== 设备 API ==================

@app.get("/api/devices")
async def list_devices():
    """获取所有设备列表"""
    device_manager.refresh()
    devices = []
    for d in device_manager.get_all_devices():
        devices.append({
            "serial": d.serial,
            "os_type": d.os_type,
            "info": d.info,
            "is_busy": d.is_busy,
            "current_task_id": d.current_task_id,
        })
    return {"devices": devices, "total": len(devices)}


@app.post("/api/devices/refresh")
async def refresh_devices():
    """手动刷新设备列表（异步执行）"""
    import threading
    # 在后台线程中执行刷新，避免阻塞请求
    threading.Thread(target=device_manager.refresh, daemon=True).start()
    return {"status": "ok", "message": "设备刷新已启动，请稍后查看设备列表"}


@app.get("/api/devices/{serial}/screenshot")
async def get_screenshot(serial: str):
    """获取设备实时截图"""
    from backend.actions.screenshot import Screenshot
    from fastapi.responses import FileResponse

    device = device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    ss = Screenshot(device.client)
    img = ss.capture()
    if img is None:
        raise HTTPException(status_code=500, detail="截图失败")

    return FileResponse(ss.path, media_type="image/png")


@app.get("/api/devices/{serial}/ocr")
async def get_device_ocr(serial: str):
    """获取设备屏幕 OCR 结果"""
    from backend.actions.screenshot import Screenshot
    from backend.vision.ocr import ocr_engine

    device = device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    ss = Screenshot(device.client)
    img = ss.capture()
    if img is None:
        raise HTTPException(status_code=500, detail="截图失败")

    results = ocr_engine.recognize(img)
    texts = [
        {"text": r.text, "confidence": round(r.confidence, 2),
         "center": list(r.center)}
        for r in results
    ]
    return {"texts": texts, "count": len(texts)}


# ================== 操作 API ==================

@app.post("/api/devices/{serial}/action")
async def device_action(serial: str, action: dict):
    """直接在设备上执行一个操作"""
    device = device_manager.get_device(serial)
    if device is None:
        raise HTTPException(status_code=404, detail="设备不存在")

    from backend.actions.touch import TouchController
    from backend.vision.element_finder import ElementFinder

    client = device.client
    touch = TouchController(client)
    finder = ElementFinder(client)

    action_type = action.get("type", "")
    params = action.get("params", {})

    try:
        # 映射动作类型
        if action_type == "tap":
            touch.tap(params.get("x", 0.5), params.get("y", 0.5))
        elif action_type == "swipe_up":
            touch.swipe_up(params.get("distance", 0.5))
        elif action_type == "swipe_down":
            touch.swipe_down(params.get("distance", 0.5))
        elif action_type == "swipe_left":
            touch.swipe_left(params.get("distance", 0.5))
        elif action_type == "swipe_right":
            touch.swipe_right(params.get("distance", 0.5))
        elif action_type == "type":
            touch.type_text(params.get("text", ""))
        elif action_type == "press_back":
            touch.press_back()
        elif action_type == "press_home":
            touch.press_home()
        elif action_type == "press_enter":
            touch.press_enter()
        elif action_type == "tap_text":
            finder.click_text(params.get("text", ""))
        elif action_type == "start_app":
            if device.os_type == "Android":
                client.start_app(params.get("package", ""))
            else:
                # iOS: 不启动/激活应用，仅检测
                bundle_id = params.get("bundle_id", params.get("package", ""))
                current_app = ""
                try:
                    current_app = client.get_current_activity()
                except Exception:
                    pass
                if current_app == bundle_id:
                    logger.info(f"应用 {bundle_id} 已在前台")
                else:
                    logger.info(f"应用 {bundle_id} 不在前台，请手动打开")
        elif action_type == "stop_app":
            if device.os_type == "Android":
                client.stop_app(params.get("package", ""))
            else:
                client.stop_app(params.get("bundle_id", params.get("package", "")))
        elif action_type == "wait":
            touch.wait(params.get("seconds", 1.0))
        else:
            raise HTTPException(status_code=400, detail=f"不支持的操作: {action_type}")

        return {"status": "ok", "action": action_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ================== 任务 CRUD API ==================

@app.get("/api/tasks")
async def list_tasks():
    """获取所有任务"""
    tasks = task_store.get_all()
    return {
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks),
    }


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """获取单个任务"""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()


@app.post("/api/tasks")
async def create_task(req: TaskCreateRequest):
    """创建新任务"""
    logger.info(f"收到创建任务请求: name={req.name}, is_advanced={req.is_advanced}, actions={len(req.actions)}")
    try:
        task = TaskDefinition(
            name=req.name,
            description=req.description,
            app=req.app,
            actions=req.actions,
            schedule=req.schedule or {},
            target_devices=req.target_devices,
            is_advanced=req.is_advanced,
            advanced_config=req.advanced_config or {},
        )
        task_store.add(task)
        logger.info(f"任务创建成功: task_id={task.task_id}, name={task.name}")
        # 如果有定时规则，添加到调度器
        if task.schedule:
            task_scheduler.refresh_task(task.task_id)
        return task.to_dict()
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")


@app.put("/api/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest):
    """更新任务"""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    if req.name is not None:
        task.name = req.name
    if req.description is not None:
        task.description = req.description
    if req.app is not None:
        task.app = req.app
    if req.actions is not None:
        task.actions = req.actions
    if req.schedule is not None:
        task.schedule = req.schedule
    if req.target_devices is not None:
        task.target_devices = req.target_devices
    if req.enabled is not None:
        task.enabled = req.enabled
    if req.is_advanced is not None:
        task.is_advanced = req.is_advanced
    if req.advanced_config is not None:
        from backend.apps.advanced_config import AdvancedTaskConfig
        task.advanced_config = AdvancedTaskConfig.from_dict(req.advanced_config)

    task_store.update(task)
    task_scheduler.refresh_task(task.task_id)
    return task.to_dict()


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    task_scheduler._unschedule_task(task_id)
    task_runner.cancel(task_id)
    if task_store.delete(task_id):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="任务不存在")


# ================== 任务执行 API ==================

@app.post("/api/tasks/{task_id}/run")
async def run_task(task_id: str, req: RunTaskRequest = None):
    """执行任务"""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")

    serial = req.serial if req and req.serial else None
    ok = task_scheduler.run_now(task_id, serial)
    if not ok:
        raise HTTPException(status_code=400, detail="无法执行任务，请检查设备状态")
    return {"status": "ok"}


@app.post("/api/tasks/{task_id}/run-all")
async def run_task_on_all(task_id: str):
    """在所有空闲设备上执行任务"""
    ok = task_scheduler.run_on_all(task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法执行任务")
    return {"status": "ok"}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消正在执行的任务"""
    task_runner.cancel(task_id)
    return {"status": "ok"}


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务执行状态"""
    status = task_runner.get_status(task_id)
    return {"task_id": task_id, "status": status}


# ================== 应用配置 API ==================

@app.get("/api/apps/schemas")
async def get_app_schemas():
    """获取所有支持应用的动作定义"""
    from backend.apps.wechat import WeChatApp
    from backend.apps.douyin import DouyinApp
    from backend.apps.xiaohongshu import XiaohongshuApp

    schemas = [
        WeChatApp.get_actions_schema_static(),
        DouyinApp.get_actions_schema_static(),
        XiaohongshuApp.get_actions_schema_static(),
    ]
    return {"apps": schemas}


# ================== 任务轮换 API ==================

@app.get("/api/rotation/tasks")
async def get_rotation_tasks():
    """获取轮换任务列表"""
    tasks = task_rotation_manager.get_rotation_tasks()
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "duration_min": t.duration_min,
                "status": t.status,
                "run_count": t.run_count,
            } for t in tasks
        ],
        "is_running": task_rotation_manager._running,
    }


@app.post("/api/rotation/tasks")
async def add_rotation_task(task_id: str, duration_min: int = 60):
    """添加轮换任务"""
    task = task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task_rotation_manager.add_rotation_task(task_id, duration_min)
    return {"status": "ok"}


@app.delete("/api/rotation/tasks/{task_id}")
async def remove_rotation_task(task_id: str):
    """移除轮换任务"""
    task_rotation_manager.remove_rotation_task(task_id)
    return {"status": "ok"}


@app.post("/api/rotation/start")
async def start_rotation():
    """启动任务轮换"""
    task_rotation_manager.start()
    return {"status": "ok"}


@app.post("/api/rotation/stop")
async def stop_rotation():
    """停止任务轮换"""
    task_rotation_manager.stop()
    return {"status": "ok"}


# ================== 系统 API ==================

@app.get("/api/system/status")
async def system_status():
    """获取系统状态"""
    return {
        "devices_total": device_manager.get_device_count(),
        "devices_idle": len(device_manager.get_idle_devices()),
        "tasks_total": len(task_store.get_all()),
        "scheduler_running": task_scheduler._running,
        "ws_connections": ws_manager.active_count,
    }


@app.get("/api/system/jobs")
async def list_jobs():
    """获取调度器活跃任务列表"""
    return {"jobs": task_scheduler.get_jobs()}


@app.post("/api/system/restart")
async def restart_system():
    """重启系统（软重启，无需重启进程）"""
    import threading
    
    def _restart():
        try:
            logger.info("开始系统软重启...")
            
            # 停止任务调度器
            task_scheduler.stop()
            
            # 停止设备扫描
            device_manager.stop_scan()
            
            # 清空设备列表
            device_manager._devices.clear()
            device_manager._last_info_refresh.clear()
            
            # 重新初始化设备扫描
            device_manager.start_scan()
            
            # 重新启动任务调度器
            task_scheduler.start()
            
            logger.info("系统软重启完成")
        except Exception as e:
            logger.error(f"系统重启失败: {e}")
    
    # 在后台线程中执行重启
    threading.Thread(target=_restart, daemon=True).start()
    return {"status": "ok", "message": "系统重启已启动，请稍等几秒后刷新页面"}


# ================== WebSocket ==================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            # 客户端心跳
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ================== App 客户端 API ==================
# iOS 助手 App 通过 WebSocket 连接，PC 前端通过 REST API 管理和下发指令

# 导入 App 客户端 WebSocket 路由（内部注册）
from backend.api.app_ws import router as app_ws_router
app.include_router(app_ws_router)

from backend.app_client import app_device_manager


@app.get("/api/app-devices")
async def list_app_devices():
    """获取所有已连接的 App 设备列表"""
    devices = app_device_manager.list_devices()
    return {
        "devices": [{
            "device_id": d.device_id,
            "device_name": d.device_name,
            "system_version": d.system_version,
            "app_version": d.app_version,
            "model": d.model,
            "status": d.status,
            "platform": d.current_platform,
            "connected_at": d.connected_at.isoformat()
        } for d in devices],
        "total": len(devices)
    }


@app.get("/api/app-devices/{device_id}")
async def get_app_device(device_id: str):
    """获取单个 App 设备信息"""
    device = app_device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未连接")
    return {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "system_version": device.system_version,
        "app_version": device.app_version,
        "model": device.model,
        "status": device.status,
        "platform": device.current_platform,
        "connected_at": device.connected_at.isoformat()
    }


class AppCommandRequest(BaseModel):
    """向 App 设备发送指令"""
    action: str          # like | comment | follow | message | scroll | open_platform | custom_js
    platform: str        # xiaohongshu | douyin | ...
    params: dict = {}    # 额外参数


@app.post("/api/app-devices/{device_id}/command")
async def send_app_command(device_id: str, req: AppCommandRequest):
    """
    向 App 设备发送指令

    可用 action:
    - open_platform: 打开指定平台
      params: { "platform": "xiaohongshu" }
    - scroll: 滚动页面
      params: { "direction": "up|down", "count": 1, "interval": 1.5 }
    - like: 点赞当前帖子
      params: {}
    - comment: 发表评论
      params: { "text": "评论内容" }
    - follow: 关注当前作者
      params: {}
    - message: 发私信
      params: { "text": "消息内容" }
    - custom_js: 执行自定义 JS
      params: { "js": "javascript code" }
    """
    device = app_device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未连接")

    result = await app_device_manager.send_command(
        device_id=device_id,
        action=req.action,
        platform=req.platform,
        params=req.params
    )

    return {
        "command_id": result.command_id,
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "timestamp": result.timestamp.isoformat()
    }


@app.post("/api/app-devices/{device_id}/task")
async def run_app_task(device_id: str, task_config: dict):
    """
    在 App 设备上执行自动化任务

    task_config 示例:
    {
      "platform": "xiaohongshu",
      "operations": [
        { "action": "open_platform", "params": { "platform": "xiaohongshu" } },
        { "action": "scroll", "params": { "direction": "up", "count": 5, "interval": 2 } },
        { "action": "like", "params": {} },
        { "action": "comment", "params": { "text": "很棒！" } }
      ],
      "interval_between_operations": 1.5
    }
    """
    import asyncio
    from datetime import datetime

    device = app_device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未连接")

    platform = task_config.get("platform", "xiaohongshu")
    operations = task_config.get("operations", [])
    interval = float(task_config.get("interval_between_operations", 1.5))

    logger.info(f"[AppTask] 设备 {device_id} 开始执行任务: platform={platform} operations={len(operations)}")

    results = []
    for idx, op in enumerate(operations):
        action = op.get("action", "")
        params = op.get("params", {})

        logger.info(f"[AppTask] 执行 {idx+1}/{len(operations)}: {action}")

        result = await app_device_manager.send_command(
            device_id=device_id,
            action=action,
            platform=platform,
            params=params,
            timeout=60
        )

        results.append({
            "index": idx,
            "action": action,
            "success": result.success,
            "message": result.message,
            "data": result.data
        })

        if idx < len(operations) - 1 and result.success:
            await asyncio.sleep(interval)

    success_count = sum(1 for r in results if r["success"])
    logger.info(f"[AppTask] 任务完成: {success_count}/{len(operations)} 成功")

    return {
        "device_id": device_id,
        "total_operations": len(operations),
        "success_count": success_count,
        "results": results
    }


@app.get("/api/app-devices/platforms")
async def list_supported_platforms():
    """获取当前支持的平台列表"""
    return {
        "platforms": [
            {
                "id": "xiaohongshu",
                "name": "小红书",
                "url": "https://www.xiaohongshu.com",
                "actions": ["open_platform", "scroll", "like", "comment", "follow", "message"]
            }
        ]
    }
