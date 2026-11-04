from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4
import shutil

from sqlalchemy import BigInteger, and_, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload

from hotel_admin import config, checkout, billing
from hotel_admin.config import PHOTO_DIR
from hotel_admin.database import SessionLocal
from hotel_admin.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password
from hotel_admin.models import AppUser, Guest, Payment, Permission, Reservation, Role, Room, RoomPhoto


def _front_desk_payment_reference(session, data: dict[str, Any], method: str) -> str:
    if method == "Transferencia":
        bank = data.get("transfer_bank")
        if bank not in config.TRANSFER_PAYMENT_CHANNELS:
            raise ValueError("Selecciona el banco de la transferencia.")
        reference = config.normalize_payment_reference(str(data.get("payment_reference", "")), bank)
        if data.get("payment_verified") is not True:
            raise ValueError("La referencia y el pago deben comprobarse en la cuenta del hotel.")
        stored = f"{bank}:{reference}"
        # Banpro bank and wallet entries share the duplicate check, including legacy records.
        channels = ("BANPRO", "BANPRO_BANCA") if bank in {"BANPRO", "BANPRO_BANCA"} else (bank,)
        reference_keys = [f"{channel}:{reference}" for channel in channels]
        duplicate = session.scalar(select(Payment.id).where(Payment.method == "Transferencia", func.upper(Payment.reference).in_(reference_keys)).limit(1))
        if duplicate is not None:
            raise ValueError("Ese comprobante o referencia ya fue registrado para el mismo banco.")
        return stored
    if method == "Tarjeta" and data.get("payment_verified") is not True:
        raise ValueError("Confirma que el TPV/POS aprobó el pago por tarjeta.")
    return f"CAJA-{uuid4().hex[:8].upper()}"


def _room_dict(room: Room) -> dict[str, Any]:
    return {
        "id": room.id,
        "number": room.number,
        "category": room.category,
        "rate": float(room.nightly_rate),
        "capacity": room.capacity,
        "bed_count": room.bed_count,
        "bed_type": room.bed_type,
        "status": room.status,
        "description": room.description or "",
        "amenities": list(room.amenities or []),
        "photos": [
            {"path": photo.path, "caption": photo.caption, "position": photo.position}
            for photo in room.photos
        ],
    }


class HotelRepository:
    """Consultas ORM y operaciones transaccionales, fuera de la capa gráfica."""

    @staticmethod
    def staff_accounts(search: str = "") -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = (
                select(AppUser)
                .options(selectinload(AppUser.permissions), joinedload(AppUser.role))
                .where(AppUser.role.has(Role.name == "Recepcionista"))
            )
            if search:
                pattern = f"%{search.strip()}%"
                query = query.where(
                    or_(
                        AppUser.username.ilike(pattern),
                        AppUser.email.ilike(pattern),
                        AppUser.phone.ilike(pattern),
                        AppUser.cedula.ilike(pattern),
                    )
                )
            accounts = session.scalars(query.order_by(AppUser.username)).unique().all()
            return [
                {
                    "id": account.id,
                    "name": account.username,
                    "email": account.email,
                    "cedula": account.cedula or "",
                    "phone": account.phone or "No registrado",
                    "role": account.role.name,
                    "status": "Activa" if account.active else "Suspendida",
                    "permissions": [permission.label for permission in account.permissions],
                }
                for account in accounts
            ]

    @staticmethod
    def save_staff_account(data: dict[str, Any]) -> int:
        with SessionLocal() as session:
            try:
                role = session.scalar(select(Role).where(Role.name == "Recepcionista"))
                if role is None:
                    raise ValueError("No se pudo habilitar la cuenta de recepción. Intenta nuevamente más tarde.")
                name = str(data.get("name", "")).strip()
                email = str(data.get("email", "")).strip().casefold()
                cedula = str(data.get("cedula", "")).strip().upper()
                user_id = data.get("id")
                account = session.get(AppUser, user_id) if user_id else None
                if user_id and (account is None or account.role.name != "Recepcionista"):
                    raise ValueError("La cuenta de recepción ya no existe.")
                is_new_account = account is None
                phone = config.validate_desktop_contact(name, email, str(data.get("phone", "")), staff=True)
                if not 5 <= len(name) <= 30:
                    raise ValueError("El nombre de usuario debe tener entre 5 y 30 caracteres.")
                if not config.is_valid_staff_email(email):
                    raise ValueError(
                        f"El correo de recepción debe tener el formato nombre.apellido@{config.STAFF_EMAIL_DOMAIN}."
                    )
                if not config.is_valid_nicaraguan_cedula(cedula):
                    raise ValueError("La cédula debe tener el formato 000-000000-0000A.")
                duplicate_cedula = session.scalar(
                    select(AppUser.id).where(AppUser.cedula == cedula, AppUser.id != (user_id or 0))
                )
                if duplicate_cedula is not None:
                    raise ValueError("Esa cédula ya está asociada a otra cuenta.")
                duplicate = session.scalar(
                    select(AppUser.id).where(func.lower(AppUser.email) == email, AppUser.id != (user_id or 0))
                )
                if duplicate is not None:
                    raise ValueError("Ese correo ya está asociado a otra cuenta.")
                duplicate_name = session.scalar(
                    select(AppUser.id).where(
                        func.lower(func.trim(AppUser.username)) == name.casefold(),
                        AppUser.id != (user_id or 0),
                    )
                )
                if duplicate_name is not None:
                    raise ValueError("Ese nombre de usuario ya existe. Elige otro.")
                if account is None:
                    password = str(data.get("password", ""))
                    if not password:
                        raise ValueError("Define una contraseña inicial para la cuenta.")
                    account = AppUser(role=role)
                else:
                    password = str(data.get("password", ""))
                if not account.id and not password:
                    raise ValueError("Define una contraseña inicial para la cuenta.")
                if password and not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
                    raise ValueError("La contraseña debe tener entre 12 y 30 caracteres.")
                labels = set(data.get("permissions", []))
                if not labels:
                    raise ValueError("Asigna al menos una sección a la cuenta de recepción.")
                available = session.scalars(select(Permission).where(Permission.label.in_(labels))).all()
                if {permission.label for permission in available} != labels:
                    raise ValueError("La selección contiene un permiso no reconocido.")
                account.username = name
                account.email = email
                account.cedula = cedula
                account.phone = phone or None
                account.active = data.get("status", "Activa") == "Activa"
                account.permissions = available
                if password:
                    account.password_hash = hash_password(password)
                if is_new_account:
                    # Añadirla después de cargar permisos evita que una consulta
                    # provoque un autoflush con username/email aún sin asignar.
                    session.add(account)
                session.commit()
                return account.id
            except (SQLAlchemyError, ValueError):
                session.rollback()
                raise

    @staticmethod
    def set_staff_status(user_id: int, active: bool) -> None:
        with SessionLocal() as session:
            try:
                account = session.scalar(
                    select(AppUser).options(joinedload(AppUser.role)).where(AppUser.id == user_id)
                )
                if account is None or account.role.name != "Recepcionista":
                    raise ValueError("La cuenta de recepción ya no existe.")
                account.active = active
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise

    @staticmethod
    def dashboard() -> dict[str, Any]:
        with SessionLocal() as session:
            total = session.scalar(select(func.count(Room.id)).where(Room.active.is_(True))) or 0
            occupied = session.scalar(select(func.count(Room.id)).where(Room.status == "Ocupada", Room.active.is_(True))) or 0
            available = session.scalar(select(func.count(Room.id)).where(Room.status == "Disponible", Room.active.is_(True))) or 0
            maintenance = session.scalar(select(func.count(Room.id)).where(Room.status == "Mantenimiento", Room.active.is_(True))) or 0
            today = billing.hotel_now().date()
            active_bookings = session.scalar(select(func.count(Reservation.id)).where(Reservation.status.in_(["Confirmada", "En camino", "Hospedado"]))) or 0
            arrivals = session.scalars(
                select(Reservation).options(joinedload(Reservation.guest), joinedload(Reservation.room))
                .where(Reservation.check_in == today, Reservation.status.in_(["Confirmada", "En camino"]))
                .order_by(Reservation.check_in)
            ).unique().all()
            departures = session.scalars(
                select(Reservation).options(joinedload(Reservation.guest), joinedload(Reservation.room))
                .where(Reservation.check_out == today, Reservation.status == "Hospedado")
                .order_by(Reservation.check_out)
            ).unique().all()
            week_start = today - timedelta(days=6)
            week_counts = [0] * 7
            week_start_at = datetime.combine(week_start, datetime.min.time())
            created_dates = session.scalars(
                select(Reservation.created_at).where(Reservation.created_at >= week_start_at)
            ).all()
            for created_at in created_dates:
                created_day = created_at.date()
                day_index = (created_day - week_start).days
                if 0 <= day_index < 7:
                    week_counts[day_index] += 1
            day_names = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
            week_activity = [
                {"label": day_names[(week_start + timedelta(days=index)).weekday()], "value": count}
                for index, count in enumerate(week_counts)
            ]
            month_start = today.replace(day=1)
            income = session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status.in_(billing.CASHFLOW_STATES), Payment.paid_at >= month_start
            )) or Decimal("0")
            cancellation_fees = session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == billing.FEE_STATE, Payment.paid_at >= month_start
            )) or Decimal("0")
            refunds = session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == "Reembolsado", Payment.paid_at >= month_start
            )) or Decimal("0")
            return {
                "total": total, "occupied": occupied, "available": available,
                "maintenance": maintenance, "bookings": active_bookings,
                "income": float(income), "cancellation_fees": float(cancellation_fees), "refunds": float(abs(refunds)), "occupancy": round(occupied * 100 / total) if total else 0,
                "week_activity": week_activity,
                "arrivals": [{"code": r.code, "guest": r.guest.username, "room": f"{r.room.category} · {r.room.number}", "status": r.status} for r in arrivals],
                "departures": [{"code": r.code, "guest": r.guest.username, "room": f"{r.room.category} · {r.room.number}", "status": "Salida"} for r in departures],
            }

    @staticmethod
    def report_summary() -> dict[str, Any]:
        today = billing.hotel_now().date()
        month_start = today.replace(day=1)
        month_start_at = datetime.combine(month_start, datetime.min.time())
        month_starts = []
        for offset in reversed(range(6)):
            year = today.year
            month = today.month - offset
            while month <= 0:
                month += 12
                year -= 1
            month_starts.append(date(year, month, 1))
        first_month_at = datetime.combine(month_starts[0], datetime.min.time())
        month_names = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")

        with SessionLocal() as session:
            payments = session.execute(
                select(Payment.paid_at, Payment.amount, Payment.method, Payment.status, Reservation.source)
                .join(Reservation, Payment.reservation_id == Reservation.id)
                .where(
                    Payment.status.in_(billing.CASHFLOW_STATES),
                    Payment.paid_at.is_not(None),
                    Payment.paid_at >= first_month_at,
                )
            ).all()

            monthly_amounts = {month: Decimal("0") for month in month_starts}
            method_amounts = {method: Decimal("0") for method in billing.PAYMENT_CHANNELS}
            method_counts = {method: 0 for method in method_amounts}
            current_income = Decimal("0")
            current_transactions = 0
            for paid_at, amount, method, payment_status, source in payments:
                method = billing.payment_channel(method, source)
                if paid_at is None:
                    continue
                paid_month = paid_at.date().replace(day=1)
                if paid_month in monthly_amounts:
                    monthly_amounts[paid_month] += Decimal(str(amount))
                if paid_at >= month_start_at:
                    current_income += Decimal(str(amount))
                    current_transactions += int(payment_status == "Pagado")
                    method_amounts[method] = method_amounts.get(method, Decimal("0")) + Decimal(str(amount))
                    method_counts[method] = method_counts.get(method, 0) + int(payment_status == "Pagado")

            reservations = session.execute(
                select(Reservation.id, Reservation.total_amount).where(Reservation.status != "Cancelada")
            ).all()
            paid_by_reservation = dict(
                session.execute(
                    select(Payment.reservation_id, func.coalesce(func.sum(Payment.amount), 0))
                    .where(Payment.status == "Pagado")
                    .group_by(Payment.reservation_id)
                ).all()
            )
            balance = sum(
                (
                    max(Decimal("0"), Decimal(str(total)) - Decimal(str(paid_by_reservation.get(reservation_id, 0))))
                    for reservation_id, total in reservations
                ),
                Decimal("0"),
            )
            completed_stays = session.scalar(
                select(func.count(Reservation.id)).where(
                    Reservation.status == "Finalizada",
                    Reservation.check_out >= month_start,
                    Reservation.check_out <= today,
                )
            ) or 0

            cancellation_fees = session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.status == billing.FEE_STATE, Payment.paid_at >= month_start_at)) or Decimal("0")
            return {
                "cancellation_fees": float(cancellation_fees),
                "income": float(current_income),
                "balance": float(balance),
                "completed_stays": completed_stays,
                "transactions": current_transactions,
                "monthly_revenue": [
                    {"label": month_names[month.month - 1], "amount": float(monthly_amounts[month])}
                    for month in month_starts
                ],
                "payment_methods": [
                    {"method": method, "amount": float(method_amounts[method]), "count": method_counts[method]}
                    for method in method_amounts
                ],
            }

    @staticmethod
    def rooms(search: str = "", status: str = "Todos") -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = select(Room).options(selectinload(Room.photos)).where(Room.active.is_(True))
            if search:
                query = query.where((Room.number.ilike(f"%{search}%")) | (Room.category.ilike(f"%{search}%")))
            if status != "Todos":
                query = query.where(Room.status == status)
            return [_room_dict(x) for x in session.scalars(query.order_by(cast(Room.number, BigInteger), Room.number, Room.id).execution_options(populate_existing=True)).all()]

    @staticmethod
    def save_room(data: dict[str, Any]) -> int:
        with SessionLocal() as session:
            try:
                room = session.get(Room, data.get("id")) if data.get("id") else Room()
                if room is None:
                    raise ValueError("La habitación ya no existe.")
                for key in ("number", "category", "capacity", "bed_count", "bed_type", "status", "description", "amenities"):
                    setattr(room, key, data[key])
                room.nightly_rate = Decimal(str(data["rate"]))
                room.active = True
                if not data.get("id"):
                    session.add(room)
                session.flush()
                if data.get("replace_photos"):
                    room.photos.clear()
                existing = {photo.path for photo in room.photos}
                for position, photo in enumerate(data.get("photos", [])):
                    source = Path(photo)
                    if not source.is_file() or str(source) in existing:
                        continue
                    if source.resolve().parent == PHOTO_DIR.resolve():
                        destination = source
                    else:
                        destination = PHOTO_DIR / f"{room.number}-{uuid4().hex[:10]}{source.suffix.lower()}"
                        shutil.copy2(source, destination)
                    room.photos.append(RoomPhoto(path=str(destination), caption=source.stem, position=position))
                session.commit()
                return room.id
            except SQLAlchemyError:
                session.rollback()
                raise

    @staticmethod
    def delete_room(room_id: int) -> None:
        with SessionLocal() as session:
            try:
                room = session.get(Room, room_id)
                if room is None:
                    return
                if room.reservations:
                    room.active = False
                    room.status = "Inactiva"
                else:
                    session.delete(room)
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise

    @staticmethod
    def reservations(search: str = "", status: str = "Todos") -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = select(Reservation).options(joinedload(Reservation.guest), joinedload(Reservation.room))
            if search:
                query = query.where((Reservation.code.ilike(f"%{search}%")) | Reservation.guest.has(Guest.username.ilike(f"%{search}%")))
            if status != "Todos":
                query = query.where(Reservation.status == status)
            rows = session.scalars(query.order_by(Reservation.check_in.desc())).unique().all()
            return [{"id": r.id, "code": r.code, "guest": r.guest.username, "room": f"{r.room.category} · {r.room.number}", "dates": f"{r.check_in:%d/%m/%Y} - {r.check_out:%d/%m/%Y}", "total": float(r.total_amount), "status": r.status, "payment": r.payment_status, "source": r.source} for r in rows]

    @staticmethod
    def reservation_options() -> dict[str, list[dict[str, Any]]]:
        with SessionLocal() as session:
            guests = session.scalars(select(Guest).where(Guest.active.is_(True)).order_by(Guest.username)).all()
            rooms = session.scalars(select(Room).where(Room.active.is_(True), Room.status == "Disponible").order_by(cast(Room.number, BigInteger), Room.number, Room.id)).all()
            return {
                "guests": [
                    {
                        "id": guest.id,
                        "name": guest.username,
                        "email": guest.email,
                        "phone": guest.phone,
                        "document_number": guest.document_number,
                    }
                    for guest in guests
                ],
                "rooms": [{"id": room.id, "number": room.number, "category": room.category, "capacity": room.capacity, "rate": float(room.nightly_rate)} for room in rooms],
            }

    @staticmethod
    def create_reservation(data: dict[str, Any]) -> int:
        billing.validate_booking_dates(data["check_in"], data["check_out"])
        with SessionLocal() as session:
            try:
                room = session.scalar(select(Room).where(Room.id == data["room_id"]).with_for_update())
                guest = session.get(Guest, data["guest_id"])
                if room is None or not room.active or room.status != "Disponible":
                    raise ValueError("La habitación seleccionada ya no está disponible.")
                if guest is None or not guest.active:
                    raise ValueError("El huésped seleccionado no está disponible.")
                checkout.assert_not_held(session, room.id, data["check_in"], data["check_out"])
                if data["check_in"] < billing.hotel_now().date():
                    raise ValueError("La entrada no puede ser anterior a hoy.")
                if int(data["guest_count"]) < 1:
                    raise ValueError("La reserva debe incluir al menos un huésped.")
                if data["check_out"] <= data["check_in"]:
                    raise ValueError("La salida debe ser posterior a la entrada.")
                if data["guest_count"] > room.capacity:
                    raise ValueError("La cantidad de huéspedes supera la capacidad del cuarto.")
                conflict = session.scalar(select(Reservation.id).where(
                    Reservation.room_id == room.id,
                    Reservation.status.not_in(["Cancelada", "Finalizada"]),
                    and_(Reservation.check_in < data["check_out"], Reservation.check_out > data["check_in"]),
                ).limit(1))
                if conflict:
                    raise ValueError("La habitación ya tiene una reserva en esas fechas.")
                nights = (data["check_out"] - data["check_in"]).days
                total = room.nightly_rate * nights
                received = Decimal(str(data.get("amount_received", 0)))
                method = str(data.get("payment_method") or "").strip()
                if method not in {"Efectivo", "Tarjeta", "Transferencia"}:
                    raise ValueError("Selecciona el método de pago.")
                if not received.is_finite() or received < total or received < 0:
                    raise ValueError("El pago debe cubrir el total de la estancia. No se permiten pagos parciales.")
                if received > total and method != "Efectivo":
                    raise ValueError("El importe con tarjeta o transferencia debe coincidir con el total.")
                payment_reference = _front_desk_payment_reference(session, data, method)
                reservation = Reservation(
                    code=f"HTL-{uuid4().hex[:8].upper()}", guest=guest, room=room,
                    check_in=data["check_in"], check_out=data["check_out"],
                    guest_count=data["guest_count"], total_amount=total,
                    status="Confirmada", payment_status="Pagado", source="Administración", created_at=billing.hotel_now(),
                )
                session.add(reservation)
                session.flush()
                session.add(Payment(
                    reservation=reservation,
                    amount=total,
                    method=method,
                    status="Pagado",
                    reference=payment_reference,
                    paid_at=billing.hotel_now(),
                ))
                session.commit()
                return reservation.id
            except (SQLAlchemyError, ValueError):
                session.rollback()
                raise

    @staticmethod
    def create_walk_in(data: dict[str, Any]) -> dict[str, Any]:
        """Register a paid front-desk stay; future arrivals remain confirmed reservations."""
        billing.validate_booking_dates(data["check_in"], data["check_out"])
        with SessionLocal() as session:
            try:
                today = billing.hotel_now().date()
                check_in = data["check_in"]
                check_out = data["check_out"]
                guest_count = int(data["guest_count"])
                received = Decimal(str(data.get("amount_received", 0)))

                if check_in < today:
                    raise ValueError("La entrada no puede ser anterior a hoy.")
                if check_out <= check_in:
                    raise ValueError("La salida debe ser posterior a la fecha de entrada.")
                if guest_count < 1:
                    raise ValueError("Indica cuántas personas se hospedarán.")
                if not received.is_finite() or received < 0:
                    raise ValueError("El importe recibido no es válido.")

                room = session.scalar(
                    select(Room).where(Room.id == data["room_id"]).with_for_update()
                )
                if room is None or not room.active or room.status != "Disponible":
                    raise ValueError("La habitación dejó de estar disponible. Actualiza la lista.")
                if guest_count > room.capacity:
                    raise ValueError("La cantidad de personas supera la capacidad del cuarto.")

                new_guest = data.get("new_guest")
                if new_guest:
                    username = str(new_guest.get("username", "")).strip()
                    email = str(new_guest["email"]).strip().lower()
                    phone = config.validate_desktop_contact(username, email, str(new_guest.get("phone", "")))
                    document = config.normalize_guest_document(str(new_guest.get("document_number", "")))
                    existing_guest = session.scalar(
                        select(Guest).where(func.lower(Guest.email) == email)
                    )
                    if existing_guest:
                        raise ValueError("Ya existe un huésped con ese correo. Selecciónalo de la lista.")
                    guest = Guest(
                        username=username,
                        email=email,
                        phone=phone or None,
                        document_number=document,
                    )
                    session.add(guest)
                    session.flush()
                else:
                    guest = session.get(Guest, data.get("guest_id"))
                    if guest is None or not guest.active:
                        raise ValueError("Selecciona un huésped válido o registra uno nuevo.")

                conflict = session.scalar(
                    select(Reservation.id).where(
                        Reservation.room_id == room.id,
                        Reservation.status.not_in(["Cancelada", "Finalizada"]),
                        and_(Reservation.check_in < check_out, Reservation.check_out > check_in),
                    ).limit(1)
                )
                if conflict:
                    raise ValueError("La habitación tiene otra estancia que coincide con esas fechas.")

                checkout.assert_not_held(session, room.id, check_in, check_out)
                nights = (check_out - check_in).days
                total = room.nightly_rate * nights
                method = str(data.get("payment_method") or "").strip()
                if method not in {"Efectivo", "Tarjeta", "Transferencia"}:
                    raise ValueError("Selecciona el método de pago.")
                if received < total:
                    raise ValueError("El pago debe cubrir el total de la estancia. No se permiten pagos parciales.")
                if received > total and method != "Efectivo":
                    raise ValueError("Solo se permite recibir más del total cuando el método es efectivo.")

                payment_reference = _front_desk_payment_reference(session, data, method)
                change = received - total if method == "Efectivo" else Decimal("0")
                payment_status = "Pagado"
                arrival_status = "Hospedado" if check_in == today else "Confirmada"
                reservation = Reservation(
                    code=f"HTL-{uuid4().hex[:8].upper()}",
                    guest=guest,
                    room=room,
                    check_in=check_in,
                    check_out=check_out,
                    guest_count=guest_count,
                    total_amount=total,
                    status=arrival_status,
                    payment_status=payment_status,
                    source="Presencial",
                    created_at=billing.hotel_now(),
                )
                if arrival_status == "Hospedado":
                    room.status = "Ocupada"
                session.add(reservation)
                session.flush()
                session.add(
                    Payment(
                        reservation=reservation,
                        amount=total,
                        method=method,
                        status="Pagado",
                        reference=payment_reference,
                        paid_at=billing.hotel_now(),
                    )
                )
                session.commit()
                return {
                    "id": reservation.id,
                    "code": reservation.code,
                    "guest": guest.username,
                    "room": room.number,
                    "total": float(total),
                    "received": float(received),
                    "paid_amount": float(total),
                    "change": float(change),
                    "balance": 0.0,
                    "payment_status": payment_status,
                    "status": arrival_status,
                    "method": method,
                    "reference": payment_reference,
                }
            except (SQLAlchemyError, ValueError):
                session.rollback()
                raise

    @staticmethod
    def cancellation_preview(reservation_id: int) -> dict[str, Any]:
        with SessionLocal() as session:
            reservation = session.scalar(select(Reservation).options(selectinload(Reservation.payments)).where(Reservation.id == reservation_id))
            if reservation is None:
                raise ValueError("La reserva ya no existe.")
            return billing.cancellation_summary(reservation) if reservation.status == "Cancelada" else billing.cancellation_quote(reservation)

    @staticmethod
    def cancel_reservation(reservation_id: int, expected_fee=None) -> dict[str, Any]:
        with SessionLocal() as session:
            reservation = session.scalar(select(Reservation).options(selectinload(Reservation.payments)).where(
                Reservation.id == reservation_id).with_for_update())
            if reservation is None:
                raise ValueError("La reserva ya no existe.")
            cancelled_at = billing.hotel_now()
            if expected_fee is not None and reservation.status != "Cancelada":
                if billing.money(expected_fee) != billing.money(billing.cancellation_quote(reservation, cancelled_at)["cancellationFee"]):
                    raise ValueError("El plazo gratuito cambió. Revisa de nuevo el cargo antes de cancelar.")
            result = billing.settle_cancellation(session, reservation, cancelled_at)
            session.commit()
            return result

    @staticmethod
    def update_reservation_status(reservation_id: int, status: str) -> None:
        transitions = {
            "Confirmada": {"Hospedado", "Cancelada"},
            "En camino": {"Hospedado", "Cancelada"},
            "Hospedado": {"Finalizada"},
        }
        if status not in {"Hospedado", "Finalizada"}:
            raise ValueError("Estado de reserva no válido.")
        with SessionLocal() as session:
            try:
                reservation = session.scalar(select(Reservation).options(joinedload(Reservation.room)).where(Reservation.id == reservation_id))
                if reservation is None:
                    raise ValueError("La reserva ya no existe.")
                if status not in transitions.get(reservation.status, set()):
                    raise ValueError(f"No se puede cambiar una reserva de {reservation.status} a {status}.")
                reservation.status = status
                if status == "Hospedado":
                    reservation.room.status = "Ocupada"
                elif status in {"Finalizada", "Cancelada"} and reservation.room.status == "Ocupada":
                    reservation.room.status = "Disponible"
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise

    @staticmethod
    def guests(search: str = "") -> list[dict[str, Any]]:
        with SessionLocal() as session:
            query = select(Guest).options(selectinload(Guest.reservations))
            if search:
                query = query.where((Guest.username.ilike(f"%{search}%")) | (Guest.email.ilike(f"%{search}%")))
            rows = session.scalars(query.order_by(Guest.username)).all()
            return [
                {
                    "id": guest.id,
                    "username": guest.username,
                    "email": guest.email,
                    "phone": guest.phone or "—",
                    "reservations": len(guest.reservations),
                    "stay": "Alojado" if any(reservation.status == "Hospedado" for reservation in guest.reservations) else "No alojado",
                    "active": "Activo" if guest.active else "Inactivo",
                }
                for guest in rows
            ]

    @staticmethod
    def save_guest(data: dict[str, Any]) -> int:
        with SessionLocal() as session:
            try:
                name = str(data.get("username", "")).strip()
                email = str(data.get("email", "")).strip().lower()
                phone = config.validate_desktop_contact(name, email, str(data.get("phone", "")))
                document = config.normalize_guest_document(str(data.get("document_number", "")))
                guest = Guest(username=name, email=email, phone=phone or None, document_number=document)
                session.add(guest)
                session.commit()
                return guest.id
            except SQLAlchemyError:
                session.rollback()
                raise

    @staticmethod
    def payments() -> list[dict[str, Any]]:
        with SessionLocal() as session:
            payments = session.scalars(select(Payment).options(
                joinedload(Payment.reservation).joinedload(Reservation.guest)).order_by(Payment.id.desc())).unique().all()
            rows = []
            for payment in payments:
                status = payment.status
                if status in {"Pendiente", "Cancelado", "Anulado"}:
                    status = "Sin cobro"
                concept = "Pago de reserva"
                if payment.status == "Reembolsado":
                    concept = "Reembolso por cancelación"
                elif payment.status == billing.FEE_STATE:
                    concept = "Cargo de cancelación retenido"
                elif status == "Sin cobro":
                    concept = "Registro sin cobro"
                rows.append({"id": payment.id, "reference": payment.reference or "—", "booking": payment.reservation.code,
                    "guest": payment.reservation.guest.username, "amount": float(payment.amount), "method": billing.payment_channel(payment.method, payment.reservation.source),
                    "status": status, "concept": concept})
            return rows
