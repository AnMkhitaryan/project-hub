from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.user import UserRegister
from app.services.security import hash_password, verify_password

INCORRECT_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="incorrect login or password",
)


async def create_user(session: AsyncSession, data: UserRegister) -> User:
    user = User(login=data.login, email=data.email, password_hash=hash_password(data.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="login or email already registered"
        ) from exc
    await session.refresh(user)
    return user


async def authenticate_user(session: AsyncSession, login: str, password: str) -> User:
    result = await session.execute(select(User).where(User.login == login))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise INCORRECT_CREDENTIALS_ERROR
    return user