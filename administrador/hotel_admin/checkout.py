"""Durable room holds and one reservation/payment per checkout token."""
from datetime import timedelta
from secrets import token_hex
from sqlalchemy import select
from hotel_admin import billing
from hotel_admin.models import BookingHold, Reservation, Room

HOLD_MINUTES = 10

class CheckoutError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status

def active_hold(session, room_id, arrival, departure, now=None):
    return session.scalar(select(BookingHold).where(
        BookingHold.room_id == room_id, BookingHold.reservation_id.is_(None),
        BookingHold.expires_at > (now or billing.hotel_now()),
        BookingHold.check_in < departure, BookingHold.check_out > arrival,
    ).with_for_update().limit(1))

def assert_not_held(session, room_id, arrival, departure):
    if active_hold(session, room_id, arrival, departure):
        raise CheckoutError(409, "La habitación está pendiente de pago por otro usuario. Elige otra o intenta más tarde.")

def describe(hold, now=None):
    now = now or billing.hotel_now()
    return {"holdToken": hold.token, "expiresAt": hold.expires_at.isoformat() + "-06:00",
            "serverNow": now.isoformat() + "-06:00", "state": "Completada" if hold.reservation_id else
            ("Pendiente" if hold.expires_at > now else "Vencida"), "reservationId": hold.reservation_id}

def owned_hold(session, user_id, token, *, locked=False):
    query = select(BookingHold).where(BookingHold.token == token, BookingHold.user_id == user_id)
    hold = session.scalar(query.with_for_update() if locked else query)
    if hold is None:
        raise CheckoutError(404, "No se encontró el apartado de la habitación.")
    return hold

def check_payload(hold, room_id, arrival, departure, guests):
    if (hold.room_id, hold.check_in, hold.check_out, hold.guest_count) != (room_id, arrival, departure, guests):
        raise CheckoutError(409, "Los datos no coinciden con el apartado. Vuelve a seleccionar la habitación.")

def acquire(session_factory, user_id, room_id, arrival, departure, guests, token=None):
    billing.validate_booking_dates(arrival, departure)
    with session_factory() as session:
        # All checkout and front-desk writers lock the room first.
        room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
        if room is None or not room.active or room.status in {"Mantenimiento", "Inactiva"}:
            raise CheckoutError(409, "La habitación no está disponible.")
        if not 1 <= guests <= room.capacity:
            raise CheckoutError(400, "La cantidad de huéspedes no es válida para esta habitación.")
        if token:
            hold = owned_hold(session, user_id, token, locked=True)
            check_payload(hold, room_id, arrival, departure, guests)
            if hold.reservation_id or hold.expires_at > billing.hotel_now():
                return describe(hold)
            raise CheckoutError(409, "El apartado venció. Vuelve a seleccionar la habitación.")
        conflict = session.scalar(select(Reservation.id).where(Reservation.room_id == room_id,
            Reservation.status.not_in(["Cancelada", "Finalizada"]), Reservation.check_in < departure,
            Reservation.check_out > arrival).with_for_update().limit(1))
        if conflict:
            raise CheckoutError(409, "La habitación ya está reservada para esas fechas.")
        pending = active_hold(session, room_id, arrival, departure)
        if pending:
            if pending.user_id == user_id:
                check_payload(pending, room_id, arrival, departure, guests)
                return describe(pending)
            raise CheckoutError(409, "La habitación está pendiente de pago por otro usuario. Elige otra o intenta más tarde.")
        hold = BookingHold(token=token_hex(32), user_id=user_id, room_id=room_id,
            check_in=arrival, check_out=departure, guest_count=guests,
            expires_at=billing.hotel_now() + timedelta(minutes=HOLD_MINUTES))
        session.add(hold)
        session.commit()
        return describe(hold)

def release(session_factory, user_id, token):
    with session_factory() as session:
        snapshot = owned_hold(session, user_id, token)
        session.scalar(select(Room.id).where(Room.id == snapshot.room_id).with_for_update())
        hold = owned_hold(session, user_id, token, locked=True)
        if hold.reservation_id is None:
            hold.expires_at = min(hold.expires_at, billing.hotel_now())
        session.commit()
        return describe(hold)

def lock_for_payment(session, user_id, token, room_id, arrival, departure, guests):
    if not isinstance(token, str) or len(token) != 64:
        raise CheckoutError(400, "Aparta la habitación antes de confirmar el pago.")
    hold = owned_hold(session, user_id, token, locked=True)
    check_payload(hold, room_id, arrival, departure, guests)
    if not hold.reservation_id and hold.expires_at <= billing.hotel_now():
        raise CheckoutError(409, "El apartado venció. No se registró el pago; vuelve a seleccionar una habitación.")
    return hold
