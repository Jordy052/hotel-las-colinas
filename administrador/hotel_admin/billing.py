"""Shared simulated charges, cancellation policy and signed refund ledger."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from hotel_admin.models import Payment, Reservation

FEE_RATE = Decimal("0.30")
MONEY = Decimal("0.01")
CASHFLOW_STATES = ("Pagado", "Reembolsado")
FEE_STATE = "Cargo cancelación"


def hotel_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=-6), "America/Managua")).replace(tzinfo=None)


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def add_months(day: date, months: int = 8) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def validate_booking_dates(arrival: date, departure: date, now=None) -> None:
    today = (now or hotel_now()).date()
    horizon = add_months(today)
    if arrival < today or departure <= arrival:
        raise ValueError("La entrada debe ser desde hoy y la salida debe ser posterior a la entrada.")
    if arrival >= horizon or departure > horizon:
        raise ValueError("Solo se permiten estancias dentro de los próximos 8 meses del calendario.")


def arrival_at(reservation) -> datetime:
    return datetime.combine(reservation.check_in, time(14, 0))


def free_deadline(reservation) -> datetime:
    created = reservation.created_at
    anticipation = max(timedelta(0), arrival_at(reservation) - created)
    # Integer microseconds avoid floating point drift; round down to whole seconds.
    microseconds = ((anticipation.days * 86400 + anticipation.seconds) * 1000000 + anticipation.microseconds)
    seconds = (microseconds * 3 // 7) // 1000000
    return created + timedelta(seconds=seconds)


def cancellation_quote(reservation, now=None) -> dict:
    now = now or hotel_now()
    paid = sum((money(p.amount) for p in reservation.payments if p.status == "Pagado" and p.amount > 0), Decimal("0"))
    deadline = free_deadline(reservation)
    is_free = now <= deadline
    fee = Decimal("0") if is_free else min(paid, money(money(reservation.total_amount) * FEE_RATE))
    return {"paidAmount": float(paid), "cancellationFee": float(fee), "refundAmount": float(paid - fee),
            "deadline": deadline.isoformat(), "isFree": is_free, "feePercentage": 30, "simulated": True}


def cancellation_summary(reservation) -> dict:
    paid = sum((money(p.amount) for p in reservation.payments if p.status == "Pagado" and p.amount > 0), Decimal("0"))
    refund = sum((abs(money(p.amount)) for p in reservation.payments if p.status == "Reembolsado"), Decimal("0"))
    fee = sum((money(p.amount) for p in reservation.payments if p.status == FEE_STATE), Decimal("0"))
    return {"paidAmount": float(paid), "cancellationFee": float(fee), "refundAmount": float(refund),
            "deadline": free_deadline(reservation).isoformat(), "isFree": fee == 0, "feePercentage": 30, "simulated": True}


def settle_cancellation(session, reservation, now=None, *, reconstruct=False) -> dict:
    now = now or hotel_now()
    if reservation.status == "Cancelada" and not reconstruct:
        return cancellation_summary(reservation)
    if not reconstruct and reservation.status not in {"Confirmada", "En camino"}:
        raise ValueError("Solo se pueden cancelar reservas que todavía no estén hospedadas.")
    quote = cancellation_quote(reservation, now)
    # Historical test cancellations have no reliable cancellation timestamp.
    # Restore a full simulated refund rather than invent a historical penalty.
    if reconstruct:
        quote.update(cancellationFee=0.0, refundAmount=quote["paidAmount"], isFree=True)
    remaining_fee = money(quote["cancellationFee"])
    for original in list(reservation.payments):
        if original.status != "Pagado" or original.amount <= 0:
            continue
        retained = min(money(original.amount), remaining_fee)
        remaining_fee -= retained
        refund = money(original.amount) - retained
        if retained:
            reservation.payments.append(Payment(amount=retained, method=original.method, status=FEE_STATE,
                reference=f"SIM-FEE-{reservation.id}-{original.id}-{uuid4().hex[:6]}", paid_at=now))
        if refund:
            reservation.payments.append(Payment(amount=-refund, method=original.method, status="Reembolsado",
                reference=f"SIM-REFUND-{reservation.id}-{original.id}-{uuid4().hex[:6]}", paid_at=now))
    reservation.status = "Cancelada"
    if quote["paidAmount"] == 0:
        reservation.payment_status = "Cancelado"
    elif quote["refundAmount"] == quote["paidAmount"]:
        reservation.payment_status = "Reembolsado"
    elif quote["refundAmount"] > 0:
        reservation.payment_status = "Reembolso parcial"
    else:
        reservation.payment_status = "Pagado"
    session.flush()
    return quote


def convert_legacy_simulations(session_factory, now=None) -> dict:
    now = now or hotel_now()
    converted = refunded = 0
    with session_factory() as session:
        reservations = session.scalars(select(Reservation).options(selectinload(Reservation.payments)).where(
            Reservation.source == "Web", Reservation.payment_status.in_(["Pendiente", "Cancelado"])
        ).with_for_update()).all()
        for reservation in reservations:
            was_cancelled = reservation.status == "Cancelada"
            paid = sum((money(p.amount) for p in reservation.payments if p.status == "Pagado" and p.amount > 0), Decimal("0"))
            remaining = max(Decimal("0"), money(reservation.total_amount) - paid)
            for payment in reservation.payments:
                if payment.status not in {"Pendiente", "Cancelado"}:
                    continue
                amount = min(max(Decimal("0"), money(payment.amount)), remaining)
                payment.amount = amount
                payment.status = "Pagado" if amount else "Anulado"
                payment.paid_at = now
                payment.reference = f"SIM-LEGACY-PAY-{reservation.id}-{payment.id}"
                remaining -= amount
            if remaining:
                reservation.payments.append(Payment(amount=remaining, method="Tarjeta", status="Pagado",
                    reference=f"SIM-LEGACY-PAY-{reservation.id}-{uuid4().hex[:8]}", paid_at=now))
            reservation.payment_status = "Pagado"
            session.flush()
            if was_cancelled:
                settle_cancellation(session, reservation, now, reconstruct=True)
                refunded += 1
            converted += 1
        session.commit()
    return {"converted": converted, "refunded": refunded}


CARD_WEB = "Tarjeta web"
CARD_POS = "Tarjeta presencial (TPV/POS)"
PAYMENT_CHANNELS = ("Efectivo", CARD_WEB, CARD_POS, "Transferencia")


def payment_channel(method: str, reservation_source: str) -> str:
    """Describe how the payment was taken, preserving the stored payment method."""
    if method != "Tarjeta":
        return method
    if reservation_source == "Web":
        return CARD_WEB
    if reservation_source in {"Administración", "Presencial"}:
        return CARD_POS
    return "Tarjeta"
