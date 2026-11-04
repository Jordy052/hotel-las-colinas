from pathlib import Path
import os
import re


APP_DIR = Path(__file__).resolve().parent.parent

env_file = APP_DIR / ".env"
if env_file.exists():
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

# Optional storage mount for hosting. Local installations keep their existing directory.
STORAGE_DIR = Path(os.getenv("HOTEL_STORAGE_DIR", str(APP_DIR / "storage"))).resolve()
PHOTO_DIR = STORAGE_DIR / "room_photos"
PHOTO_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1").strip()
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "hotel_reservas").strip()
MYSQL_CONNECT_TIMEOUT = int(os.getenv("MYSQL_CONNECT_TIMEOUT", "5"))
MYSQL_SSL = os.getenv("MYSQL_SSL", "false").lower() in {"1", "true", "yes", "on"}
MYSQL_SSL_CA = os.getenv("MYSQL_SSL_CA", "").strip()
MYSQL_SSL_CA_PEM = os.getenv("MYSQL_SSL_CA_PEM", "").strip()

BOOTSTRAP_ADMIN_EMAIL = os.getenv("HOTEL_BOOTSTRAP_ADMIN_EMAIL", "admin@hotel.local").strip().lower()
BOOTSTRAP_ADMIN_PASSWORD = os.getenv("HOTEL_BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_NAME = os.getenv("HOTEL_BOOTSTRAP_ADMIN_NAME", "Carlos").strip()
STAFF_EMAIL_DOMAIN = "hotellascolinas.com"


def is_valid_staff_email(email: str) -> bool:
    normalized = email.strip().casefold()
    pattern = rf"[a-z0-9]+(?:\.[a-z0-9]+)+@{re.escape(STAFF_EMAIL_DOMAIN)}"
    return re.fullmatch(pattern, normalized) is not None


def is_valid_nicaraguan_cedula(value: str) -> bool:
    return re.fullmatch(r"[0-9]{3}-[0-9]{6}-[0-9]{4}[A-Z]", value.strip().upper()) is not None


HOTEL_NAME = os.getenv("HOTEL_NAME", "Hotel Las Colinas").strip()

SMTP_HOST = os.getenv("HOTEL_SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("HOTEL_SMTP_PORT", "587") or "587")
SMTP_USERNAME = os.getenv("HOTEL_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.getenv("HOTEL_SMTP_PASSWORD", "").replace(" ", "")
SMTP_FROM = os.getenv("HOTEL_SMTP_FROM", SMTP_USERNAME).strip()
SMTP_STARTTLS = os.getenv("HOTEL_SMTP_STARTTLS", "true").strip().lower() in {
    "1", "true", "yes", "on"
}
EMAIL_PROVIDER = os.getenv("HOTEL_EMAIL_PROVIDER", "smtp").strip().lower()
EMAIL_FROM = os.getenv("HOTEL_EMAIL_FROM", "").strip() or SMTP_FROM
BREVO_API_KEY = os.getenv("HOTEL_BREVO_API_KEY", "").strip()
PASSWORD_RESET_SECRET = os.getenv("HOTEL_PASSWORD_RESET_SECRET", "")


# Ordinary fixed/mobile contact numbers; country codes exclude national trunk prefixes.
# Reference: ITU national numbering plans and Google libphonenumber metadata.
LATIN_AMERICAN_PHONES = {
    "AR": ("Argentina", "54", (10, 11), "11 2345-6789 / 9 11 2345-6789"),
    "BZ": ("Belice", "501", (7,), "222-1234"),
    "BO": ("Bolivia", "591", (8,), "7123-4567"),
    "BR": ("Brasil", "55", (10, 11), "11 2345-6789 / 11 91234-5678"),
    "CL": ("Chile", "56", (9,), "9 6123-4567"),
    "CO": ("Colombia", "57", (10,), "300 123-4567"),
    "CR": ("Costa Rica", "506", (8,), "8123-4567"),
    "CU": ("Cuba", "53", (8,), "5123-4567"),
    "EC": ("Ecuador", "593", (8, 9), "2 234-5678 / 99 123-4567"),
    "SV": ("El Salvador", "503", (8,), "7123-4567"),
    "GT": ("Guatemala", "502", (8,), "5123-4567"),
    "GY": ("Guyana", "592", (7,), "612-3456"),
    "HT": ("Haití", "509", (8,), "3412-3456"),
    "HN": ("Honduras", "504", (8,), "9123-4567"),
    "MX": ("México", "52", (10,), "55 1234-5678"),
    "NI": ("Nicaragua", "505", (8,), "8888-1234"),
    "PA": ("Panamá", "507", (7, 8), "234-5678 / 6123-4567"),
    "PY": ("Paraguay", "595", (9,), "981 123-456"),
    "PE": ("Perú", "51", (8, 9), "1 234-5678 / 912 345-678"),
    "PR": ("Puerto Rico", "1", (10,), "787 234-5678 / 939 234-5678"),
    "DO": ("República Dominicana", "1", (10,), "809 234-5678 / 829 / 849"),
    "SR": ("Surinam", "597", (6, 7), "212-345 / 812-3456"),
    "UY": ("Uruguay", "598", (8,), "9123-4567"),
    "VE": ("Venezuela", "58", (10,), "412 123-4567"),
}


def split_contact_phone(value: str, country: str | None = None) -> tuple[str, str]:
    """Return region and national number; +1 is shared by PR and DO."""
    value = value.strip()
    if not re.fullmatch(r"\+?[0-9 ()-]+", value):
        raise ValueError("El teléfono solo admite números, espacios, paréntesis y guiones.")
    digits = re.sub(r"[^0-9]", "", value)
    if country is not None and country not in LATIN_AMERICAN_PHONES:
        raise ValueError("Selecciona el país del teléfono.")
    if not value.startswith("+"):
        return country or "NI", digits
    if country is not None:
        if country not in LATIN_AMERICAN_PHONES:
            raise ValueError("Selecciona el país del teléfono.")
        code = LATIN_AMERICAN_PHONES[country][1]
        if not digits.startswith(code):
            raise ValueError("El prefijo del teléfono no coincide con el país seleccionado.")
        return country, digits[len(code):]
    candidates = sorted(LATIN_AMERICAN_PHONES, key=lambda key: len(LATIN_AMERICAN_PHONES[key][1]), reverse=True)
    for region in candidates:
        code = LATIN_AMERICAN_PHONES[region][1]
        if digits.startswith(code):
            national = digits[len(code):]
            if code == "1":
                area_codes = {"PR": ("787", "939"), "DO": ("809", "829", "849")}
                if not national.startswith(area_codes[region]):
                    continue
            return region, national
    raise ValueError("Selecciona un país de Latinoamérica o Centroamérica y revisa el prefijo.")


def format_contact_national(country: str, digits: str) -> str:
    """Display grouping only; never discard excess input."""
    if country == "BR":
        groups = (2, 5, 4) if len(digits) == 11 else (2, 4, 4)
    elif country == "AR":
        groups = (1, 2, 4, 4) if len(digits) == 11 else (2, 4, 4)
    elif country == "MX" and len(digits) == 10:
        groups = (2, 4, 4)
    elif country == "CL" and len(digits) == 9:
        groups = (1, 4, 4)
    elif country in {"EC", "PE"} and len(digits) == 8:
        groups = (1, 3, 4)
    elif country == "EC" and len(digits) == 9:
        groups = (2, 3, 4)
    elif len(digits) == 10:
        groups = (3, 3, 4)
    elif len(digits) == 9:
        groups = (3, 3, 3)
    elif len(digits) == 6:
        groups = (3, 3)
    elif len(digits) == 7:
        groups = (3, 4)
    else:
        groups = (4, 4)
    parts = []
    position = 0
    for size in groups:
        if position < len(digits):
            parts.append(digits[position:position + size])
        position += size
    if position < len(digits):
        parts.append(digits[position:])
    return "-".join(parts)


def normalize_contact_phone(value: str, country: str | None = None) -> str:
    if not value.strip():
        return ""
    region, digits = split_contact_phone(value, country)
    name, code, lengths, example = LATIN_AMERICAN_PHONES[region]
    if len(digits) not in lengths or digits[0] == "0" or (digits[0] == "1" and region not in {"AR", "BR", "PE"}):
        raise ValueError(f"Revisa el teléfono de {name}. Ejemplo: +{code} {example}.")
    if region in {"PR", "DO"}:
        area_codes = {"PR": ("787", "939"), "DO": ("809", "829", "849")}
        if not digits.startswith(area_codes[region]) or digits[3] in "01":
            raise ValueError(f"Revisa el código de área y el número de {name}: {example}.")
    if region == "AR" and len(digits) == 11 and not digits.startswith("9"):
        raise ValueError("El número móvil internacional de Argentina debe comenzar con 9 después de +54.")
    if region == "BR" and len(digits) == 11 and digits[2] != "9":
        raise ValueError("El móvil de Brasil lleva el código de área y un número de 9 dígitos que comienza con 9.")
    return f"+{code} {format_contact_national(region, digits)}"


def validate_desktop_contact(name: str, email: str, phone: str, *, staff: bool = False, phone_country: str | None = None) -> str:
    if not 5 <= len(name.strip()) <= 30:
        raise ValueError("El nombre de usuario debe tener entre 5 y 30 caracteres.")
    email = email.strip()
    if len(email) > 30:
        raise ValueError("El correo electrónico admite un máximo de 30 caracteres.")
    if not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+", email):
        raise ValueError("Escribe un correo válido, por ejemplo nombre@correo.com.")
    if staff and not is_valid_staff_email(email):
        raise ValueError(f"Usa el formato nombre.apellido@{STAFF_EMAIL_DOMAIN} (máximo 30 caracteres).")
    return normalize_contact_phone(phone, phone_country)


def normalize_guest_document(value: str) -> str:
    kind, separator, number = value.strip().partition(":")
    number = number.strip().upper()
    if not separator or not number:
        raise ValueError("Selecciona el tipo de documento y escribe su número.")
    if kind == "CI":
        number = normalize_national_identity("NI", number)
        valid = True
        message = ""
    elif kind.startswith("CI-"):
        number = normalize_national_identity(kind[3:], number)
        valid = True
        message = ""
    elif kind == "PAS":
        # Capture policy only: ICAO numbers are alphanumeric; issuing states vary.
        valid = re.fullmatch(r"[A-Z0-9]{1,30}", number) is not None
        message = "Copia el número del pasaporte: letras A–Z y números, sin espacios ni guiones (máximo 30)."
    elif kind == "OTRO":
        valid = re.fullmatch(r"[A-Z0-9-]{4,30}", number) is not None
        message = "Usa entre 4 y 30 letras A–Z, números o guiones."
    else:
        valid = False
        message = "Selecciona un tipo de documento válido."
    if not valid:
        raise ValueError(message)
    return f"{kind}:{number}"


# Format checks for national identity documents; not registry/authenticity checks.
LATIN_AMERICAN_IDENTITIES = {
    "NI": ("Nicaragua · cédula", r"[0-9]{3}-[0-9]{6}-[0-9]{4}[A-Z]", "000-000000-0000A", (3, 6, 5)),
    "GT": ("Guatemala · DPI/CUI", r"[0-9]{4} [0-9]{5} [0-9]{4}", "0000 00000 0000", (4, 5, 4)),
    "SV": ("El Salvador · DUI", r"[0-9]{8}-[0-9]", "00000000-0", (8, 1)),
    "HN": ("Honduras · DNI", r"[0-9]{4}-[0-9]{4}-[0-9]{5}", "0000-0000-00000", (4, 4, 5)),
    "CR": ("Costa Rica · cédula", r"[1-9]-[0-9]{4}-[0-9]{4}", "1-0000-0000", (1, 4, 4)),
    "PA": ("Panamá · cédula", r"(?:[1-9]|1[0-4]|N|E|PE|(?:[1-9]|1[0-4])(?:AV|PI))-[0-9]{1,7}-[0-9]{1,7}", "Ej. 8-123-4567 / PE-123-4567", ()),
    # Belize has multiple identity documents; do not impose a fictitious cédula layout.
    "BZ": ("Belice · registro electoral", r"[0-9]{1,30}", "Número de registro electoral", ()),
    "AR": ("Argentina · DNI", r"[0-9]{7,8}", "Ej. 12345678", ()),
    "BO": ("Bolivia · cédula", r"[0-9]{1,10}(?:-[A-Z0-9]{2})?", "Ej. 2601642 / 2601642-1K", ()),
    "BR": ("Brasil · CIN/CPF", r"[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2}", "000.000.000-00", (3, 3, 3, 2)),
    "CL": ("Chile · RUN", r"[0-9]{7,8}-[0-9K]", "12345678-K", ()),
    "CO": ("Colombia · cédula", r"[0-9]{1,10}", "Ej. 1234567890", ()),
    "CU": ("Cuba · carné de identidad", r"[0-9]{11}", "11 números, sin guiones", ()),
    "EC": ("Ecuador · cédula", r"[0-9]{10}", "10 números, sin guiones", ()),
    "HT": ("Haití · identificación", r"[A-Z0-9][A-Z0-9 .-]{0,29}", "Número impreso en el documento", ()),
    "MX": ("México · CURP", r"[A-Z]{4}[0-9]{6}[HM][A-Z]{5}[A-Z0-9][0-9]", "AAAA000000HAAAAA00", ()),
    "PY": ("Paraguay · cédula", r"[0-9]{1,9}", "Número de cédula, sin puntos", ()),
    "PE": ("Perú · DNI", r"[0-9]{8}", "8 números, sin guiones", ()),
    "DO": ("República Dominicana · cédula", r"[0-9]{3}-[0-9]{7}-[0-9]", "000-0000000-0", (3, 7, 1)),
    "UY": ("Uruguay · documento de identidad", r"[0-9]{6,7}-[0-9]", "1234567-8", ()),
    "VE": ("Venezuela · cédula", r"(?:[VE]-)?[0-9]{1,9}", "V-12345678 / E-12345678", ()),
    "GY": ("Guyana · identificación", r"[A-Z0-9][A-Z0-9 .-]{0,29}", "Número impreso en el documento", ()),
    "SR": ("Surinam · identificación", r"[A-Z0-9][A-Z0-9 .-]{0,29}", "Número impreso en el documento", ()),
    "PR": ("Puerto Rico · identificación", r"[A-Z0-9][A-Z0-9 .-]{0,29}", "Número de la identificación oficial", ()),

}


LATIN_AMERICAN_IDENTITIES = {country: LATIN_AMERICAN_IDENTITIES[country] for country in LATIN_AMERICAN_PHONES}


def format_national_identity(country: str, value: str) -> str:
    if country not in LATIN_AMERICAN_IDENTITIES:
        raise ValueError("Selecciona el país emisor del documento.")
    groups = LATIN_AMERICAN_IDENTITIES[country][3]
    value = value.strip().upper()
    raw = value.replace("-", "").replace(" ", "").replace(".", "")
    if country in {"AR", "CO", "CU", "EC", "PY", "PE"} and re.fullmatch(r"[0-9]+", raw):
        return raw
    if country in {"CL", "UY"}:
        pattern = r"[0-9]{7,8}[0-9K]" if country == "CL" else r"[0-9]{7,8}"
        if re.fullmatch(pattern, raw):
            return raw[:-1] + "-" + raw[-1]
    if country == "VE" and re.fullmatch(r"[VE][0-9]{1,9}", raw):
        return raw[0] + "-" + raw[1:]
    if not groups:
        return value
    if country == "NI":
        if not re.fullmatch(r"[0-9]{0,13}[A-Z]?", raw) or (any(c.isalpha() for c in raw) and len(raw) != 14):
            return value
    elif not re.fullmatch(r"[0-9]*", raw):
        return value
    # Do not discard surplus input: validation must reject it.
    if len(raw) > sum(groups):
        return value
    parts = []
    offset = 0
    for length in groups:
        if offset < len(raw):
            parts.append(raw[offset:offset + length])
        offset += length
    if country == "BR":
        return ".".join(parts[:3]) + ("-" + parts[3] if len(parts) > 3 else "")
    return (" " if country == "GT" else "-").join(parts)


def normalize_national_identity(country: str, value: str) -> str:
    formatted = format_national_identity(country, value)
    name, pattern, example, groups = LATIN_AMERICAN_IDENTITIES[country]
    if re.fullmatch(pattern, formatted) is None:
        raise ValueError(f"Revisa el documento de {name}: {example}.")
    return formatted


def normalize_payment_reference(reference: str, channel: str | None = None) -> str:
    value = reference.strip().upper()
    pattern = r"[A-Z0-9][A-Z0-9 /_-]{0,59}"
    message = "Escribe el comprobante o referencia: de 1 a 60 letras o números; admite espacios, guiones, / y _."
    if channel is not None:
        if channel not in TRANSFER_REFERENCE_RULES:
            raise ValueError("Selecciona el banco o canal de la transferencia.")
        pattern, placeholder, message = TRANSFER_REFERENCE_RULES[channel]
    if not re.fullmatch(pattern, value):
        raise ValueError(message)
    return value


# Channel identifiers preserve existing BANPRO wallet references in payments.reference.
TRANSFER_PAYMENT_CHANNELS = {
    "LAFISE": "LAFISE",
    "BAC": "BAC Credomatic",
    "BANPRO_BANCA": "Banpro · transferencia bancaria",
    "BANPRO": "Banpro · Billetera Móvil",
}


# Capture rules requested from the customer's supplied recent receipt samples.
# These are application rules for those channels, not an authenticity check or
# a claim that all historical/future receipts from the bank share one format.
TRANSFER_REFERENCE_RULES = {
    "BANPRO": (r"[0-9]{9}", "Ej. 123456789 · 9 dígitos", "Billetera Móvil requiere 9 números, sin espacios ni letras."),
    "LAFISE": (r"[0-9]{12}", "Ej. 000012345678 · 12 dígitos", "LAFISE requiere 12 números, incluidos los ceros iniciales."),
    "BAC": (r"[A-Z0-9][A-Z0-9 /_-]{0,59}", "Referencia del comprobante BAC", "Copia la referencia completa del comprobante BAC."),
    "BANPRO_BANCA": (r"[0-9]{8}", "Ej. 12345678 · 8 dígitos", "Banpro bancario requiere 8 números, sin espacios ni letras."),
}
