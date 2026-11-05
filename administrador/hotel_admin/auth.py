from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from hotel_admin.database import SessionLocal
from hotel_admin.models import AppUser
from hotel_admin.security import MAX_PASSWORD_LENGTH, verify_password


class AuthService:
    @staticmethod
    def authenticate(email: str, password: str) -> dict | None:
        normalized_email = email.strip().casefold()
        if not normalized_email or not password or len(password) > MAX_PASSWORD_LENGTH:
            return None
        with SessionLocal() as session:
            user = session.execute(
                select(AppUser)
                .options(joinedload(AppUser.role), joinedload(AppUser.permissions))
                .where(func.lower(AppUser.email) == normalized_email)
            ).unique().scalar_one_or_none()
            if user is None or not user.active or not verify_password(password, user.password_hash):
                return None
            return {
                "id": user.id,
                "name": user.username,
                "email": user.email,
                "role": user.role.name,
                "permissions": [permission.label for permission in user.permissions],
            }
