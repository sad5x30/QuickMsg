from fastapi import APIRouter, Depends, Request, Form, HTTPException, WebSocket, WebSocketException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.security import OAuth2PasswordRequestForm
import os

from pathlib import Path

from dotenv import load_dotenv

from db import async_session

import hashlib

import bcrypt

from datetime import timedelta
from datetime import datetime

from jose import jwt, JWTError

from models.users_models import Users

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

templating = Jinja2Templates(directory="templates")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.txt")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

async def get_db():
    async with async_session() as db:
        yield db

def _password_to_bcrypt_input(password: str) -> bytes:
    # Pre-hash removes bcrypt 72-byte input limit while keeping bcrypt as KDF.
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(password: str):
    normalized = _password_to_bcrypt_input(password)
    return bcrypt.hashpw(normalized, bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password, hashed_password):
    hashed_bytes = hashed_password.encode("utf-8")

    # Backward compatibility for previously stored raw bcrypt hashes.
    try:
        if bcrypt.checkpw(plain_password.encode("utf-8"), hashed_bytes):
            return True
    except ValueError:
        pass

    normalized = _password_to_bcrypt_input(plain_password)
    return bcrypt.checkpw(normalized, hashed_bytes)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=30))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.get("/login", response_class=HTMLResponse)
async def get_login(request:Request):
    return templating.TemplateResponse(request, "auth/login.html")

@router.get("/register", response_class=HTMLResponse)
async def get_registration(request:Request):
    return templating.TemplateResponse(request, "auth/register.html")

@router.post("/register")
async def registration(username: str = Form(...), password: str = Form(...), session: AsyncSession=Depends(get_db)):
    new_user = await session.execute(
        select(Users).where(Users.username == username)
    )

    get_one_user = new_user.scalar_one_or_none()

    if get_one_user:
        raise HTTPException(status_code=400, detail="User already exists")

    hashing_password = hash_password(password)

    creating_new_user = Users(
        username = username,
        password = hashing_password
    )

    session.add(creating_new_user)
    await session.commit()
    await session.refresh(creating_new_user)

    return RedirectResponse(url="/login", status_code=303)

    
@router.post("/login", status_code=HTMLResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),session: AsyncSession = Depends(get_db)):
    login_user = await session.execute(
        select(Users).where(Users.username == form_data.username)
    )

    user = login_user.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    
    if not verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="wrong password")

    access_token = create_access_token({"sub": str(user.id)})

    redirect = RedirectResponse("/", status_code=303)
    redirect.set_cookie(key="access_token", value=access_token, httponly=True)
    return redirect


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

async def get_current_user_ws(websocket: WebSocket, db: AsyncSession):
    token = websocket.cookies.get("access_token")

    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    result = await db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    return user

@router.get("/profile", response_class=HTMLResponse)
async def profile(request: Request, current_user: Users = Depends(get_current_user)):
    return templating.TemplateResponse(
        request,
        "auth/profile.html",
        {"current_user": current_user},
    )

@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response
