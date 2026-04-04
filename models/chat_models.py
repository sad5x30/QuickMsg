from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from db import Base

class Chat(Base):
    __tablename__ = "chats"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    participants = relationship("ChatParticipant", back_populates="chat", cascade="all, delete")
    messages = relationship("Message", back_populates="chat", cascade="all, delete")