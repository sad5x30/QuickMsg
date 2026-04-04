from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, Text
from sqlalchemy.orm import relationship

from db import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    sender_id = Column(Integer, ForeignKey("users.id"))
    text = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="messages")