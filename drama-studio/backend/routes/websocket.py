"""
WebSocket 实时进度推送路由。

前端可通过 WebSocket 订阅项目进度事件（agent 开始/完成/失败、流水线完成等）。
"""

import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import auth
from ..services.pipeline import progress_emitter

logger = logging.getLogger("drama-studio.routes.websocket")

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, list] = {}

    async def connect(self, project_id: str, ws: WebSocket):
        await ws.accept()
        self.active.setdefault(project_id, []).append(ws)

    def disconnect(self, project_id: str, ws: WebSocket):
        if project_id in self.active:
            if ws in self.active[project_id]:
                self.active[project_id].remove(ws)
            if not self.active[project_id]:
                del self.active[project_id]

    async def broadcast(self, project_id: str, event: Dict):
        if project_id in self.active:
            for ws in list(self.active[project_id]):
                try:
                    await ws.send_json(event)
                except Exception:
                    self.disconnect(project_id, ws)


manager = ConnectionManager()


async def _relay(project_id: str, event: Dict):
    await manager.broadcast(project_id, event)


# 注册到全局进度发射器
progress_emitter.add_listener(_relay)


@router.websocket("/ws/{project_id}")
async def websocket_endpoint(ws: WebSocket, project_id: str):
    # 校验会话 Cookie（BaseHTTPMiddleware 不包裹 WebSocket，需在此处单独校验）
    token = ws.cookies.get(auth.SESSION_COOKIE)
    if not auth.verify_session_token(token):
        await ws.close(code=1008)  # Policy Violation
        return
    await manager.connect(project_id, ws)
    try:
        # 发送连接成功消息
        await ws.send_json({"type": "connected", "project_id": project_id})
        while True:
            # 接收心跳或指令
            data = await ws.receive_text()
            # 心跳响应
            await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(project_id, ws)
