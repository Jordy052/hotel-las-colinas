"""HTTPS delivery for hosting plans that block outbound SMTP."""
from email.message import EmailMessage
import json
from urllib.request import Request, urlopen
from hotel_admin import config

def validate_settings() -> None:
    if not config.EMAIL_FROM:
        raise ValueError("El remitente del hotel aún no está configurado.")
    if config.EMAIL_PROVIDER == "brevo":
        if not config.BREVO_API_KEY:
            raise ValueError("El correo del hotel aún no está configurado en el alojamiento.")
    elif config.EMAIL_PROVIDER == "smtp":
        if not config.SMTP_HOST or bool(config.SMTP_USERNAME) != bool(config.SMTP_PASSWORD):
            raise ValueError("La configuración de correo del hotel está incompleta.")
    else:
        raise ValueError("El proveedor de correo configurado no es válido.")

def send_https(message: EmailMessage) -> None:
    validate_settings()
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
