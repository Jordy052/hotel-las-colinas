from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, JSON, LargeBinary, Numeric, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


user_permission_links = Table(
    "user_permissions",
    Base.metadata,
    Column("user_id", ForeignKey("app_users.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    users: Mapped[list["AppUser"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    users: Mapped[list["AppUser"]] = relationship(
        secondary=user_permission_links, back_populates="permissions"
    )


class AppUser(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        UniqueConstraint("username", name="uq_app_users_username"),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(username)) BETWEEN 5 AND 30 "
            "AND CHAR_LENGTH(username) = CHAR_LENGTH(TRIM(username))",
            name="ck_app_users_username_length",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(30), nullable=False)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    cedula: Mapped[Optional[str]] = mapped_column(String(16), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=user_permission_links, back_populates="users", lazy="selectin"
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    nightly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    bed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    bed_type: Mapped[str] = mapped_column(String(40), nullable=False, default="Queen")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Disponible", index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    amenities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    photos: Mapped[list["RoomPhoto"]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="RoomPhoto.position"
    )
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="room")


class RoomPhoto(Base):
    __tablename__ = "room_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    room: Mapped[Room] = relationship(back_populates="photos")
    asset: Mapped[Optional["RoomPhotoAsset"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", uselist=False
    )


class RoomPhotoAsset(Base):
    """Persistent image bytes shared by the API and desktop clients."""
    __tablename__ = "room_photo_assets"

    photo_id: Mapped[int] = mapped_column(ForeignKey("room_photos.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=False, deferred=True)
    mime_type: Mapped[str] = mapped_column(String(80), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    photo: Mapped[RoomPhoto] = relationship(back_populates="asset")


class Guest(Base):
    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    document_number: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="guest")


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False, index=True)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Confirmada", index=True)
    payment_status: Mapped[str] = mapped_column(String(24), nullable=False, default="Pagado")
    source: Mapped[str] = mapped_column(
        String(24), nullable=False, default="Administración", server_default="Administración"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    guest: Mapped[Guest] = relationship(back_populates="reservations")
    room: Mapped[Room] = relationship(back_populates="reservations")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column(
        ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="Tarjeta")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="Pagado")
    reference: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reservation: Mapped[Reservation] = relationship(back_populates="payments")


class BookingHold(Base):
    __tablename__ = "booking_holds"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_users.id"), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    check_in: Mapped[date] = mapped_column(Date, nullable=False)
    check_out: Mapped[date] = mapped_column(Date, nullable=False)
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    reservation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("reservations.id"), nullable=True, unique=True)
