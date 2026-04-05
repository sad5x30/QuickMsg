from pathlib import Path
import sys
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.chat_models import Chat
from models.members_table import ChatParticipant
from models.messages import Message
from models.users_models import Users
from routers.create_chat import get_private_chat_between_users, get_chat_messages


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeScalarsResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return self

    def all(self):
        return self.values


@pytest.mark.anyio
async def test_get_private_chat_between_users_returns_existing_private_chat():
    chat = Chat()
    chat.id = 10

    db_session = AsyncMock()
    db_session.execute.return_value = FakeResult(chat)

    result = await get_private_chat_between_users(1, 2, db_session)

    assert result is not None
    assert result.id == chat.id
    db_session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_get_private_chat_between_users_returns_none_when_chat_does_not_exist():
    db_session = AsyncMock()
    db_session.execute.return_value = FakeResult(None)

    result = await get_private_chat_between_users(1, 2, db_session)

    assert result is None
    db_session.execute.assert_awaited_once()

@pytest.mark.anyio
async def test_get_chat_messages_returns_403_when_user_is_not_a_participant():
    current_user = Users(id=1, username="sad", password="secret")
    db_session = AsyncMock()
    db_session.execute.return_value = FakeResult(None)

    with pytest.raises(HTTPException) as exc_info:
        await get_chat_messages(1, current_user, db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Forbidden"
    db_session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_get_chat_messages_returns_serialized_messages_for_participant():
    participant = ChatParticipant()
    participant.chat_id = 1
    participant.user_id = 1

    current_user = Users(id=1, username="sad", password="secret")
    message = Message(
        id=10,
        chat_id=1,
        sender_id=1,
        text="hello",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )

    db_session = AsyncMock()
    db_session.execute.side_effect = [
        FakeResult(participant),
        FakeScalarsResult([message]),
    ]

    result = await get_chat_messages(1, current_user, db_session)

    assert result == [
        {
            "id": 10,
            "chat_id": 1,
            "text": "hello",
            "sender_id": 1,
            "created_at": "2024-01-01T12:00:00",
            "is_own": True,
        }
    ]
    assert db_session.execute.await_count == 2
