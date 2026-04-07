from datetime import datetime, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from services.auth import get_current_user_ws

router = APIRouter()

last_seen: dict[int, datetime] = {}


class StatusConnectionManager:
    def __init__(self):
        self.subscribers: dict[int, list[WebSocket]] = {}

    async def connect(self, target_user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.subscribers.setdefault(target_user_id, []).append(websocket)

    def disconnect(self, target_user_id: int, websocket: WebSocket):
        connections = self.subscribers.get(target_user_id)
        if not connections:
            return

        if websocket in connections:
            connections.remove(websocket)

        if not connections:
            self.subscribers.pop(target_user_id, None)

    async def broadcast(self, user_id: int, payload: dict) -> None:
        stale_connections: list[WebSocket] = []

        for websocket in self.subscribers.get(user_id, []):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(user_id, websocket)


class NotificationConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        was_online = self.is_online(user_id)
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

        if not was_online:
            await broadcast_user_status(user_id)

    def disconnect(self, user_id: int, websocket: WebSocket):
        connections = self.active_connections.get(user_id)
        if not connections:
            return

        if websocket in connections:
            connections.remove(websocket)

        if connections:
            return False

        self.active_connections.pop(user_id, None)
        last_seen[user_id] = datetime.now(timezone.utc)
        return True

    def is_online(self, user_id: int) -> bool:
        return user_id in self.active_connections

    async def notify(self, user_id: int, payload: dict) -> None:
        stale_connections: list[WebSocket] = []

        for websocket in self.active_connections.get(user_id, []):
            try:
                await websocket.send_json(payload)
            except Exception:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            became_offline = self.disconnect(user_id, websocket)
            if became_offline:
                await broadcast_user_status(user_id)


notification_manager = NotificationConnectionManager()
status_manager = StatusConnectionManager()


def get_user_status_payload(user_id: int) -> dict:
    if notification_manager.is_online(user_id):
        return {
            "user_id": user_id,
            "status": "online",
            "last_seen": None,
        }

    return {
        "user_id": user_id,
        "status": "offline",
        "last_seen": last_seen.get(user_id),
    }


async def broadcast_user_status(user_id: int) -> None:
    await status_manager.broadcast(user_id, get_user_status_payload(user_id))


async def notify_user(user_id: int, data: dict) -> None:
    await notification_manager.notify(user_id, data)


@router.get("/users/{user_id}/status")
def get_user_status(user_id: int):
    return get_user_status_payload(user_id)


@router.websocket("/ws/status/{user_id}")
async def user_status_websocket(
    websocket: WebSocket,
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    await get_current_user_ws(websocket, db)
    await status_manager.connect(user_id, websocket)
    await websocket.send_json(get_user_status_payload(user_id))

    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        status_manager.disconnect(user_id, websocket)
    except Exception:
        status_manager.disconnect(user_id, websocket)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
