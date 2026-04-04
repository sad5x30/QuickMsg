from collections import defaultdict
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active_connections = defaultdict(list)
        # chat_id -> [websocket, websocket]

    async def connect(self, chat_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[chat_id].append(websocket)

    def disconnect(self, chat_id: int, websocket: WebSocket):
        if websocket in self.active_connections[chat_id]:
            self.active_connections[chat_id].remove(websocket)

    async def send_to_chat(self, chat_id: int, message: str):
        for connection in self.active_connections[chat_id]:
            await connection.send_text(message)


manager = ConnectionManager()
