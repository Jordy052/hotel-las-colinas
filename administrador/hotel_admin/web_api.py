"""API local que comparte MySQL entre la web de huéspedes y Administración."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4
import hashlib
import hmac
import json
import mimetypes
import re
import os
import secrets
import smtplib
import ssl
import time

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload, selectinload

from hotel_admin import config, billing, checkout
from hotel_admin.photos import read_photo
from hotel_admin import mail_delivery
from hotel_admin.auth import AuthService
from hotel_admin.database import SessionLocal, initialize_database
from hotel_admin.models import AppUser, Guest, Payment, Reservation, Role, Room, RoomPhoto
from hotel_admin.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, hash_password, verify_password


API_HOST = os.getenv("HOTEL_WEB_API_HOST", "0.0.0.0" if os.getenv("PORT") else "127.0.0.1")
API_PORT = int(os.getenv("PORT") or os.getenv("HOTEL_WEB_API_PORT", "8765"))
PUBLIC_BASE_URL = os.getenv("HOTEL_PUBLIC_BASE_URL", "").strip().rstrip("/")
if PUBLIC_BASE_URL:
    public_url = urlparse(PUBLIC_BASE_URL)
    if public_url.scheme not in {"http", "https"} or not public_url.netloc or public_url.path or public_url.query or public_url.fragment or public_url.username:
        raise RuntimeError("HOTEL_PUBLIC_BASE_URL debe ser el origen de la API, por ejemplo https://api.ejemplo.com.")
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.getenv("HOTEL_ALLOWED_ORIGINS", "http://127.0.0.1:5500,http://localhost:5500").split(",")
    if origin.strip()
}
TOKEN_TTL_SECONDS = 12 * 60 * 60
PASSWORD_RESET_TTL_SECONDS = 10 * 60
PASSWORD_RESET_RESEND_SECONDS = 60
PASSWORD_RESET_MAX_ATTEMPTS = 5
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_RESET_CODE_SECRET = (
    config.PASSWORD_RESET_SECRET.encode("utf-8")
    if config.PASSWORD_RESET_SECRET
    else secrets.token_bytes(32)
)

_sessions: dict[str, tuple[int, float]] = {}
_sessions_lock = RLock()
_password_reset_codes: dict[str, dict[str, object]] = {}
_password_reset_requests_by_email: dict[str, float] = {}
_password_reset_requests_by_ip: dict[str, list[float]] = {}
_password_reset_lock = RLock()


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
        super().__init__(message)


def _password_reset_digest(email: str, code: str) -> bytes:
    message = f"{email.casefold()}:{code}".encode("utf-8")
    return hmac.new(_PASSWORD_RESET_CODE_SECRET, message, hashlib.sha256).digest()


def _send_password_reset_email(email: str, code: str) -> None:
    _validate_email_settings()

    message = EmailMessage()
    message["Subject"] = f"Código para restablecer tu contraseña · {config.HOTEL_NAME}"
    message["From"] = config.EMAIL_FROM
    message["To"] = email
    message.set_content(
        f"Hola,\n\n"
        f"Usa este código para restablecer la contraseña de tu cuenta de {config.HOTEL_NAME}:\n\n"
        f"{code}\n\n"
        "El código vence en 10 minutos y solo puede usarse una vez. "
        "Si no solicitaste este cambio, ignora este mensaje.\n"
    )

    _deliver_security_email(message)


def _validate_email_settings() -> None:
    try:
        mail_delivery.validate_settings()
    except ValueError as error:
        raise ApiError(503, str(error)) from error


def _deliver_security_email(message: EmailMessage) -> None:
    _validate_email_settings()
    if config.EMAIL_PROVIDER in {"brevo", "google_apps_script"}:
        mail_delivery.send_https(message)
        return
    if config.SMTP_PORT == 465:
        server_connection = smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=15,
            context=ssl.create_default_context(),
        )
    else:
        server_connection = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15)

    with server_connection as server:
        server.ehlo()
        if config.SMTP_STARTTLS and config.SMTP_PORT != 465:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.send_message(message)


def _check_password_reset_rate_limit(email: str, remote_ip: str) -> None:
    now = time.time()
    with _password_reset_lock:
        for old_email, requested_at in list(_password_reset_requests_by_email.items()):
            if now - requested_at > 3600:
                _password_reset_requests_by_email.pop(old_email, None)
        for old_ip, request_times in list(_password_reset_requests_by_ip.items()):
            active_times = [requested_at for requested_at in request_times if now - requested_at <= 3600]
            if active_times:
                _password_reset_requests_by_ip[old_ip] = active_times
            else:
                _password_reset_requests_by_ip.pop(old_ip, None)
        email_last = _password_reset_requests_by_email.get(email)
        ip_times = _password_reset_requests_by_ip.get(remote_ip, [])
        if email_last and now - email_last < PASSWORD_RESET_RESEND_SECONDS:
            raise ApiError(429, "Espera un minuto antes de solicitar otro código.")
        if len(ip_times) >= 5:
            raise ApiError(429, "Se solicitaron demasiados códigos desde esta conexión. Intenta más tarde.")
        _password_reset_requests_by_email[email] = now
        _password_reset_requests_by_ip.setdefault(remote_ip, []).append(now)


# Registration codes are purpose-separated from password reset codes.
_registration_codes: dict[str, dict] = {}
_registration_requests_by_email: dict[str, float] = {}
_registration_requests_by_ip: dict[str, list[float]] = {}
_registration_lock = RLock()

def _registration_digest(name, email, phone, password) -> bytes:
    payload = json.dumps([name, email, phone, password], ensure_ascii=False).encode("utf-8")
    return hmac.new(_PASSWORD_RESET_CODE_SECRET, b"registration-payload:" + payload, hashlib.sha256).digest()

def _registration_code_digest(identifier, email, code) -> bytes:
    return hmac.new(_PASSWORD_RESET_CODE_SECRET,
        f"registration-code:{identifier}:{email}:{code}".encode("utf-8"), hashlib.sha256).digest()

def _send_registration_email(email: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = f"Confirma tu correo · {config.HOTEL_NAME}"
    message["From"] = config.EMAIL_FROM
    message["To"] = email
    message.set_content(
        f"Hola,\n\nTu código para crear tu cuenta en {config.HOTEL_NAME} es:\n\n{code}\n\n"
        "Vence en 10 minutos y solo se puede usar una vez. "
        "Al confirmar tu correo, podrás consultar las reservas asociadas a él, "
        "incluidas las registradas en recepción.\n\n"
        "Si no solicitaste crear una cuenta, ignora este mensaje y no compartas el código.\n")
    _deliver_security_email(message)

def _request_registration_verification(email: str, fingerprint: bytes, remote_ip: str) -> dict:
    now = time.time()
    with _registration_lock:
        for identifier, record in list(_registration_codes.items()):
            if record["expires"] <= now:
                _registration_codes.pop(identifier, None)
        for address, requested in list(_registration_requests_by_email.items()):
            if now - requested >= 3600:
                _registration_requests_by_email.pop(address, None)
        for address, requests in list(_registration_requests_by_ip.items()):
            active = [stamp for stamp in requests if now-stamp < 3600]
            if active:
                _registration_requests_by_ip[address] = active
            else:
                _registration_requests_by_ip.pop(address, None)
        previous = _registration_requests_by_email.get(email)
        if previous is not None and now-previous < 60:
            raise ApiError(429, "Espera un minuto antes de solicitar otro código.")
        if len(_registration_requests_by_ip.get(remote_ip, [])) >= 5:
            raise ApiError(429, "Se solicitaron demasiados códigos. Intenta nuevamente más tarde.")
        _registration_requests_by_email[email] = now
        _registration_requests_by_ip.setdefault(remote_ip, []).append(now)
    identifier = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        _send_registration_email(email, code)
    except Exception as error:
        with _registration_lock:
            if _registration_requests_by_email.get(email) == now:
                _registration_requests_by_email.pop(email, None)
        print(f"[web-api] No se pudo enviar el código de registro ({type(error).__name__}).")
        raise ApiError(503, "No se pudo enviar el código. Intenta nuevamente más tarde o contacta al hotel.") from error
    with _registration_lock:
        # A resend invalidates all previous registration codes for the address.
        for old, record in list(_registration_codes.items()):
            if record["email"] == email:
                _registration_codes.pop(old, None)
        _registration_codes[identifier] = {"email": email, "fingerprint": fingerprint,
            "digest": _registration_code_digest(identifier, email, code),
            "expires": time.time()+600, "attempts": 0}
    return {"verificationRequired": True, "verificationId": identifier,
            "expiresIn": 600, "retryAfter": 60,
            "message": "Te enviamos un código para confirmar tu correo. Revisa también el correo no deseado."}

def _verify_registration_code(identifier, email, fingerprint, code) -> None:
    if not isinstance(identifier, str) or len(identifier) > 100:
        raise ApiError(400, "Solicita un nuevo código de verificación.")
    with _registration_lock:
        record = _registration_codes.get(identifier)
        if record is None or record["email"] != email or record["expires"] <= time.time():
            raise ApiError(400, "El código venció o ya no está disponible. Solicita uno nuevo.")
        if record["attempts"] >= 5:
            raise ApiError(429, "Se agotaron los intentos. Solicita un nuevo código.")
        if not hmac.compare_digest(record["fingerprint"], fingerprint):
            raise ApiError(409, "Los datos de registro cambiaron. Solicita un nuevo código.")
        record["attempts"] += 1
        if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code) or not hmac.compare_digest(
            record["digest"], _registration_code_digest(identifier, email, code)):
            raise ApiError(400, "El código no es correcto. Revisa los seis números del correo.")



def _invalidate_user_sessions(user_id: int) -> None:
    with _sessions_lock:
        tokens = [token for token, (session_user_id, _expiry) in _sessions.items()
                  if session_user_id == user_id]
        for token in tokens:
            _sessions.pop(token, None)


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ApiError(400, f"El campo {field} es obligatorio.")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ApiError(400, f"La fecha de {field} no es válida.") from error


def _bed_label(room: Room) -> str:
    plural = "s" if room.bed_count != 1 else ""
    return f"{room.bed_count} cama{plural} {room.bed_type.lower()}"


def _room_payload(room: Room, request_host: str) -> dict:
    fallback_images = {
        "Doble": "doble.png",
        "Matrimonial": "matrimonial.png",
        "Familiar": "familiar.png",
    }
    photos = [
        {
            "url": f"{request_host if request_host.startswith(('https://', 'http://')) else 'http://' + request_host}/api/room-photos/{photo.id}",
            "label": photo.caption or f"Vista {index + 1}",
        }
        for index, photo in enumerate(room.photos)
    ]
    image_url = photos[0]["url"] if photos else (
        f"../img/rooms/{fallback_images.get(room.category, 'doble.png')}"
    )
    return {
        "id": room.id,
        "number": room.number,
        "name": f"Habitación {room.category.lower()}",
        "category": room.category,
        "rate": float(room.nightly_rate),
        "capacity": room.capacity,
        "beds": _bed_label(room),
        "bedCount": room.bed_count,
        "bedType": room.bed_type,
        "description": room.description or "",
        "amenities": list(room.amenities or []),
        "image": image_url,
        "photos": photos or [{"url": image_url, "label": "Vista general"}],
    }


def _reservation_payload(reservation: Reservation, request_host: str) -> dict:
    room_data = _room_payload(reservation.room, request_host)
    nights = (reservation.check_out - reservation.check_in).days
    payment = next((p for p in reservation.payments if p.status == "Pagado" and p.amount > 0), reservation.payments[0] if reservation.payments else None)
    return {
        "id": reservation.id,
        "code": reservation.code,
        "receiptCode": f"COMP-{reservation.code}",
        "roomId": reservation.room_id,
        "room": room_data,
        "roomName": room_data["name"],
        "roomImage": room_data["image"],
        "beds": room_data["beds"],
        "rate": float(reservation.room.nightly_rate),
        "arrival": reservation.check_in.isoformat(),
        "departure": reservation.check_out.isoformat(),
        "guests": reservation.guest_count,
        "nights": nights,
        "total": float(reservation.total_amount),
        "status": reservation.status,
        "paymentStatus": reservation.payment_status,
        "paymentMethod": payment.method if payment else "Tarjeta",
        "simulatedPayment": True,
        "cancellation": billing.cancellation_summary(reservation) if reservation.status == "Cancelada" else billing.cancellation_quote(reservation),
        "canCancel": reservation.status in {"Confirmada", "En camino"} and billing.hotel_now() < billing.arrival_at(reservation),
        "guestName": reservation.guest.username,
        "guestEmail": reservation.guest.email,
        "issuedAt": reservation.created_at.isoformat(),
        "checkInTime": "2:00 p. m.",
        "checkOutTime": "12:00 p. m.",
    }


def _available_rooms(session, request_host: str, arrival: date | None,
                     departure: date | None, guests: int) -> list[dict]:
    query = (
        select(Room)
        .options(selectinload(Room.photos))
        .where(Room.active.is_(True), Room.status.not_in(["Mantenimiento", "Inactiva"]))
    )
    rooms = session.scalars(query.order_by(Room.nightly_rate, Room.number)).unique().all()
    results = []
    for room in rooms:
        if room.capacity < guests:
            continue
        if arrival and departure:
            conflict = session.scalar(
                select(Reservation.id).where(
                    Reservation.room_id == room.id,
                    Reservation.status.not_in(["Cancelada", "Finalizada"]),
                    and_(Reservation.check_in < departure, Reservation.check_out > arrival),
                ).limit(1)
            )
            if conflict:
                continue
        payload = _room_payload(room, request_host)
        if arrival and departure:
            pending = checkout.active_hold(session, room.id, arrival, departure)
            payload["availabilityStatus"] = "Pendiente" if pending else "Disponible"
            payload["availableToBook"] = pending is None
        results.append(payload)
    return results


def _new_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with _sessions_lock:
        _sessions[token] = (user_id, time.time() + TOKEN_TTL_SECONDS)
    return token


def _user_from_token(token: str) -> AppUser:
    with _sessions_lock:
        session_data = _sessions.get(token)
        if not session_data:
            raise ApiError(401, "La sesión venció. Inicia sesión nuevamente.")
        user_id, expires_at = session_data
        if expires_at <= time.time():
            _sessions.pop(token, None)
            raise ApiError(401, "La sesión venció. Inicia sesión nuevamente.")
    with SessionLocal() as session:
        user = session.scalar(
            select(AppUser).options(joinedload(AppUser.role)).where(
                AppUser.id == user_id, AppUser.active.is_(True)
            )
        )
        if user is None or user.role.name != "Usuario":
            raise ApiError(401, "La cuenta no tiene acceso al portal de huéspedes.")
        return user


def _hotel_today() -> date:
    return datetime.now(timezone(timedelta(hours=-6), "America/Managua")).date()


def _mark_reservation_en_route(user: AppUser, code: str) -> dict:
    with SessionLocal() as session:
        reservation = session.scalar(
            select(Reservation).join(Reservation.guest).where(
                Reservation.code == code,
                func.lower(Guest.email) == user.email.casefold(),
            ).with_for_update()
        )
        if reservation is None:
            raise ApiError(404, "No se encontró la reserva.")
        if reservation.check_in < _hotel_today():
            raise ApiError(409, "La fecha de entrada ya pasó. Contacta a recepción para revisar tu reserva.")
        if reservation.status not in {"Confirmada", "En camino"}:
            raise ApiError(409, "Solo una reserva confirmada puede marcarse como En camino.")
        reservation.status = "En camino"
        session.commit()
    return {"ok": True, "status": "En camino"}


def _validated_guest_phone(data: dict) -> str:
    value = str(data.get("phone") or "").strip()
    country = data.get("phoneCountry")
    if country not in config.LATIN_AMERICAN_PHONES:
        raise ApiError(400, "Selecciona el país del teléfono.")
    if not value or len(value) > 30:
        raise ApiError(400, "Escribe tu teléfono de contacto (máximo 30 caracteres).")
    try:
        return config.normalize_contact_phone(value, country)
    except ValueError as error:
        raise ApiError(400, str(error)) from error


class HotelApiHandler(BaseHTTPRequestHandler):
    server_version = "HotelReservationsAPI/1.0"

    def log_message(self, format_string: str, *args) -> None:
        print(f"[web-api] {self.address_string()} {format_string % args}")

    def _cors(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def _json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _fail(self, error: ApiError) -> None:
        self._json(error.status, {"error": error.message})

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                raise ApiError(400, "El contenido de la solicitud no es válido.")
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except ApiError:
            raise
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(400, "El contenido de la solicitud no es JSON válido.") from error
        if not isinstance(value, dict):
            raise ApiError(400, "El contenido de la solicitud no es válido.")
        return value

    def _token(self) -> str:
        scheme, _, token = self.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise ApiError(401, "Inicia sesión para continuar.")
        return token

    def _host(self) -> str:
        return PUBLIC_BASE_URL or f"{API_HOST}:{API_PORT}"

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            if parsed.path == "/api/health":
                self._json(200, {"status": "ok", "database": "MySQL"})
                return

            if parsed.path == "/api/rooms":
                start_text = params.get("check_in", [None])[0]
                end_text = params.get("check_out", [None])[0]
                if bool(start_text) != bool(end_text):
                    raise ApiError(400, "Indica la entrada y la salida.")
                arrival = _parse_date(start_text, "entrada") if start_text else None
                departure = _parse_date(end_text, "salida") if end_text else None
                if arrival and departure and departure <= arrival:
                    raise ApiError(400, "La salida debe ser posterior a la entrada.")
                if arrival and arrival < billing.hotel_now().date():
                    raise ApiError(400, "La entrada no puede ser anterior a hoy.")
                try:
                    guests = max(1, int(params.get("guests", ["1"])[0]))
                except ValueError as error:
                    raise ApiError(400, "La cantidad de huéspedes no es válida.") from error
                with SessionLocal() as session:
                    rooms = _available_rooms(session, self._host(), arrival, departure, guests)
                self._json(200, {"rooms": rooms})
                return

            if parsed.path.startswith("/api/room-photos/"):
                try:
                    photo_id = int(parsed.path.rsplit("/", 1)[1])
                except (ValueError, IndexError) as error:
                    raise ApiError(404, "La fotografía no existe.") from error
                with SessionLocal() as session:
                    photo = session.get(RoomPhoto, photo_id)
                    if photo is None:
                        raise ApiError(404, "La fotografía no existe.")
                    try:
                        content, mime_type = read_photo(photo)
                    except (FileNotFoundError, ValueError) as error:
                        raise ApiError(404, "La fotografía no existe.") from error
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Cache-Control", "public, max-age=300")
                self.end_headers()
                self.wfile.write(content)
                return

            if parsed.path.startswith("/api/booking-holds/"):
                user = _user_from_token(self._token())
                token = unquote(parsed.path.rsplit("/", 1)[1])
                with SessionLocal() as session:
                    hold = checkout.owned_hold(session, user.id, token)
                    result = checkout.describe(hold)
                    if hold.reservation_id:
                        result["code"] = session.get(Reservation, hold.reservation_id).code
                self._json(200, result)
                return

            if parsed.path == "/api/account":
                user = _user_from_token(self._token())
                self._json(200, {"id": user.id, "name": user.username,
                                 "email": user.email, "phone": user.phone or ""})
                return

            if parsed.path == "/api/reservations":
                user = _user_from_token(self._token())
                with SessionLocal() as session:
                    rows = session.scalars(
                        select(Reservation).join(Reservation.guest).options(
                            joinedload(Reservation.guest),
                            joinedload(Reservation.room).selectinload(Room.photos),
                            selectinload(Reservation.payments),
                        ).where(func.lower(Guest.email) == user.email.casefold())
                        .order_by(Reservation.created_at.desc())
                    ).unique().all()
                    result = [_reservation_payload(row, self._host()) for row in rows]
                self._json(200, {"reservations": result})
                return

            if parsed.path.startswith("/api/reservations/") and parsed.path.endswith("/cancellation-preview"):
                code = unquote(parsed.path.split("/")[-2])
                user = _user_from_token(self._token())
                with SessionLocal() as session:
                    reservation = session.scalar(select(Reservation).join(Reservation.guest).options(selectinload(Reservation.payments)).where(
                        Reservation.code == code, func.lower(Guest.email) == user.email.casefold()))
                    if reservation is None:
                        raise ApiError(404, "No se encontró la reserva.")
                    if reservation.status not in {"Confirmada", "En camino"} or billing.hotel_now() >= billing.arrival_at(reservation):
                        raise ApiError(409, "La reserva ya no se puede cancelar desde la web.")
                    quote = billing.cancellation_quote(reservation)
                self._json(200, quote)
                return

            if parsed.path.startswith("/api/reservations/"):
                code = unquote(parsed.path.rsplit("/", 1)[1])
                user = _user_from_token(self._token())
                with SessionLocal() as session:
                    row = session.scalar(
                        select(Reservation).join(Reservation.guest).options(
                            joinedload(Reservation.guest),
                            joinedload(Reservation.room).selectinload(Room.photos),
                            selectinload(Reservation.payments),
                        ).where(
                            Reservation.code == code,
                            func.lower(Guest.email) == user.email.casefold(),
                        )
                    )
                    if row is None:
                        raise ApiError(404, "No se encontró el comprobante.")
                    result = _reservation_payload(row, self._host())
                self._json(200, result)
                return

            raise ApiError(404, "La ruta solicitada no existe.")
        except checkout.CheckoutError as error:
            self._json(error.status, {"error": str(error)})
        except ApiError as error:
            self._fail(error)
        except Exception:
            self._json(500, {"error": "No se pudo consultar la información. Intenta nuevamente más tarde."})

    def do_POST(self) -> None:
        try:
            path = urlparse(self.path).path
            data = self._body()

            if path == "/api/auth/password-reset/request":
                email = str(data.get("email", "")).strip().casefold()
                if not email or len(email) > 160 or not _EMAIL_PATTERN.fullmatch(email):
                    raise ApiError(400, "Escribe un correo electrónico válido.")
                _validate_email_settings()

                _check_password_reset_rate_limit(email, self.client_address[0])
                with SessionLocal() as session:
                    account = session.scalar(
                        select(AppUser).options(joinedload(AppUser.role)).where(
                            func.lower(AppUser.email) == email,
                            AppUser.active.is_(True),
                        )
                    )
                    eligible = account is not None and account.role.name == "Usuario"

                if eligible:
                    code = f"{secrets.randbelow(1_000_000):06d}"
                    try:
                        _send_password_reset_email(email, code)
                    except ApiError:
                        raise
                    except Exception as error:
                        print(f"[web-api] No se pudo enviar el código de recuperación ({type(error).__name__}).")
                        raise ApiError(503, "No se pudo enviar el código. Verifica la configuración de correo e intenta más tarde.") from error
                    with _password_reset_lock:
                        expired_codes = [
                            key for key, value in _password_reset_codes.items()
                            if float(value["expires_at"]) <= time.time()
                        ]
                        for expired_email in expired_codes:
                            _password_reset_codes.pop(expired_email, None)
                        _password_reset_codes[email] = {
                            "digest": _password_reset_digest(email, code),
                            "expires_at": time.time() + PASSWORD_RESET_TTL_SECONDS,
                            "attempts": 0,
                        }

                self._json(202, {
                    "ok": True,
                    "message": "Si el correo está asociado a una cuenta, recibirás un código de verificación.",
                })
                return

            if path == "/api/auth/password-reset/confirm":
                email = str(data.get("email", "")).strip().casefold()
                code = str(data.get("code", "")).strip()
                new_password = str(data.get("newPassword", ""))
                if not email or len(email) > 160 or not _EMAIL_PATTERN.fullmatch(email):
                    raise ApiError(400, "Escribe un correo electrónico válido.")
                if not re.fullmatch(r"\d{6}", code):
                    raise ApiError(400, "El código es incorrecto o venció. Solicita uno nuevo.")
                if len(new_password) < MIN_PASSWORD_LENGTH or len(new_password) > MAX_PASSWORD_LENGTH:
                    raise ApiError(400, f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres.")

                with _password_reset_lock:
                    reset = _password_reset_codes.get(email)
                    now = time.time()
                    if reset is None or float(reset["expires_at"]) <= now:
                        _password_reset_codes.pop(email, None)
                        raise ApiError(400, "El código es incorrecto o venció. Solicita uno nuevo.")

                    digest_matches = hmac.compare_digest(
                        bytes(reset["digest"]),
                        _password_reset_digest(email, code),
                    )
                    if not digest_matches:
                        reset["attempts"] = int(reset["attempts"]) + 1
                        if int(reset["attempts"]) >= PASSWORD_RESET_MAX_ATTEMPTS:
                            _password_reset_codes.pop(email, None)
                        raise ApiError(400, "El código es incorrecto o venció. Solicita uno nuevo.")

                    with SessionLocal() as session:
                        account = session.scalar(
                            select(AppUser).options(joinedload(AppUser.role)).where(
                                func.lower(AppUser.email) == email,
                                AppUser.active.is_(True),
                            )
                        )
                        if account is None or account.role.name != "Usuario":
                            _password_reset_codes.pop(email, None)
                            raise ApiError(400, "El código es incorrecto o venció. Solicita uno nuevo.")
                        account.password_hash = hash_password(new_password)
                        user_id = account.id
                        session.commit()

                    _password_reset_codes.pop(email, None)
                    _invalidate_user_sessions(user_id)

                self._json(200, {"ok": True})
                return

            if path == "/api/account/phone":
                user = _user_from_token(self._token())
                phone = _validated_guest_phone(data)
                with SessionLocal() as session:
                    account = session.scalar(select(AppUser).where(AppUser.id == user.id).with_for_update())
                    if account is None or not account.active:
                        raise ApiError(401, "La cuenta ya no está disponible.")
                    account.phone = phone
                    guest = session.scalar(select(Guest).where(func.lower(Guest.email) == account.email.casefold()).with_for_update())
                    if guest is None:
                        guest = Guest(username=account.username, email=account.email, phone=phone, active=True)
                        session.add(guest)
                    else:
                        guest.phone = phone
                    result = {"id": account.id, "name": account.username, "email": account.email, "phone": phone}
                    session.commit()
                self._json(200, result)
                return

            if path == "/api/auth/register":
                name = str(data.get("name", "")).strip()
                email = str(data.get("email", "")).strip().casefold()
                password = str(data.get("password", ""))
                if len(name) < 5 or len(name) > 30:
                    raise ApiError(400, "El nombre de usuario debe tener entre 5 y 30 caracteres.")
                if len(email) > 160 or not _EMAIL_PATTERN.fullmatch(email):
                    raise ApiError(400, "Escribe un correo electrónico válido de hasta 160 caracteres.")
                if len(password) < MIN_PASSWORD_LENGTH or len(password) > MAX_PASSWORD_LENGTH:
                    raise ApiError(400, f"La contraseña debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres.")
                phone = _validated_guest_phone(data)
                fingerprint = _registration_digest(name, email, phone, password)
                with SessionLocal() as session:
                    role = session.scalar(select(Role).where(Role.name == "Usuario"))
                    if role is None:
                        raise ApiError(500, "No se pudo crear la cuenta. Intenta nuevamente más tarde.")
                    if session.scalar(select(AppUser.id).where(func.lower(AppUser.email) == email)):
                        raise ApiError(409, "Ya existe una cuenta con ese correo. Inicia sesión.")
                    if session.scalar(
                        select(AppUser.id).where(func.lower(func.trim(AppUser.username)) == name.casefold())
                    ):
                        raise ApiError(409, "Ese nombre de usuario ya existe. Elige otro.")
                    verification_id = data.get("verificationId")
                    if not verification_id:
                        session.rollback()
                        proof = _request_registration_verification(email, fingerprint, self.client_address[0])
                        self._json(202, proof)
                        return
                    _verify_registration_code(verification_id, email, fingerprint, data.get("verificationCode"))
                    encoded_password = hash_password(password)
                    guest = session.scalar(select(Guest).where(func.lower(Guest.email) == email).with_for_update())
                    if guest is not None and not guest.active:
                        raise ApiError(403, "El perfil del huésped no está habilitado. Contacta al hotel.")
                    if guest is None:
                        guest = Guest(username=name, email=email, phone=phone, active=True)
                        session.add(guest)
                    else:
                        guest.username = name
                        guest.phone = phone
                        guest.active = True
                    account = AppUser(username=name, email=email, phone=phone, password_hash=encoded_password,
                                      active=True, role=role)
                    session.add(account)
                    try:
                        session.commit()
                    except IntegrityError as error:
                        session.rollback()
                        if "uq_app_users_username" in str(error.orig).casefold():
                            raise ApiError(409, "Ese nombre de usuario ya existe. Elige otro.") from error
                        raise ApiError(409, "Ya existe una cuenta con ese correo.") from error
                    user_id = account.id
                    with _registration_lock:
                        _registration_codes.pop(verification_id, None)
                token = _new_token(user_id)
                self._json(201, {"token": token, "user": {"id": user_id, "name": name, "email": email, "phone": phone}})
                return

            if path == "/api/auth/login":
                email = str(data.get("email", "")).strip().casefold()
                password = str(data.get("password", ""))
                if not email or len(email) > 160 or not _EMAIL_PATTERN.fullmatch(email):
                    raise ApiError(400, "Escribe un correo electrónico válido.")
                if not password or len(password) > MAX_PASSWORD_LENGTH:
                    raise ApiError(400, f"Escribe tu contraseña (máximo {MAX_PASSWORD_LENGTH} caracteres).")
                user = AuthService.authenticate(email, password)
                if user is None:
                    raise ApiError(401, "Correo o contraseña incorrectos.")
                if user["role"] != "Usuario":
                    raise ApiError(403, "Esta cuenta pertenece al personal del hotel.")
                token = _new_token(user["id"])
                self._json(200, {
                    "token": token,
                    "user": {"id": user["id"], "name": user["name"], "email": user["email"]},
                })
                return

            if path == "/api/auth/change-password":
                user = _user_from_token(self._token())
                current = str(data.get("currentPassword", ""))
                new_password = str(data.get("newPassword", ""))
                if not current or len(current) > MAX_PASSWORD_LENGTH:
                    raise ApiError(400, f"Escribe tu contraseña actual (máximo {MAX_PASSWORD_LENGTH} caracteres).")
                if len(new_password) < MIN_PASSWORD_LENGTH or len(new_password) > MAX_PASSWORD_LENGTH:
                    raise ApiError(400, f"La contraseña nueva debe tener entre {MIN_PASSWORD_LENGTH} y {MAX_PASSWORD_LENGTH} caracteres.")
                with SessionLocal() as session:
                    account = session.get(AppUser, user.id)
                    if account is None or not verify_password(current, account.password_hash):
                        raise ApiError(401, "La contraseña actual es incorrecta.")
                    if current == new_password:
                        raise ApiError(400, "La contraseña nueva debe ser distinta de la actual.")
                    account.password_hash = hash_password(new_password)
                    session.commit()
                self._json(200, {"ok": True})
                return

            if path == "/api/auth/logout":
                token = self._token()
                with _sessions_lock:
                    _sessions.pop(token, None)
                self._json(200, {"ok": True})
                return

            if path.startswith("/api/booking-holds/") and path.endswith("/release"):
                user = _user_from_token(self._token())
                token = unquote(path.split("/")[-2])
                self._json(200, checkout.release(SessionLocal, user.id, token))
                return

            if path == "/api/booking-holds":
                user = _user_from_token(self._token())
                arrival = _parse_date(data.get("arrival"), "entrada")
                departure = _parse_date(data.get("departure"), "salida")
                try:
                    result = checkout.acquire(SessionLocal, user.id, int(data.get("roomId")), arrival,
                        departure, int(data.get("guests")), data.get("holdToken"))
                except (TypeError, ValueError) as error:
                    if isinstance(error, checkout.CheckoutError):
                        raise
                    raise ApiError(400, str(error)) from error
                if result.get("reservationId"):
                    with SessionLocal() as session:
                        result["code"] = session.get(Reservation, result["reservationId"]).code
                self._json(200, result)
                return

            if path == "/api/reservations":
                user = _user_from_token(self._token())
                arrival = _parse_date(data.get("arrival"), "entrada")
                departure = _parse_date(data.get("departure"), "salida")
                if departure <= arrival:
                    raise ApiError(400, "La salida debe ser posterior a la entrada.")
                if data.get("simulatePayment") is not True:
                    raise ApiError(400, "Confirma el pago completo para registrar la reserva.")
                try:
                    room_id = int(data.get("roomId"))
                    guests = int(data.get("guests"))
                except (TypeError, ValueError) as error:
                    raise ApiError(400, "La habitación o la cantidad de huéspedes no es válida.") from error
                if guests < 1:
                    raise ApiError(400, "Indica al menos un huésped.")

                with SessionLocal() as session:
                    room = session.scalar(
                        select(Room).options(selectinload(Room.photos))
                        .where(Room.id == room_id).with_for_update()
                    )
                    if room is None:
                        raise ApiError(404, "No se encontró la habitación.")
                    hold = checkout.lock_for_payment(session, user.id, data.get("checkoutToken"),
                        room_id, arrival, departure, guests)
                    if hold.reservation_id:
                        existing = session.get(Reservation, hold.reservation_id)
                        self._json(200, _reservation_payload(existing, self._host()))
                        return
                    if not room.active or room.status in ("Mantenimiento", "Inactiva"):
                        raise ApiError(409, "La habitación ya no está disponible.")
                    if guests > room.capacity:
                        raise ApiError(400, "La cantidad de huéspedes supera la capacidad del cuarto.")
                    try:
                        billing.validate_booking_dates(arrival, departure)
                    except ValueError as error:
                        raise ApiError(400, str(error)) from error
                    conflict = session.scalar(
                        select(Reservation.id).where(
                            Reservation.room_id == room.id,
                            Reservation.status.not_in(["Cancelada", "Finalizada"]),
                            and_(Reservation.check_in < departure, Reservation.check_out > arrival),
                        ).limit(1)
                    )
                    if conflict:
                        raise ApiError(409, "La habitación ya fue reservada para esas fechas.")
                    guest = session.scalar(
                        select(Guest).where(func.lower(Guest.email) == user.email.casefold())
                    )
                    if guest is None:
                        guest = Guest(username=user.username, email=user.email,
                                      phone=user.phone, active=True)
                        session.add(guest)
                    if not guest.active:
                        raise ApiError(403, "El perfil del huésped está deshabilitado.")
                    nights = (departure - arrival).days
                    total = Decimal(room.nightly_rate) * nights
                    reservation = Reservation(
                        code=f"HTL-{uuid4().hex[:8].upper()}",
                        guest=guest,
                        room=room,
                        check_in=arrival,
                        check_out=departure,
                        guest_count=guests,
                        total_amount=total,
                        status="Confirmada",
                        payment_status="Pagado",
                        source="Web",
                        created_at=billing.hotel_now(),
                    )
                    session.add(reservation)
                    session.flush()
                    session.add(Payment(
                        reservation=reservation,
                        amount=total,
                        method="Tarjeta",
                        status="Pagado",
                        reference=f"SIM-PAY-{uuid4().hex[:16].upper()}",
                        paid_at=billing.hotel_now(),
                    ))
                    hold.reservation_id = reservation.id
                    session.commit()
                    reservation_id = reservation.id
                    row = session.scalar(
                        select(Reservation).options(
                            joinedload(Reservation.guest),
                            joinedload(Reservation.room).selectinload(Room.photos),
                            selectinload(Reservation.payments),
                        ).where(Reservation.id == reservation_id)
                    )
                    result = _reservation_payload(row, self._host())
                self._json(201, result)
                return

            if path.startswith("/api/reservations/") and path.endswith("/en-route"):
                code = unquote(path.split("/")[-2])
                user = _user_from_token(self._token())
                self._json(200, _mark_reservation_en_route(user, code))
                return

            if path.startswith("/api/reservations/") and path.endswith("/cancel"):
                code = unquote(path.split("/")[-2])
                user = _user_from_token(self._token())
                with SessionLocal() as session:
                    reservation = session.scalar(select(Reservation).join(Reservation.guest).options(selectinload(Reservation.payments)).where(
                        Reservation.code == code, func.lower(Guest.email) == user.email.casefold()).with_for_update())
                    if reservation is None:
                        raise ApiError(404, "No se encontró la reserva.")
                    cancelled_at = billing.hotel_now()
                    if reservation.status != "Cancelada" and cancelled_at >= billing.arrival_at(reservation):
                        raise ApiError(409, "La reserva ya comenzó. Contacta a recepción.")
                    if reservation.status != "Cancelada":
                        expected = data.get("acceptedCancellationFee")
                        if expected is None or billing.money(expected) != billing.money(billing.cancellation_quote(reservation, cancelled_at)["cancellationFee"]):
                            raise ApiError(409, "Revisa y confirma el cargo de cancelación actualizado.")
                    try:
                        quote = billing.settle_cancellation(session, reservation, cancelled_at)
                    except ValueError as error:
                        raise ApiError(409, str(error)) from error
                    session.commit()
                self._json(200, {"ok": True, "status": "Cancelada", "cancellation": quote})
                return

            raise ApiError(404, "La ruta solicitada no existe.")
        except checkout.CheckoutError as error:
            self._json(error.status, {"error": str(error)})
        except ApiError as error:
            self._fail(error)
        except Exception:
            self._json(500, {"error": "No se pudo guardar la información. Intenta nuevamente más tarde."})


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer((API_HOST, API_PORT), HotelApiHandler)
    print(f"API web activa: http://{API_HOST}:{API_PORT}")
    print("Base de datos: configuración de administrador/.env")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAPI web detenida.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
