"""
AutoBot REST API 路由（仅保留 App WebSocket 自动化系统）
"""
import json
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from backend.config import config
from backend.app_client import app_device_manager
from backend.app_client.models import AppDeviceInfo, AppCommand, AppCommandResult
from backend.task_manager import template_manager, scheduler


# ================ FastAPI 应用 ================
app = FastAPI(title="AutoBot iOS 自动化助手", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ================ Token 认证工具 ================

def verify_token(token: str) -> bool:
    """校验 token。AUTH_TOKEN 为空时跳过校验（局域网模式）"""
    if not config.AUTH_TOKEN:
        return True
    return token == config.AUTH_TOKEN


# ================ 前端 WebSocket 管理器 ================
class _FrontendWSManager:
    """管理前端（浏览器）的 WebSocket 连接，用于推送设备状态"""

    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict):
        for ws in list(self._connections):
            try:
                await ws.send_json(message)
            except Exception:
                pass


frontend_ws = _FrontendWSManager()

async def send_log_to_frontend(message: str, level: str = 'info'):
    """向前端发送日志消息"""
    await frontend_ws.broadcast({
        "type": "log",
        "message": message,
        "level": level
    })

async def send_schedule_event(message: str):
    """向前端发送定时任务事件"""
    await frontend_ws.broadcast({
        "type": "schedule_event",
        "message": message
    })

async def send_frontend_broadcast(message: dict):
    """向前端发送任意广播消息"""
    await frontend_ws.broadcast(message)


# ================ 请求模型 ================
class AppCommandRequest(BaseModel):
    action: str           # open_platform | scroll | like | comment | follow | message | custom_js
    platform: str = ""    # xiaohongshu | douyin
    params: dict = {}


# ================ 静态文件 ================
app.mount("/static", StaticFiles(directory=config.BASE_DIR + "/web/static"), name="static")


# ================ 页面 ================
@app.get("/test", response_class=HTMLResponse)
async def test_page():
    """测试页面 - 验证 JS 是否正常执行"""
    try:
        with open(config.BASE_DIR + "/web/templates/test.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-store"})
    except Exception:
        return HTMLResponse("<h1>Test page not found</h1>")

@app.get("/panel", include_in_schema=False)
@app.get("/", include_in_schema=False)
async def index():
    """管理面板主页"""
    try:
        with open(config.BASE_DIR + "/web/templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), headers={"Cache-Control": "no-store"})
    except Exception as e:
        return HTMLResponse(f"<h1>AutoBot 加载失败: {e}</h1>")


# ================ API ================
@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


# ---------- App 设备管理 ----------

from fastapi import Query, Header


def _check_api_token(token: str = Query(default=None, alias="token"), x_token: str = Header(default=None, alias="X-Auth-Token")):
    """REST API Token 校验（从 query param 或 header 获取）"""
    effective_token = token or x_token
    if not verify_token(effective_token):
        raise HTTPException(status_code=401, detail="Token 无效或未提供")


@app.get("/api/app-devices")
async def list_app_devices(_auth: None = Depends(_check_api_token)):
    """获取所有已连接的 App 设备"""
    devices = app_device_manager.list_devices()
    return {
        "devices": [{
            "device_id": d.device_id,
            "device_name": d.device_name,
            "system_version": d.system_version,
            "app_version": d.app_version,
            "model": d.model,
            "screen_width": d.screen_width,
            "screen_height": d.screen_height,
            "status": d.status,
            "current_platform": d.current_platform,
            "connected_at": d.connected_at.isoformat() if d.connected_at else None,
        } for d in devices]
    }


@app.get("/api/app-devices/{device_id}")
async def get_app_device(device_id: str, _auth: None = Depends(_check_api_token)):
    """获取单个设备信息"""
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
        "current_platform": device.current_platform,
        "connected_at": device.connected_at.isoformat() if device.connected_at else None,
    }


@app.post("/api/app-devices/{device_id}/command")
async def send_app_command(device_id: str, req: AppCommandRequest, _auth: None = Depends(_check_api_token)):
    """向指定设备发送单个指令

    Args:
        device_id: 目标设备 ID
        req: { action, platform, params }

    Actions:
        - open_platform: 打开平台页面
        - scroll: 滚动页面
        - like: 点赞
        - comment: 评论
        - follow: 关注
        - message: 私信
        - custom_js: 自定义 JS
    """
    result = await app_device_manager.send_command(
        device_id=device_id,
        action=req.action,
        platform=req.platform,
        params=req.params,
        timeout=60,
    )

    return {
        "command_id": result.command_id,
        "success": result.success,
        "message": result.message,
        "data": result.data,
        "timestamp": result.timestamp.isoformat() if hasattr(result.timestamp, 'isoformat') else datetime.now().isoformat()
    }


@app.post("/api/app-devices/{device_id}/task")
async def run_app_task(device_id: str, task_config: Dict[str, Any], _auth: None = Depends(_check_api_token)):
    """在 App 设备上执行复合任务

    task_config 示例:
    {
      "platform": "xiaohongshu",
      "operations": [
        { "action": "open_platform", "params": {} },
        { "action": "scroll", "params": {"direction": "up", "count": 3, "interval": 1.5} },
        { "action": "like", "params": {} }
      ],
      "interval_between_operations": 1.0
    }
    """
    device = app_device_manager.get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未连接")

    platform = task_config.get("platform", "")
    operations = task_config.get("operations", [])
    interval = float(task_config.get("interval_between_operations", 1.0))

    logger.info(f"[Task] 设备 {device_id} 执行任务: platform={platform}, operations={len(operations)}")

    results = []
    for idx, op in enumerate(operations):
        action = op.get("action", "")
        params = op.get("params", {})

        logger.info(f"[Task] {idx+1}/{len(operations)}: {action}")

        result = await app_device_manager.send_command(
            device_id=device_id,
            action=action,
            platform=platform,
            params=params,
            timeout=60,
        )

        results.append({
            "index": idx,
            "action": action,
            "success": result.success,
            "message": result.message,
        })

        if idx < len(operations) - 1 and interval > 0:
            await asyncio.sleep(interval)

    success_count = sum(1 for r in results if r["success"])
    logger.info(f"[Task] 完成: {success_count}/{len(operations)} 成功")

    return {
        "device_id": device_id,
        "total_operations": len(operations),
        "success_count": success_count,
        "results": results,
    }


# ================ WebSocket ================

@app.websocket("/ws/app/connect")
async def app_websocket_endpoint(websocket: WebSocket):
    """iOS 助手 App WebSocket 连接端点"""
    await websocket.accept()
    device_id = None

    try:
        # 等待注册消息
        register_msg = await websocket.receive_json()
        msg_type = register_msg.get("type", "")

        if msg_type != "register":
            await websocket.send_json({"type": "error", "message": "第一条消息必须是 'register'"})
            await websocket.close()
            return

        # ===== Token 校验 =====
        client_token = register_msg.get("token", "")
        if not verify_token(client_token):
            logger.warning(f"[AppWS] Token 校验失败，拒绝连接")
            await websocket.send_json({"type": "error", "message": "Token 无效，请在设置中配置正确的连接 Token"})
            await websocket.close(code=4001)
            return

        # 注册设备
        device_info = AppDeviceInfo(
            device_id=register_msg.get("device_id", ""),
            device_name=register_msg.get("device_name", "Unknown"),
            system_version=register_msg.get("system_version", ""),
            app_version=register_msg.get("app_version", ""),
            model=register_msg.get("model", ""),
            screen_width=register_msg.get("screen_width", 0),
            screen_height=register_msg.get("screen_height", 0),
        )
        device_id = device_info.device_id

        if not device_id:
            await websocket.send_json({"type": "error", "message": "device_id 必填"})
            await websocket.close()
            return

        # 添加到管理器
        await app_device_manager.connect(websocket, device_info)

        # 回复注册成功
        await websocket.send_json({
            "type": "welcome",
            "server_time": datetime.now().isoformat(),
            "device_id": device_id,
        })

        # 推送设备列表到前端
        await _push_device_list_to_frontend()

        logger.info(f"[AppWS] 设备已注册: {device_id} ({device_info.device_name})")

        # 消息循环
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                continue
            except WebSocketDisconnect:
                break

            msg_type = data.get("type", "")

            if msg_type == "result":
                # App 返回指令执行结果
                await app_device_manager.handle_result(data)

            elif msg_type == "heartbeat":
                # 心跳
                app_device_manager.update_heartbeat(device_id)
                await websocket.send_json({"type": "pong", "server_time": datetime.now().isoformat()})

            elif msg_type == "log":
                # App 上报日志
                logger.info(f"[AppLog:{device_id}] {data.get('message', '')}")

            elif msg_type == "status":
                # App 主动上报状态
                if device_id in app_device_manager._devices:
                    ws, info = app_device_manager._devices[device_id]
                    info.status = data.get("status", info.status)
                    info.current_platform = data.get("platform", info.current_platform)
                    await _push_device_list_to_frontend()

            else:
                logger.debug(f"[AppWS] 未知消息类型: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"[AppWS] 设备断开: {device_id}")
    except Exception as e:
        logger.error(f"[AppWS] 连接异常: {e}")
    finally:
        if device_id:
            await app_device_manager.disconnect(device_id)
            await _push_device_list_to_frontend()


@app.websocket("/ws/frontend")
async def frontend_websocket_endpoint(websocket: WebSocket):
    """前端（浏览器）WebSocket 连接，用于实时接收设备状态"""
    await frontend_ws.connect(websocket)
    try:
        # 立即推送一次设备列表
        devices = app_device_manager.list_devices()
        await websocket.send_json({
            "type": "app_devices",
            "devices": [{
                "device_id": d.device_id,
                "device_name": d.device_name,
                "system_version": d.system_version,
                "app_version": d.app_version,
                "model": d.model,
                "status": d.status,
                "current_platform": d.current_platform,
            } for d in devices]
        })

        # 保持连接
        while True:
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        frontend_ws.disconnect(websocket)


# ================ 统计 API ================

@app.get("/api/stats")
async def get_stats(device_id: str = None, task_id: str = None):
    """获取任务统计信息"""
    from backend.task_manager import task_statistics
    stats = task_statistics.get_stats(device_id, task_id)
    return {"success": True, "data": stats}


@app.get("/api/stats/device/{device_id}")
async def get_device_stats(device_id: str):
    """获取指定设备的统计信息"""
    from backend.task_manager import task_statistics
    stats = task_statistics.get_stats(device_id)
    return {"success": True, "data": stats}


@app.get("/api/stats/task/{task_id}")
async def get_task_stats(task_id: str):
    """获取指定任务在所有设备上的统计信息"""
    from backend.task_manager import task_statistics
    all_stats = task_statistics.get_stats()
    task_stats = {}
    for dev_id, tasks in all_stats.items():
        if task_id in tasks:
            task_stats[dev_id] = tasks[task_id]
    return {"success": True, "data": task_stats}


# ================ 工具函数 ================
async def _push_device_list_to_frontend():
    """向所有前端 WebSocket 连接推送设备列表"""
    try:
        devices = app_device_manager.list_devices()
        device_list = [{
            "device_id": d.device_id,
            "device_name": d.device_name,
            "system_version": d.system_version,
            "app_version": d.app_version,
            "model": d.model,
            "status": d.status,
            "current_platform": d.current_platform,
        } for d in devices]

        await frontend_ws.broadcast({
            "type": "app_devices",
            "devices": device_list,
        })
    except Exception as e:
        logger.debug(f"[FrontendWS] 推送设备列表失败: {e}")


# ================ 任务模板 API ================

@app.get("/api/templates")
async def list_templates(scope: str = "all", device_id: str = "", _auth: None = Depends(_check_api_token)):
    """列出任务模板"""
    actual_scope = scope
    if scope == "device" and device_id:
        actual_scope = f"device:{device_id}"
    return {"templates": template_manager.list_templates(scope=actual_scope)}


@app.post("/api/templates")
async def save_template(body: dict, _auth: None = Depends(_check_api_token)):
    """保存/更新任务模板"""
    result = template_manager.save_template(
        name=body.get("name", "未命名任务"),
        task_config=body.get("config", {}),
        scope=body.get("scope", "global"),
        device_id=body.get("device_id"),
        template_id=body.get("id"),
    )
    return result


@app.get("/api/templates/{template_id}")
async def get_template(template_id: str, _auth: None = Depends(_check_api_token)):
    """获取单个模板详情"""
    tpl = template_manager.get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return tpl


@app.delete("/api/templates/{template_id}")
async def delete_template(template_id: str, _auth: None = Depends(_check_api_token)):
    """删除模板"""
    if template_manager.delete_template(template_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="模板不存在")


@app.post("/api/templates/{template_id}/mount")
async def mount_template_to_device(template_id: str, body: dict, _auth: None = Depends(_check_api_token)):
    """将模板挂载到设备（复制一份到设备级）"""
    device_id = body.get("device_id", "")
    if not device_id:
        raise HTTPException(status_code=400, detail="需要提供 device_id")
    result = template_manager.copy_to_device(template_id, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="源模板不存在")
    return result


# ================ 定时任务 API ================

@app.get("/api/schedules")
async def list_schedules(_auth: None = Depends(_check_api_token)):
    """列出所有定时任务"""
    return {"schedules": scheduler.list_jobs()}


@app.post("/api/schedules")
async def save_schedule(body: dict, _auth: None = Depends(_check_api_token)):
    """保存/更新定时任务"""
    result = scheduler.save_job(body)
    return result


@app.get("/api/schedules/{job_id}")
async def get_schedule(job_id: str, _auth: None = Depends(_check_api_token)):
    """获取定时任务详情"""
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return job


@app.delete("/api/schedules/{job_id}")
async def delete_schedule(job_id: str, _auth: None = Depends(_check_api_token)):
    """删除定时任务"""
    if scheduler.delete_job(job_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="定时任务不存在")


@app.post("/api/schedules/{job_id}/toggle")
async def toggle_schedule(job_id: str, body: dict = {}, _auth: None = Depends(_check_api_token)):
    """启用/禁用定时任务"""
    enabled = body.get("enabled", True)
    result = scheduler.toggle_job(job_id, enabled)
    if not result:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return result


@app.post("/api/schedules/{job_id}/trigger")
async def trigger_schedule_now(job_id: str, _auth: None = Depends(_check_api_token)):
    """手动立即触发执行一次定时任务"""
    success = await scheduler.trigger_now(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="定时任务不存在")
    return {"success": True, "message": "已触发执行"}


# ============================================================
# 动作日志 API
# ============================================================

@app.get("/api/action-logs")
async def get_action_logs(device_id: str = "", task_id: str = "", limit: int = 100, _auth: None = Depends(_check_api_token)):
    """获取动作日志"""
    from backend.task_manager import action_logger
    
    if device_id:
        logs = action_logger.get_logs_by_device(device_id, limit=limit)
    elif task_id:
        logs = action_logger.get_logs_by_task(task_id, limit=limit)
    else:
        logs = action_logger.get_all_logs(limit=limit)
    
    return {"logs": logs}


@app.delete("/api/action-logs")
async def clear_action_logs(_auth: None = Depends(_check_api_token)):
    """清空所有动作日志"""
    from backend.task_manager import action_logger
    action_logger.clear_logs()
    return {"success": True, "message": "日志已清空"}
