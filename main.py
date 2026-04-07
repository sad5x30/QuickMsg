from fastapi import FastAPI, Request, Query, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from db import init_models
import models  # noqa: F401

from services.auth import router as auth_router
from services.search import router as search_router
from routers.create_chat import router as chat_router
from routers.notifications import router as notifications_router
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

app = FastAPI()
templating = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_router)
app.include_router(search_router, prefix="/users", tags=["search"])
app.include_router(chat_router)
app.include_router(notifications_router)
@app.get("/", response_class=HTMLResponse)
async def home(request:Request):
    user = request.cookies.get("access_token")
    return templating.TemplateResponse(
        request,
        "index.html",
        {"is_authenticated": bool(user)}
    )
