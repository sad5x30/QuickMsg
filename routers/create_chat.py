import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db import get_db
from models.chat_models import Chat
from models.members_table import ChatParticipant
from models.messages import Message
from models.users_models import Users
from routers.notifications import send_notification
from services.auth import get_current_user, get_current_user_ws
from services.manager import manager

router = APIRouter(prefix="/chats", tags=["chats"])


async def check_user_in_chat(user_id: int, chat_id: int, db: AsyncSession) -> bool:
    result = await db.execute(
        select(ChatParticipant).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id == user_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def get_private_chat_between_users(
    user1_id: int,
    user2_id: int,
    db: AsyncSession,
) -> Chat | None:
    chat_ids = (
        select(ChatParticipant.chat_id)
        .group_by(ChatParticipant.chat_id)
        .having(
            func.count(ChatParticipant.user_id) == 2,
            func.count(ChatParticipant.user_id)
            .filter(ChatParticipant.user_id == user1_id) == 1,
            func.count(ChatParticipant.user_id)
            .filter(ChatParticipant.user_id == user2_id) == 1,
        )
    )

    result = await db.execute(
        select(Chat)
        .where(Chat.id.in_(chat_ids))
        .options(
            selectinload(Chat.participants).selectinload(ChatParticipant.user),
        )
    )
    return result.scalar_one_or_none()


async def get_chat_last_message(chat_id: int, db: AsyncSession) -> Message | None:
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def serialize_message(message: Message, current_user_id: int) -> dict:
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "text": message.text,
        "sender_id": message.sender_id,
        "created_at": message.created_at.isoformat(),
        "is_own": message.sender_id == current_user_id,
    }


async def serialize_chat(chat: Chat, current_user_id: int, db: AsyncSession) -> dict:
    other_user = next(
        (participant.user for participant in chat.participants if participant.user_id != current_user_id),
        None,
    )
    last_message = await get_chat_last_message(chat.id, db)

    return {
        "id": chat.id,
        "title": other_user.username if other_user else "Личный чат",
        "participant": {
            "id": other_user.id if other_user else current_user_id,
            "username": other_user.username if other_user else "Вы",
        },
        "last_message": last_message.text if last_message else "",
        "last_message_created_at": (
            last_message.created_at.isoformat() if last_message else None
        ),
        "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
    }


async def get_user_chats(db: AsyncSession, user_id: int) -> list[Chat]:
    result = await db.execute(
        select(Chat)
        .join(ChatParticipant)
        .where(ChatParticipant.user_id == user_id)
        .options(
            selectinload(Chat.participants).selectinload(ChatParticipant.user),
        )
        .order_by(Chat.updated_at.desc(), Chat.id.desc())
    )
    return result.scalars().all()


async def get_chat_recipient_ids(chat_id: int, sender_id: int, db: AsyncSession) -> list[int]:
    result = await db.execute(
        select(ChatParticipant.user_id).where(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id != sender_id,
        )
    )
    return list(result.scalars().all())


@router.get("/me")
async def get_me(current_user: Users = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
    }


@router.get("")
async def list_chats(
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    chats = await get_user_chats(db, current_user.id)
    return [await serialize_chat(chat, current_user.id, db) for chat in chats]


@router.post("/direct/{target_user_id}")
async def get_or_create_private_chat(
    target_user_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if target_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot create a chat with yourself")

    user_result = await db.execute(select(Users).where(Users.id == target_user_id))
    target_user = user_result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    chat = await get_private_chat_between_users(current_user.id, target_user_id, db)

    if chat is None:
        chat = Chat()
        db.add(chat)
        await db.flush()

        db.add_all(
            [
                ChatParticipant(chat_id=chat.id, user_id=current_user.id),
                ChatParticipant(chat_id=chat.id, user_id=target_user_id),
            ]
        )

        await db.commit()

        result = await db.execute(
            select(Chat)
            .where(Chat.id == chat.id)
            .options(
                selectinload(Chat.participants).selectinload(ChatParticipant.user),
            )
        )
        chat = result.scalar_one()

    return await serialize_chat(chat, current_user.id, db)


@router.get("/{chat_id}/messages")
async def get_chat_messages(
    chat_id: int,
    current_user: Users = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_participant = await check_user_in_chat(current_user.id, chat_id, db)
    if not is_participant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    messages = result.scalars().all()
    return [serialize_message(message, current_user.id) for message in messages]


@router.websocket("/ws/chat/{chat_id}")
async def websocket_chat(
    websocket: WebSocket,
    chat_id: int,
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user_ws(websocket, db)

    is_participant = await check_user_in_chat(user.id, chat_id, db)
    if not is_participant:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(chat_id, websocket)

    try:
        while True:
            data = (await websocket.receive_text()).strip()
            if not data:
                continue

            message = Message(
                chat_id=chat_id,
                sender_id=user.id,
                text=data,
            )
            db.add(message)
            await db.flush()

            created_at = message.created_at or datetime.utcnow()

            await db.execute(
                update(Chat)
                .where(Chat.id == chat_id)
                .values(updated_at=created_at)
            )

            await db.commit()

            recipient_ids = await get_chat_recipient_ids(chat_id, user.id, db)
            for recipient_id in recipient_ids:
                await send_notification(
                    db,
                    user_id=recipient_id,
                    type_="message",
                    text=f"Новое сообщение от {user.username}",
                    data={
                        "chat_id": chat_id,
                        "message_id": message.id,
                        "sender_id": user.id,
                        "sender_username": user.username,
                        "text": message.text,
                        "created_at": created_at.isoformat(),
                    },
                )

            await manager.send_to_chat(
                chat_id,
                json.dumps(
                    {
                        "id": message.id,
                        "chat_id": chat_id,
                        "text": message.text,
                        "sender_id": user.id,
                        "created_at": created_at.isoformat(),
                    }
                ),
            )

    except WebSocketDisconnect:
        manager.disconnect(chat_id, websocket)
    except Exception:
        manager.disconnect(chat_id, websocket)
        await db.rollback()
