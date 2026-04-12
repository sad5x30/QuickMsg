from collections import defaultdict
from typing import Any

from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = defaultdict(list)
        # chat_id -> [websocket, websocket]

    async def connect(self, chat_id: int, user_id: int, websocket: WebSocket):
        await websocket.accept()

        self.active_connections[chat_id].append({
            "ws": websocket,
            "user_id": user_id
        })

    def disconnect(self, chat_id: int, websocket: WebSocket):
        self.active_connections[chat_id] = [
            c for c in self.active_connections[chat_id]
            if c["ws"] != websocket
        ]
        if not self.active_connections[chat_id]:
            self.active_connections.pop(chat_id, None)

    async def send_to_chat(self, chat_id: int, payload: dict[str, Any]):
        stale_connections: list[WebSocket] = []

        for conn in self.active_connections[chat_id]:
            try:
                await conn["ws"].send_json(payload)
            except Exception:
                stale_connections.append(conn["ws"])

        for websocket in stale_connections:
            self.disconnect(chat_id, websocket)

    async def send_to_chat_except(
        self,
        chat_id: int,
        exclude_user_id: int,
        payload: dict[str, Any],
    ):
        stale_connections: list[WebSocket] = []

        for conn in self.active_connections[chat_id]:
            if conn["user_id"] == exclude_user_id:
                continue

            try:
                await conn["ws"].send_json(payload)
            except Exception:
                stale_connections.append(conn["ws"])

        for websocket in stale_connections:
            self.disconnect(chat_id, websocket)


manager = ConnectionManager()
