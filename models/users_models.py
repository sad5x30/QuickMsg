from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from db import Base

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    members = relationship("ChatParticipant", back_populates="user")


