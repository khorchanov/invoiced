from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user import UserRepository

_DUMMY_HASH = hash_password("dummy-password-for-timing")


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self.users = users

    async def register(self, email: str, password: str) -> User:
        email = email.lower()
        if await self.users.get_by_email(email):
            raise EmailAlreadyRegisteredError(email)
        try:
            return await self.users.create(email, hash_password(password))
        except IntegrityError:
            await self.users.session.rollback()
            raise EmailAlreadyRegisteredError(email)

    async def login(self, email: str, password: str) -> str:
        user = await self.users.get_by_email(email.lower())
        hashed = user.hashed_password if user else _DUMMY_HASH
        password_ok = verify_password(password, hashed)
        if not user or not password_ok:
            raise InvalidCredentialsError
        return create_access_token(str(user.id))
