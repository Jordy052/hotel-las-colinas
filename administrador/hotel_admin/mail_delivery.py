"""HTTPS delivery for hosting plans that block outbound SMTP."""
from email.message import EmailMessage
import json
import base64
import hashlib
import hmac
import re
import time
from uuid import uuid4
from urllib.request import Request, urlopen
from hotel_admin import config

def validate_settings() -> None:
    if not config.EMAIL_FROM:
        raise ValueError("El remitente del hotel aún no está configurado.")
    if config.EMAIL_PROVIDER == "brevo":
        if not config.BREVO_API_KEY:
            raise ValueError("El correo del hotel aún no está configurado en el alojamiento.")
    elif config.EMAIL_PROVIDER == "google_apps_script":
        if not re.fullmatch(r"https://script\.google\.com/macros/s/[A-Za-z0-9_-]+/exec", config.GOOGLE_MAIL_URL) or len(config.GOOGLE_MAIL_SECRET) < 40:
            raise ValueError("Falta completar la dirección y la clave del correo de Google.")
    elif config.EMAIL_PROVIDER == "smtp":
        if not config.SMTP_HOST or bool(config.SMTP_USERNAME) != bool(config.SMTP_PASSWORD):
            raise ValueError("La configuración de correo del hotel está incompleta.")
    else:
        raise ValueError("El proveedor de correo configurado no es válido.")

def send_https(message: EmailMessage) -> None:
    validate_settings()
    if config.EMAIL_PROVIDER == "google_apps_script":
        google_request({"operation": "send", "to": str(message["To"]), "subject": str(message["Subject"]), "body": message.get_content()})
        return
    if config.EMAIL_PROVIDER != "brevo":
        raise ValueError("Selecciona el proveedor HTTPS de correo.")
    payload = {"sender": {"email": config.EMAIL_FROM, "name": config.HOTEL_NAME},
               "to": [{"email": str(message["To"])}], "subject": str(message["Subject"]),
               "textContent": message.get_content()}
    request = Request("https://api.brevo.com/v3/smtp/email", method="POST",
                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                      headers={"api-key": config.BREVO_API_KEY, "Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
        if response.status != 201 or not result.get("messageId"):
            raise ValueError("El proveedor de correo no confirmó el envío.")


def google_request(payload: dict) -> dict:
    """Authenticated request and response; never transmit the shared secret itself."""
    validate_settings()
    if config.EMAIL_PROVIDER != "google_apps_script":
        raise ValueError("Selecciona el proveedor de correo de Google.")
    request_id = uuid4().hex
    timestamp = int(time.time())
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).decode("ascii")
    secret = config.GOOGLE_MAIL_SECRET.encode("utf-8")
    signature = hmac.new(secret, f"{timestamp}.{request_id}.{encoded}".encode("utf-8"), hashlib.sha256).hexdigest()
    envelope = {"timestamp": timestamp, "requestId": request_id, "payload": encoded, "signature": signature}
    request = Request(config.GOOGLE_MAIL_URL, method="POST", data=json.dumps(envelope).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "application/json"})
    with urlopen(request, timeout=30) as response:
        result = json.loads(response.read(65536))
    data = result.get("payload", "")
    expected = hmac.new(secret, f"response.{request_id}.{data}".encode("utf-8"), hashlib.sha256).hexdigest()
    if result.get("requestId") != request_id or not isinstance(result.get("signature"), str) or not hmac.compare_digest(expected, result["signature"]):
        raise ValueError("Google no devolvió una confirmación de correo válida.")
    result = json.loads(base64.b64decode(data, validate=True).decode("utf-8"))
    if result.get("ok") is not True:
        raise ValueError("El correo de Google no está disponible. Revisa la autorización y la cuota diaria.")
    if payload.get("operation") == "send" and result.get("messageId") != request_id:
        raise ValueError("Google no confirmó el envío del mensaje.")
    return result
