from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from db import Base

class ChatParticipant(Base):
    __tablename__ = "chat_participants"

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer, ForeignKey("chats.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime, default=datetime.utcnow)

    chat = relationship("Chat", back_populates="participants")
    user = relationship("Users")