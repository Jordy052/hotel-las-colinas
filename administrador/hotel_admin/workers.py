from threading import Event
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal


class CancellationToken:
    """Cancelación cooperativa para tareas que puedan dividirse en pasos."""

    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise InterruptedError("La operación fue cancelada.")


class TaskThread(QThread):
    """Ejecuta un servicio fuera del hilo de la interfaz y publica su resultado."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, task: Callable[[CancellationToken], Any], parent=None) -> None:
        super().__init__(parent)
        self.task = task
        self.token = CancellationToken()

    def request_cancel(self) -> None:
        self.token.cancel()

    def run(self) -> None:
        try:
            self.token.raise_if_cancelled()
            result = self.task(self.token)
            self.token.raise_if_cancelled()
        except InterruptedError:
            return
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(result)
