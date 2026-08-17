from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import get_current_user
from app.models import User
from app.schemas.token import Token, UserLogin
from app.schemas.user import UserPublic, UserRegister
from app.services.security import create_access_token
from app.services.users import authenticate_user, create_user

router = APIRouter(tags=["auth"])


@router.post("/auth", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegister, session: AsyncSession = Depends(get_session)) -> User:
    return await create_user(session, payload)


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, session: AsyncSession = Depends(get_session)) -> Token:
    user = await authenticate_user(session, payload.login, payload.password)
    return Token(access_token=create_access_token(user_id=user.id))


@router.get("/me", response_model=UserPublic)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
