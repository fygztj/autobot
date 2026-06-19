"""
App 客户端 WebSocket 路由
iOS 助手 App 通过此端点连接到 PC 端服务
"""
import json
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

from backend.app_client import app_device_manager
from backend.app_client.models import AppDeviceInfo
from backend.api.websocket import ws_manager  # 前端 WebSocket（用于推送设备状态）

router = APIRouter(tags=["app"])


@router.websocket("/ws/app/connect")
async def app_websocket_endpoint(websocket: WebSocket):
    """
    iOS 助手 App 连接端点

    连接流程:
    1. App 发送 register 消息，上报设备信息
    2. PC 端发送指令（command）
    3. App 执行后返回 result
    """
    await websocket.accept()
    device_id = None

    try:
        # 等待注册消息
        register_msg = await websocket.receive_json()
        msg_type = register_msg.get("type", "")

        if msg_type != "register":
            await websocket.send_json({
                "type": "error",
                "message": "First message must be 'register'"
            })
            await websocket.close()
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
            await websocket.send_json({"type": "error", "message": "device_id required"})
            await websocket.close()
            return

        # 添加到管理器
        await app_device_manager.connect(websocket, device_info)

        # 回复注册成功
        await websocket.send_json({
            "type": "welcome",
            "server_time": datetime.now().isoformat(),
            "device_id": device_id
        })

        # 向前端推送设备列表更新
        await _push_device_list()

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
                    await _push_device_list()

            else:
                logger.debug(f"[AppWS] 未知消息类型: {msg_type} data={data}")

    except WebSocketDisconnect:
        logger.info(f"[AppWS] 设备断开连接: {device_id}")
    except Exception as e:
        logger.error(f"[AppWS] 连接异常: {e}")
    finally:
        if device_id:
            await app_device_manager.disconnect(device_id)
            await _push_device_list()


async def _push_device_list():
    """向前端页面推送最新设备列表"""
    try:
        devices = app_device_manager.list_devices()
        device_list = [{
            "device_id": d.device_id,
            "device_name": d.device_name,
            "system_version": d.system_version,
            "app_version": d.app_version,
            "model": d.model,
            "status": d.status,
            "platform": d.current_platform,
            "connected_at": d.connected_at.isoformat()
        } for d in devices]

        await ws_manager.broadcast({
            "type": "app_devices",
            "devices": device_list
        })
    except Exception as e:
        logger.debug(f"[AppWS] 推送设备列表失败: {e}")
