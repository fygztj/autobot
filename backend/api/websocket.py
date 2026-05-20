"""
WebSocket 管理器 - 实时推送设备状态和任务进度
"""
from typing import List
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self._connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, message: dict):
        """向所有客户端广播消息"""
        import json
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, message: dict):
        try:
            await ws.send_json(message)
        except Exception:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()