"""Room images survive redeploys by living in the shared MySQL database."""
from pathlib import Path
from uuid import uuid4
import hashlib
from io import BytesIO
from PIL import Image, ImageOps
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

def optimized_content(content: bytes) -> bytes:
    # Fit the complete image, never crop; keep original source files on disk.
    with Image.open(BytesIO(content)) as image:
        if image.format == "WEBP" and len(content) <= 512 * 1024 and image.width <= 1600 and image.height <= 1200 and image.getexif().get(274, 1) == 1:
            return content
        image = ImageOps.exif_transpose(image)
        image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "transparency" in image.info else "RGB")
        output = BytesIO()
        image.save(output, format="WEBP", quality=86, method=6)
        return output.getvalue()


def store_photo(photo: RoomPhoto, path: Path) -> None:
    if not 0 < path.stat().st_size <= MAX_PHOTO_BYTES:
        raise ValueError("Cada fotografía debe ocupar como máximo 8 MB.")
    content = optimized_content(path.read_bytes())
    photo.asset = RoomPhotoAsset(content=content, mime_type="image/webp", sha256=hashlib.sha256(content).hexdigest())

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


def prime_photo_cache(session, photos: list[RoomPhoto]) -> None:
    """Download missing desktop images together, rather than one query per file."""
    from sqlalchemy import select
    from sqlalchemy.orm import undefer
    missing = []
    for photo in photos:
        local = Path(photo.path).resolve()
        if local.is_file() and config.PHOTO_DIR.resolve() in local.parents:
            continue
        asset = photo.asset
        if asset is None:
            continue
        cached = config.PHOTO_DIR / f"shared-{photo.id}-{asset.sha256}{EXTENSIONS.get(asset.mime_type, '.img')}"
        if not cached.is_file():
            missing.append(photo)
    if missing:
        session.scalars(select(RoomPhotoAsset).options(undefer(RoomPhotoAsset.content))
                        .where(RoomPhotoAsset.photo_id.in_([photo.id for photo in missing]))).all()
        for photo in missing:
            local_photo_path(photo)
