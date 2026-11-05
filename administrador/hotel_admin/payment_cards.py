"""Tarjeta recordada por cuenta para el flujo de pago del hotel."""
import re
from uuid import uuid4
from sqlalchemy import select
from hotel_admin import billing
from hotel_admin.models import AppUser, SavedCard


def normalize_card(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Revisa los datos de la tarjeta.")
    if set(data) - {"holder", "last4", "expiry", "billing"}:
        raise ValueError("La tarjeta guardada solo admite titular, terminación, vencimiento y facturación.")
    def field(source, key, minimum, maximum):
        value = source.get(key, "")
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            raise ValueError("Revisa los datos de la tarjeta y su dirección de facturación.")
        return value.strip()
    holder = field(data, "holder", 2, 60)
    last_four = field(data, "last4", 4, 4)
    if re.fullmatch(r"[0-9]{4}", last_four) is None:
        raise ValueError("La terminación de la tarjeta debe tener cuatro dígitos.")
    expiry = field(data, "expiry", 5, 5)
    match = re.fullmatch(r"(0[1-9]|1[0-2])/([0-9]{2})", expiry)
    if not match:
        raise ValueError("Escribe el vencimiento con el formato MM/AA.")
    month, year = int(match[1]), 2000 + int(match[2])
    now = billing.hotel_now()
    if (year, month) < (now.year, now.month):
        raise ValueError("La tarjeta está vencida. Agrega otra tarjeta.")
    address = data.get("billing")
    if not isinstance(address, dict) or set(address) - {"email", "phone", "country", "city", "address", "region", "postal"}:
        raise ValueError("Revisa la dirección de facturación.")
    contact = {key: field(address, key, minimum, maximum) for key, minimum, maximum in (
        ("email", 3, 254), ("phone", 0, 30), ("country", 2, 80), ("city", 2, 80),
        ("address", 3, 180), ("region", 0, 80), ("postal", 0, 16),
    )}
    if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact["email"]) is None:
        raise ValueError("Escribe un correo de facturación válido.")
    if contact["phone"] and (re.fullmatch(r"\+?[0-9 ()-]+", contact["phone"]) is None or not 7 <= len(re.sub(r"\D", "", contact["phone"])) <= 15):
        raise ValueError("Escribe un teléfono de facturación válido.")
    if contact["postal"] and re.fullmatch(r"[A-Za-z0-9 -]{2,16}", contact["postal"]) is None:
        raise ValueError("Revisa el código postal de facturación.")
    return {"holder": holder, "last_four": last_four, "expiry_month": month, "expiry_year": year, "billing": contact}


def is_expired(card: SavedCard) -> bool:
    now = billing.hotel_now()
    return (card.expiry_year, card.expiry_month) < (now.year, now.month)


def describe(card: SavedCard) -> dict:
    return {"token": card.token, "holder": card.holder, "last4": card.last_four,
            "expiry": f"{card.expiry_month:02d}/{card.expiry_year % 100:02d}",
            "billing": dict(card.billing), "expired": is_expired(card)}


def save_card(session, user_id: int, data: dict) -> SavedCard:
    values = normalize_card(data)
    session.scalar(select(AppUser.id).where(AppUser.id == user_id).with_for_update())
    card = session.get(SavedCard, user_id)
    if card is None:
        card = SavedCard(user_id=user_id, created_at=billing.hotel_now())
        session.add(card)
    for name, value in values.items():
        setattr(card, name, value)
    card.token = uuid4().hex
    card.updated_at = billing.hotel_now()
    return card


def require_saved_card(session, user_id: int, token: str) -> SavedCard:
    card = session.get(SavedCard, user_id)
    if card is None or not isinstance(token, str) or card.token != token:
        raise ValueError("La tarjeta guardada cambió o fue eliminada. Vuelve a seleccionarla o agrega otra.")
    if is_expired(card):
        raise ValueError("La tarjeta guardada está vencida. Agrega otra tarjeta.")
    return card
