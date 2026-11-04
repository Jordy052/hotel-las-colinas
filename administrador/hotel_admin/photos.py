"""Room images survive redeploys by living in the shared MySQL database."""
from pathlib import Path
from uuid import uuid4
import hashlib
from hotel_admin import config
from hotel_admin.models import RoomPhoto, RoomPhotoAsset

MAX_PHOTO_BYTES = 8 * 1024 * 1024
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif", "image/bmp": ".bmp"}

def image_type(content: bytes) -> str:
    if content.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if content.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if content.startswith((b"GIF87a", b"GIF89a")): return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP": return "image/webp"
    if content.startswith(b"BM"): return "image/bmp"
    raise ValueError("Usa una imagen PNG, JPG, WebP, GIF o BMP válida.")

def store_photo(photo: RoomPhoto, path: Path) -> None:
    if not 0 < path.stat().st_size <= MAX_PHOTO_BYTES:
        raise ValueError("Cada fotografía debe ocupar como máximo 8 MB.")
    content = path.read_bytes()
    photo.asset = RoomPhotoAsset(content=content, mime_type=image_type(content), sha256=hashlib.sha256(content).hexdigest())

def read_photo(photo: RoomPhoto) -> tuple[bytes, str]:
    if photo.asset is not None:
        return photo.asset.content, photo.asset.mime_type
    path = Path(photo.path).resolve()
    if config.PHOTO_DIR.resolve() not in path.parents or not path.is_file():
        raise FileNotFoundError("La fotografía no existe.")
    content = path.read_bytes()
    return content, image_type(content)

def local_photo_path(photo: RoomPhoto) -> str:
    path = Path(photo.path).resolve()
    if path.is_file() and config.PHOTO_DIR.resolve() in path.parents:
        return str(path)
    asset = photo.asset
    if asset is None: return photo.path
    suffix = EXTENSIONS.get(asset.mime_type, ".img")
    cached = config.PHOTO_DIR / f"shared-{photo.id}-{asset.sha256}{suffix}"
    if not cached.is_file():
        temporary = cached.with_name(cached.name + "." + uuid4().hex + ".tmp")
        temporary.write_bytes(asset.content)
        temporary.replace(cached)
    return str(cached)
