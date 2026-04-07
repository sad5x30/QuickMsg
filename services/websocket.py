from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        user_connections = self.active_connections.get(user_id)
        if not user_connections:
            return

        if websocket in user_connections:
            user_connections.remove(websocket)

        if not user_connections:
            self.active_connections.pop(user_id, None)

    async def notify(self, user_id: int, payload: dict) -> None:
        stale_connections: list[WebSocket] = []

        for websocket in self.active_connections.get(user_id, []):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(user_id, websocket)


notification_manager = NotificationConnectionManager()


async def notify_user(user_id: int, data: dict) -> None:
    await notification_manager.notify(user_id, data)
