from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, JSON, LargeBinary, Numeric, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMBLOB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


user_permission_links = Table(
    "usuarios_permisos",
    Base.metadata,
    Column("usuario_id", ForeignKey("usuarios_app.id", ondelete="CASCADE"), primary_key=True),
    Column("permiso_id", ForeignKey("permisos.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column("nombre", String(40), unique=True, nullable=False)
    users: Mapped[list["AppUser"]] = relationship(back_populates="role")


class Permission(Base):
    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column("codigo", String(40), unique=True, nullable=False)
    label: Mapped[str] = mapped_column("etiqueta", String(60), unique=True, nullable=False)
    users: Mapped[list["AppUser"]] = relationship(
        secondary=user_permission_links, back_populates="permissions"
    )


class AppUser(Base):
    __tablename__ = "usuarios_app"
    __table_args__ = (
        UniqueConstraint("nombre_usuario", name="uq_usuarios_app_nombre_usuario"),
        CheckConstraint(
            "CHAR_LENGTH(TRIM(nombre_usuario)) BETWEEN 5 AND 30 "
            "AND CHAR_LENGTH(nombre_usuario) = CHAR_LENGTH(TRIM(nombre_usuario))",
            name="ck_usuarios_app_nombre_usuario_longitud",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column("nombre_usuario", String(30), nullable=False)
    email: Mapped[str] = mapped_column("correo", String(160), unique=True, nullable=False, index=True)
    cedula: Mapped[Optional[str]] = mapped_column(String(16), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column("hash_contrasena", String(255), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column("telefono", String(30), nullable=True)
    active: Mapped[bool] = mapped_column("activo", Boolean, nullable=False, default=True, index=True)
    role_id: Mapped[int] = mapped_column("rol_id", ForeignKey("roles.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=datetime.now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column("actualizado_en", DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    role: Mapped[Role] = relationship(back_populates="users")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=user_permission_links, back_populates="users", lazy="selectin"
    )


class Room(Base):
    __tablename__ = "habitaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column("numero", String(12), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column("categoria", String(40), nullable=False, index=True)
    nightly_rate: Mapped[Decimal] = mapped_column("precio_noche", Numeric(10, 2), nullable=False)
    capacity: Mapped[int] = mapped_column("capacidad", Integer, nullable=False, default=2)
    bed_count: Mapped[int] = mapped_column("cantidad_camas", Integer, nullable=False, default=1)
    bed_type: Mapped[str] = mapped_column("tipo_cama", String(40), nullable=False, default="Queen")
    status: Mapped[str] = mapped_column("estado", String(24), nullable=False, default="Disponible", index=True)
    description: Mapped[Optional[str]] = mapped_column("descripcion", Text, nullable=True)
    amenities: Mapped[list[str]] = mapped_column("comodidades", JSON, nullable=False, default=list)
    active: Mapped[bool] = mapped_column("activo", Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=datetime.now, nullable=False)

    photos: Mapped[list["RoomPhoto"]] = relationship(
        back_populates="room", cascade="all, delete-orphan", order_by="RoomPhoto.position"
    )
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="room")


class RoomPhoto(Base):
    __tablename__ = "fotos_habitacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_id: Mapped[int] = mapped_column("habitacion_id", ForeignKey("habitaciones.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column("ruta", String(500), nullable=False)
    caption: Mapped[str] = mapped_column("leyenda", String(120), nullable=False, default="")
    position: Mapped[int] = mapped_column("posicion", Integer, nullable=False, default=0)
    room: Mapped[Room] = relationship(back_populates="photos")
    asset: Mapped[Optional["RoomPhotoAsset"]] = relationship(
        back_populates="photo", cascade="all, delete-orphan", uselist=False
    )


class RoomPhotoAsset(Base):
    """Persistent image bytes shared by the API and desktop clients."""
    __tablename__ = "archivos_foto_habitacion"

    photo_id: Mapped[int] = mapped_column("foto_id", ForeignKey("fotos_habitacion.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column("contenido", LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), nullable=False, deferred=True)
    mime_type: Mapped[str] = mapped_column("tipo_mime", String(80), nullable=False)
    sha256: Mapped[str] = mapped_column("resumen_sha256", String(64), nullable=False)
    photo: Mapped[RoomPhoto] = relationship(back_populates="asset")


class Guest(Base):
    __tablename__ = "huespedes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column("nombre", String(80), nullable=False, index=True)
    email: Mapped[str] = mapped_column("correo", String(160), unique=True, nullable=False, index=True)
    phone: Mapped[Optional[str]] = mapped_column("telefono", String(30), nullable=True)
    document_number: Mapped[Optional[str]] = mapped_column("numero_documento", String(40), nullable=True)
    active: Mapped[bool] = mapped_column("activo", Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=datetime.now, nullable=False)
    reservations: Mapped[list["Reservation"]] = relationship(back_populates="guest")


class Reservation(Base):
    __tablename__ = "reservas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column("codigo", String(24), unique=True, nullable=False, index=True)
    guest_id: Mapped[int] = mapped_column("huesped_id", ForeignKey("huespedes.id"), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column("habitacion_id", ForeignKey("habitaciones.id"), nullable=False, index=True)
    check_in: Mapped[date] = mapped_column("fecha_entrada", Date, nullable=False)
    check_out: Mapped[date] = mapped_column("fecha_salida", Date, nullable=False)
    guest_count: Mapped[int] = mapped_column("cantidad_huespedes", Integer, nullable=False, default=1)
    total_amount: Mapped[Decimal] = mapped_column("importe_total", Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column("estado", String(24), nullable=False, default="Confirmada", index=True)
    payment_status: Mapped[str] = mapped_column("estado_pago", String(24), nullable=False, default="Pagado")
    source: Mapped[str] = mapped_column("origen",
        String(24), nullable=False, default="Administración", server_default="Administración"
    )
    created_at: Mapped[datetime] = mapped_column("creado_en", DateTime, default=datetime.now, nullable=False)

    guest: Mapped[Guest] = relationship(back_populates="reservations")
    room: Mapped[Room] = relationship(back_populates="reservations")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="reservation", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "pagos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reservation_id: Mapped[int] = mapped_column("reserva_id",
        ForeignKey("reservas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column("importe", Numeric(10, 2), nullable=False)
    method: Mapped[str] = mapped_column("metodo", String(32), nullable=False, default="Tarjeta")
    status: Mapped[str] = mapped_column("estado", String(24), nullable=False, default="Pagado")
    reference: Mapped[Optional[str]] = mapped_column("referencia", String(80), nullable=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column("pagado_en", DateTime, nullable=True)
    reservation: Mapped[Reservation] = relationship(back_populates="payments")


class BookingHold(Base):
    __tablename__ = "bloqueos_reserva"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column("usuario_id", ForeignKey("usuarios_app.id"), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column("habitacion_id", ForeignKey("habitaciones.id", ondelete="CASCADE"), nullable=False, index=True)
    check_in: Mapped[date] = mapped_column("fecha_entrada", Date, nullable=False)
    check_out: Mapped[date] = mapped_column("fecha_salida", Date, nullable=False)
    guest_count: Mapped[int] = mapped_column("cantidad_huespedes", Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column("expira_en", DateTime, nullable=False, index=True)
    reservation_id: Mapped[Optional[int]] = mapped_column("reserva_id", ForeignKey("reservas.id"), nullable=True, unique=True)
