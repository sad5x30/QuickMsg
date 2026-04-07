from pathlib import Path
import sys
from datetime import datetime
from unittest.mock import AsyncMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from models.notifications_table import Notifications
from routers.notifications import send_notification, serialize_notification
from services.websocket import NotificationConnectionManager


class FailingWebSocket:
    async def send_json(self, payload):
        raise RuntimeError("socket is closed")


class FakeNotificationSession:
    def __init__(self, created_at: datetime):
        self.created_at = created_at
        self.saved_notifications = []
        self.commit = AsyncMock()
        self.refresh = AsyncMock(side_effect=self._refresh)

    def add(self, instance):
        instance.id = 7
        instance.created_at = self.created_at
        self.saved_notifications.append(instance)

    async def _refresh(self, instance):
        return instance


@pytest.mark.anyio
async def test_send_notification_creates_and_pushes_notification(monkeypatch):
    created_at = datetime(2024, 1, 2, 3, 4, 5)
    db_session = FakeNotificationSession(created_at)

    pushed_payloads = []

    async def fake_notify_user(user_id, payload):
        pushed_payloads.append((user_id, payload))

    monkeypatch.setattr("routers.notifications.notify_user", fake_notify_user)

    await send_notification(
        db_session,
        user_id=2,
        type_="message",
        text="Новое сообщение от alice",
        data={"chat_id": 5, "text": "hello"},
    )

    assert len(db_session.saved_notifications) == 1
    db_session.commit.assert_awaited_once()
    db_session.refresh.assert_awaited_once()
    assert pushed_payloads == [
        (
            2,
            {
                "id": 7,
                "type": "message",
                "text": "Новое сообщение от alice",
                "is_read": False,
                "data": {"chat_id": 5, "text": "hello"},
                "created_at": "2024-01-02T03:04:05",
            },
        )
    ]


def test_serialize_notification_returns_expected_payload():
    notification = Notifications(
        id=3,
        user_id=10,
        type="message",
        text="Новое сообщение",
        is_read=1,
        data='{"chat_id": 9}',
        created_at=datetime(2024, 5, 6, 7, 8, 9),
    )

    assert serialize_notification(notification) == {
        "id": 3,
        "type": "message",
        "text": "Новое сообщение",
        "is_read": True,
        "data": {"chat_id": 9},
        "created_at": "2024-05-06T07:08:09",
    }


@pytest.mark.anyio
async def test_notification_manager_removes_stale_connections():
    manager = NotificationConnectionManager()
    healthy_socket = AsyncMock()
    stale_socket = FailingWebSocket()

    manager.active_connections = {4: [healthy_socket, stale_socket]}

    await manager.notify(4, {"text": "ping"})

    healthy_socket.send_json.assert_awaited_once_with({"text": "ping"})
    assert manager.active_connections == {4: [healthy_socket]}
