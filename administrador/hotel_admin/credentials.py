"""Remember desktop credentials in the current Windows user's Credential Manager."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from hotel_admin import config


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME), ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(wintypes.BYTE)), ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR),
    ]


def _target() -> str:
    project = str(config.APP_DIR.resolve()).casefold().encode("utf-8")
    return "HotelLasColinas:Personal:" + hashlib.sha256(project).hexdigest()[:16]


def _api():
    if os.name != "nt":
        raise OSError("Recordar cuenta requiere el almacén de credenciales de Windows.")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_Credential))]
    api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    return api


def _account_target(email: str) -> str:
    normalized = email.strip().casefold().encode("utf-8")
    return _target() + ":Cuenta:" + hashlib.sha256(normalized).hexdigest()


def _read_account(target: str) -> tuple[str, str] | None:
    api = _api()
    pointer = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:
            return None
        raise ctypes.WinError(error)
    try:
        credential = pointer.contents
        password = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-16-le")
        return credential.UserName or "", password
    finally:
        api.CredFree(pointer)


def read_remembered_account(email: str | None = None) -> tuple[str, str] | None:
    if email is None:
        return _read_account(_target())
    normalized = email.strip().casefold()
    saved = _read_account(_account_target(normalized))
    if saved is None:
        # Preserve the account saved by earlier versions.
        saved = _read_account(_target())
    return saved if saved and saved[0].strip().casefold() == normalized else None


def _write_account(target: str, email: str, password: str) -> None:
    api = _api()
    blob = password.encode("utf-16-le")
    buffer = (wintypes.BYTE * len(blob)).from_buffer_copy(blob)
    credential = _Credential()
    credential.Type = 1
    credential.TargetName = target
    credential.UserName = email.strip().lower()
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(wintypes.BYTE))
    credential.Persist = 2  # Same Windows user on this computer, across logon sessions.
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def save_remembered_account(email: str, password: str) -> None:
    # Keep a legacy single-account credential before updating the last-used slot.
    previous = _read_account(_target())
    if previous and previous[0].strip().casefold() != email.strip().casefold():
        previous_target = _account_target(previous[0])
        if _read_account(previous_target) is None:
            _write_account(previous_target, previous[0], previous[1])
    _write_account(_account_target(email), email, password)
    _write_account(_target(), email, password)


def _delete_account(target: str) -> None:
    api = _api()
    if not api.CredDeleteW(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise ctypes.WinError(error)


def forget_remembered_account(email: str | None = None) -> None:
    if email is None:
        _delete_account(_target())
        return
    normalized = email.strip().casefold()
    _delete_account(_account_target(normalized))
    last = _read_account(_target())
    if last and last[0].strip().casefold() == normalized:
        _delete_account(_target())
