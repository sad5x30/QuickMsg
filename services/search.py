from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from models.users_models import Users
from sqlalchemy import select
from db import get_db

router = APIRouter()

async def search_function(query: str, db: AsyncSession):
    result = await db.execute(
        select(Users).where(Users.username.ilike(f"%{query}%")).limit(20)
    )

    return result.scalars().all()


@router.get("/search")
async def search(query: str, db: AsyncSession = Depends(get_db)):
    users = await search_function(query, db)
    return [
        {
            "id": user.id,
            "username": user.username,
        }
        for user in users
    ]
