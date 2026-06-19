"""
App 设备管理器 - 管理所有通过 WebSocket 连接的 iOS 助手 App
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, Optional, List
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from backend.app_client.models import AppDeviceInfo, AppCommand, AppCommandResult


class AppDeviceManager:
    """App 设备管理器"""

    def __init__(self):
        # device_id -> (websocket, device_info)
        self._devices: Dict[str, tuple] = {}
        # command_id -> future (用于等待指令返回结果)
        self._pending_commands: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    # ========== 连接管理 ==========

    async def connect(self, websocket: WebSocket, device_info: AppDeviceInfo):
        """新设备连接"""
        device_id = device_info.device_id
        async with self._lock:
            # 如果已有连接，先关闭旧连接
            if device_id in self._devices:
                old_ws, _ = self._devices[device_id]
                try:
                    await old_ws.close()
                except Exception:
                    pass

            self._devices[device_id] = (websocket, device_info)
            logger.info(f"[AppDevice] 设备连接: {device_id} ({device_info.device_name})")

    async def disconnect(self, device_id: str):
        """设备断开连接"""
        async with self._lock:
            if device_id in self._devices:
                _, info = self._devices[device_id]
                del self._devices[device_id]
                logger.info(f"[AppDevice] 设备断开: {device_id} ({info.device_name})")

                # 清理该设备的 pending commands
                for cmd_id, future in list(self._pending_commands.items()):
                    if cmd_id.startswith(f"{device_id}_"):
                        if not future.done():
                            future.set_exception(
                                Exception("Device disconnected")
                            )

    # ========== 指令下发 ==========

    async def send_command(
        self,
        device_id: str,
        action: str,
        platform: str,
        params: dict = None,
        timeout: int = 30
    ) -> AppCommandResult:
        """
        向指定设备发送指令并等待结果

        Args:
            device_id: 目标设备 ID
            action: 操作类型 like|comment|follow|scroll|...
            platform: 平台 xiaohongshu|...
            params: 额外参数
            timeout: 超时时间（秒）

        Returns:
            AppCommandResult 执行结果
        """
        command_id = f"{device_id}_{uuid.uuid4().hex[:8]}"

        async with self._lock:
            if device_id not in self._devices:
                return AppCommandResult(
                    command_id=command_id,
                    success=False,
                    message=f"设备 {device_id} 未连接"
                )
            websocket, _ = self._devices[device_id]

        # 创建 future 等待结果
        future = asyncio.get_event_loop().create_future()
        self._pending_commands[command_id] = future

        try:
            # 发送指令
            command = AppCommand(
                command_id=command_id,
                action=action,
                platform=platform,
                params=params or {}
            )
            await websocket.send_json(command.to_dict())
            logger.info(f"[AppDevice] 下发指令: {device_id} {action} params={params}")

            # 等待结果
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"[AppDevice] 指令完成: {command_id} success={result.success}")
            return result

        except asyncio.TimeoutError:
            return AppCommandResult(
                command_id=command_id,
                success=False,
                message=f"指令执行超时（{timeout}s）"
            )
        except WebSocketDisconnect:
            await self.disconnect(device_id)
            return AppCommandResult(
                command_id=command_id,
                success=False,
                message="设备连接已断开"
            )
        except Exception as e:
            logger.error(f"[AppDevice] 指令发送失败: {e}")
            return AppCommandResult(
                command_id=command_id,
                success=False,
                message=str(e)
            )
        finally:
            if command_id in self._pending_commands:
                del self._pending_commands[command_id]

    async def handle_result(self, result_dict: dict):
        """处理 App 返回的指令结果"""
        command_id = result_dict.get("command_id", "")
        result = AppCommandResult.from_dict(result_dict)

        if command_id in self._pending_commands:
            future = self._pending_commands[command_id]
            if not future.done():
                future.set_result(result)
        else:
            logger.debug(f"[AppDevice] 收到未请求的结果: {command_id}")

    # ========== 查询 ==========

    def get_device(self, device_id: str) -> Optional[AppDeviceInfo]:
        """获取指定设备信息"""
        if device_id in self._devices:
            return self._devices[device_id][1]
        return None

    def list_devices(self) -> List[AppDeviceInfo]:
        """获取所有已连接设备"""
        return [info for _, info in self._devices.values()]

    def get_device_count(self) -> int:
        """获取已连接设备数量"""
        return len(self._devices)

    # ========== 广播 ==========

    async def broadcast(self, message: dict):
        """向所有设备广播消息"""
        async with self._lock:
            devices = list(self._devices.values())

        for ws, info in devices:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(info.device_id)

    # ========== 心跳 ==========

    def update_heartbeat(self, device_id: str):
        """更新设备心跳"""
        if device_id in self._devices:
            ws, info = self._devices[device_id]
            info.last_heartbeat = datetime.now()
