from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text

from db import Base


class Notifications(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    type = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    is_read = Column(Integer, default=0, nullable=False)
    data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
