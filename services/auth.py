from fastapi import APIRouter, Depends, Request, Form, HTTPException, WebSocket, WebSocketException, UploadFile, File, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
import os
from uuid import uuid4

from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError

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

AVATAR_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "avatars"
AVATAR_URL_PREFIX = "/static/uploads/avatars/"
ALLOWED_AVATAR_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024
AVATAR_IMAGE_SIZE = (256, 256)
AVATAR_OUTPUT_SETTINGS = {
    "image/jpeg": { "extension": ".jpg", "format": "JPEG", "save_kwargs": {"quality": 88, "optimize": True}},
    "image/jpg": { "extension": ".jpg", "format": "JPEG", "save_kwargs": {"quality": 88, "optimize": True}},
    "image/png": { "extension": ".png", "format": "PNG", "save_kwargs": {"optimize": True}},
    "image/webp": { "extension": ".webp", "format": "WEBP", "save_kwargs": {"quality": 88, "method": 6}},
    # GIF avatars are normalized to a static PNG so layout and file size stay predictable.
    "image/gif": { "extension": ".png", "format": "PNG", "save_kwargs": {"optimize": True}},
}

async def get_db():
    async with async_session() as db:
        yield db


def ensure_avatar_upload_dir() -> None:
    AVATAR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_avatar_file_path(avatar_url: str) -> Path | None:
    if not avatar_url or not avatar_url.startswith(AVATAR_URL_PREFIX):
        return None

    file_name = avatar_url.removeprefix(AVATAR_URL_PREFIX)
    return AVATAR_UPLOAD_DIR / file_name


def normalize_avatar_image(content: bytes, content_type: str) -> tuple[bytes, str]:
    output_settings = AVATAR_OUTPUT_SETTINGS.get(content_type)
    if output_settings is None:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    try:
        with Image.open(BytesIO(content)) as source_image:
            prepared_image = ImageOps.exif_transpose(source_image)
            fitted_image = ImageOps.fit(
                prepared_image,
                AVATAR_IMAGE_SIZE,
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

            target_format = output_settings["format"]
            if target_format == "JPEG":
                fitted_image = fitted_image.convert("RGB")
            else:
                fitted_image = fitted_image.convert("RGBA")

            normalized_buffer = BytesIO()
            fitted_image.save(
                normalized_buffer,
                format=target_format,
                **output_settings["save_kwargs"],
            )
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Failed to process avatar image") from exc

    return normalized_buffer.getvalue(), output_settings["extension"]

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


@router.post("/profile/avatar")
async def upload_avatar(
    avatar: UploadFile = File(...),
    current_user: Users = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    content_type = avatar.content_type or ""
    extension = ALLOWED_AVATAR_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(status_code=400, detail="Unsupported image format")

    content = await avatar.read()
    await avatar.close()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Avatar is too large (max 5 MB)")

    normalized_content, normalized_extension = normalize_avatar_image(content, content_type)

    ensure_avatar_upload_dir()

    previous_avatar_url = current_user.avatar_url
    file_name = f"user_{current_user.id}_{uuid4().hex}{normalized_extension}"
    avatar_path = AVATAR_UPLOAD_DIR / file_name
    avatar_path.write_bytes(normalized_content)

    current_user.avatar_url = f"{AVATAR_URL_PREFIX}{file_name}"
    await session.commit()
    await session.refresh(current_user)

    previous_avatar_path = get_avatar_file_path(previous_avatar_url)
    if (
        previous_avatar_path
        and previous_avatar_path.exists()
        and previous_avatar_path != avatar_path
    ):
        previous_avatar_path.unlink(missing_ok=True)

    return RedirectResponse("/profile", status_code=303)

@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("access_token")
    return response
