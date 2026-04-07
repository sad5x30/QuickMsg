import json

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.notifications_table import Notifications
from models.users_models import Users
from services.auth import get_current_user, get_current_user_ws
from services.websocket import notification_manager, notify_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


def serialize_notification(notification: Notifications) -> dict:
    return {
        "id": notification.id,
        "type": notification.type,
        "text": notification.text,
        "is_read": bool(notification.is_read),
        "data": json.loads(notification.data) if notification.data else None,
        "created_at": notification.created_at.isoformat(),
    }

async def create_notification(db, user_id: int, type_: str, text: str, data: dict | None = None):
    notification = Notifications(
        user_id=user_id,
        type=type_,
        text=text,
        data=json.dumps(data) if data else None
    )

    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    return notification

async def send_notification(db, user_id: int, type_: str, text: str, data: dict | None = None):
    notification = await create_notification(db, user_id, type_, text, data)

    await notify_user(user_id, serialize_notification(notification))

@router.websocket("/ws")
async def notifications_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_ws(websocket, db)
    await notification_manager.connect(user.id, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notification_manager.disconnect(user.id, websocket)
    except Exception:
        notification_manager.disconnect(user.id, websocket)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


@router.get("")
async def get_notifications(
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Notifications)
        .where(Notifications.user_id == current_user.id)
        .order_by(Notifications.created_at.desc())
    )

    return [serialize_notification(item) for item in result.scalars().all()]

@router.post("/read")
async def mark_as_read(
    chat_id: int | None = Query(default=None),
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(Notifications).where(
        Notifications.user_id == current_user.id,
        Notifications.is_read == 0,
    )

    if chat_id is not None:
        query = query.where(Notifications.data.contains(f'"chat_id": {chat_id}'))

    result = await db.execute(query)

    notifications = result.scalars().all()

    for n in notifications:
        n.is_read = 1

    await db.commit()

    return {"status": "ok", "updated": len(notifications)}
