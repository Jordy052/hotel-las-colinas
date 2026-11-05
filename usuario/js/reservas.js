(function () {
  const baseUrl = window.HotelRuntime.apiBaseUrl;
  const tokenKey = "hotel-session-token";
  const userKey = "hotel-demo-user";

  async function request(path, options) {
    if (!baseUrl) throw new Error("El servicio del hotel aún no está publicado. Intenta nuevamente más tarde.");
    const settings = options || {};
    const headers = new Headers(settings.headers || {});
    headers.set("Accept", "application/json");
    if (settings.body !== undefined) {
      headers.set("Content-Type", "application/json");
      settings.body = JSON.stringify(settings.body);
    }
    const token = sessionStorage.getItem(tokenKey);
    if (token) {
      headers.set("Authorization", "Bearer " + token);
    }
    let response;
    try {
      response = await fetch(baseUrl + path, { ...settings, headers: headers });
    } catch {
      throw new Error("El servicio no está disponible en este momento. Intenta de nuevo más tarde.");
    }
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      throw new Error(payload.error || "La solicitud no pudo completarse.");
    }
    return payload;
  }

  function saveSession(payload) {
    sessionStorage.setItem(tokenKey, payload.token);
    sessionStorage.setItem(userKey, JSON.stringify(payload.user));
  }

  function clearSession() {
    sessionStorage.removeItem(tokenKey);
    sessionStorage.removeItem(userKey);
  }

  function getUser() {
    try {
      return JSON.parse(sessionStorage.getItem(userKey) || "null");
    } catch {
      return null;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const label = document.querySelector(".guest-label");
    const user = getUser();
    if (label && user) {
      label.textContent = user.name;
    }
  });

  window.HotelApi = {
    get: function (path) {
      return request(path, { method: "GET" });
    },
    post: function (path, body) {
      return request(path, { method: "POST", body: body });
    },
    getToken: function () {
      return sessionStorage.getItem(tokenKey);
    },
    getUser: getUser,
    saveSession: saveSession,
    clearSession: clearSession
  };
})();
"use strict";

const reservationList = document.querySelector("#reservation-list");
const reservationCount = document.querySelector("#reservation-count");

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, function (character) {
    return {
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[character];
  });
}

function formatMoney(amount) {
  return "C$ " + Number(amount).toLocaleString("es-NI", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function formatDate(value) {
  const parts = value.split("-");
  return parts[2] + "/" + parts[1] + "/" + parts[0];
}

function cancellationDeadline(reservation) {
  return reservation.cancellation.deadline;
}

function hotelToday() {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: "America/Managua", year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(function (part) { return [part.type, part.value]; }));
  return values.year + "-" + values.month + "-" + values.day;
}

function canNotifyEnRoute(reservation) {
  return reservation.status === "Confirmada" && reservation.arrival >= hotelToday();
}

function canCancel(reservation) {
  return reservation.canCancel === true;
}

function renderReservations(reservations) {
  reservationCount.textContent =
    reservations.length + (reservations.length === 1 ? " reserva registrada" : " reservas registradas");

  if (!reservations.length) {
    reservationList.innerHTML =
      '<p class="empty-state">Aún no tienes reservas. Elige una habitación y confirma tu estadía para verla aquí.</p>';
    return;
  }

  reservationList.innerHTML = reservations.map(function (reservation) {
    const room = reservation.room || {};
    const deadline = cancellationDeadline(reservation);
    const cancelButton = canCancel(reservation)
      ? '<button class="button secondary" type="button" data-cancel="' +
        encodeURIComponent(reservation.code) + '">Cancelar reserva</button>'
      : "";
    const enRouteButton = canNotifyEnRoute(reservation)
      ? '<button class="button primary en-route-button" type="button" data-en-route="' +
        encodeURIComponent(reservation.code) + '">Estoy en camino</button>'
      : "";
    const arrivalNotice = reservation.status === "En camino"
      ? '<p class="arrival-notice">Avisaste al hotel que estás en camino. Recepción registrará tu llegada cuando te presentes.</p>'
      : "";
    const summary = reservation.cancellation;
    const paymentLabel = "Pago: " + escapeHtml(reservation.paymentStatus) +
      (reservation.status === "Cancelada" ? " · Cargo: " + formatMoney(summary.cancellationFee) + " · Reembolso: " + formatMoney(summary.refundAmount) : "");

    return (
      '<article class="reservation-card">' +
        '<img src="' + escapeHtml(reservation.roomImage || room.image || "") +
          '" alt="' + escapeHtml(reservation.roomName || room.name || "Habitación") + '">' +
        '<div>' +
          '<p class="available">' + escapeHtml(reservation.code) + ' · ' +
            escapeHtml(reservation.status) + '</p>' +
          '<h2>' + escapeHtml(reservation.roomName || room.name) + '</h2>' +
          '<p>Entrada: ' + formatDate(reservation.arrival) +
            '　Salida: ' + formatDate(reservation.departure) + '</p>' +
          '<p class="reservation-meta">' + reservation.guests + ' huéspedes · ' +
            reservation.nights + ' noches · Puerto Cabezas, Nicaragua</p>' +
          '<p class="payment-state">' + paymentLabel + '</p>' +
          arrivalNotice +
          '<p class="reservation-policy"><strong>Entrada:</strong> desde las ' +
            escapeHtml(reservation.checkInTime) + ' · <strong>Salida:</strong> hasta las ' +
            escapeHtml(reservation.checkOutTime) + '.</p>' +
          '<p class="reservation-policy"><strong>Cancelación gratuita hasta:</strong> ' +
            HotelPolicy.format(deadline) + '. Después: cargo del 30 %; reembolso del 70 %.</p>' +
        '</div>' +
        '<div class="reservation-total">' +
          '<strong>' + formatMoney(reservation.total) + '</strong>' +
          '<span>Total de la estadía</span>' +
          '<a class="button secondary receipt-link" href="factura.html?code=' +
            encodeURIComponent(reservation.code) + '">Ver comprobante</a>' +
          enRouteButton +
          cancelButton +
        '</div>' +
      '</article>'
    );
  }).join("");
}

async function loadReservations() {
  if (!HotelApi.getToken()) {
    reservationCount.textContent = "";
    document.querySelector(".page-heading p:nth-of-type(2)").hidden = true;
    HotelGuest.showPage(reservationList, "Tus reservas en un solo lugar",
      "Inicia sesión para consultar tus reservas y avisar al hotel cuando estés en camino. Si aún no tienes una cuenta, puedes crearla para reservar.", "reservas.html");
    return;
  }
  try {
    const response = await HotelApi.get("/reservations");
    renderReservations(response.reservations || []);
  } catch (error) {
    reservationCount.textContent = "";
    reservationList.innerHTML =
      '<p class="empty-state">' + escapeHtml(error.message) + '</p>';
  }
}

const cancellationDialog = document.querySelector("#cancel-reservation-dialog");
const cancellationDescription = document.querySelector("#cancellation-description");
const cancellationSummary = document.querySelector("[data-cancellation-summary]");
const cancellationError = document.querySelector("[data-cancellation-error]");
const cancellationConfirm = document.querySelector("[data-confirm-cancellation]");
const keepReservation = document.querySelector("[data-keep-reservation]");
const closeCancellation = document.querySelector("[data-close-cancellation]");
let activeCancellation = null;

async function loadCancellationQuote(state, notice = "") {
  cancellationConfirm.disabled = true;
  cancellationSummary.hidden = true;
  cancellationDescription.textContent = "Consultando los importes de tu reserva…";
  cancellationError.textContent = notice;
  state.quote = null;
  try {
    const quote = await HotelApi.get(state.path + "/cancellation-preview");
    if (activeCancellation !== state || !cancellationDialog.open) return;
    state.quote = quote;
    const deadline = HotelPolicy.format(quote.deadline);
    if (quote.isFree) {
      cancellationDescription.textContent = "Todavía estás dentro del período de cancelación gratuita, hasta el " + deadline + ". Puedes cancelar sin que se descuente dinero de tu pago.";
    } else if (quote.cancellationFee > 0) {
      cancellationDescription.textContent = "El período de cancelación gratuita terminó el " + deadline + ". Si cancelas, se descontarán " + formatMoney(quote.cancellationFee) + " de tu pago por haber superado ese plazo.";
    } else {
      cancellationDescription.textContent = "Esta reserva no registra un pago. No se aplicará ningún cargo por cancelarla.";
    }
    document.querySelector("[data-cancellation-paid]").textContent = formatMoney(quote.paidAmount);
    document.querySelector("[data-cancellation-charge]").textContent = formatMoney(quote.cancellationFee);
    document.querySelector("[data-cancellation-percentage]").textContent = quote.cancellationFee > 0 ? "(" + quote.feePercentage + " %)" : "";
    document.querySelector("[data-cancellation-refund]").textContent = formatMoney(quote.refundAmount);
    cancellationSummary.hidden = false;
    cancellationConfirm.disabled = false;
  } catch (error) {
    if (activeCancellation !== state || !cancellationDialog.open) return;
    cancellationDescription.textContent = "No se pudo consultar el importe de la cancelación. Conserva tu reserva y vuelve a intentarlo.";
    cancellationError.textContent = error.message;
  }
}

function openCancellationDialog(button, code, path) {
  if (cancellationDialog.open) return;
  const state = {button, code, path, quote: null, busy: false, completed: false};
  activeCancellation = state;
  button.disabled = true;
  document.querySelector("[data-cancellation-reservation]").textContent = "Reserva " + code;
  cancellationConfirm.textContent = "Sí, cancelar reserva";
  cancellationError.textContent = "";
  cancellationSummary.hidden = true;
  cancellationConfirm.disabled = true;
  cancellationDescription.textContent = "Consultando los importes de tu reserva…";
  keepReservation.disabled = false;
  closeCancellation.disabled = false;
  document.body.classList.add("cancellation-open");
  cancellationDialog.showModal();
  keepReservation.focus();
  loadCancellationQuote(state);
}

function dismissCancellation() {
  if (!activeCancellation?.busy) cancellationDialog.close();
}
keepReservation.addEventListener("click", dismissCancellation);
closeCancellation.addEventListener("click", dismissCancellation);
cancellationDialog.addEventListener("click", function (event) {
  if (event.target !== cancellationDialog) return;
  const box = cancellationDialog.getBoundingClientRect();
  if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dismissCancellation();
});
cancellationDialog.addEventListener("cancel", function (event) {
  if (activeCancellation?.busy) event.preventDefault();
});
cancellationDialog.addEventListener("close", function () {
  const state = activeCancellation;
  activeCancellation = null;
  document.body.classList.remove("cancellation-open");
  if (state?.button.isConnected) {
    if (!state.completed) state.button.disabled = false;
    state.button.focus();
  }
});
cancellationConfirm.addEventListener("click", async function () {
  const state = activeCancellation;
  if (!state || !state.quote || state.busy) return;
  state.busy = true;
  cancellationConfirm.disabled = true;
  keepReservation.disabled = true;
  closeCancellation.disabled = true;
  cancellationConfirm.textContent = "Cancelando…";
  cancellationError.textContent = "";
  try {
    const result = await HotelApi.post(state.path + "/cancel", {acceptedCancellationFee: state.quote.cancellationFee});
    state.completed = true;
    cancellationDialog.close();
    const feedback = document.querySelector("#reservation-feedback");
    feedback.textContent = "Reserva cancelada. Cargo: " + formatMoney(result.cancellation.cancellationFee) + ". Reembolso: " + formatMoney(result.cancellation.refundAmount) + ".";
    await loadReservations();
    feedback.focus({preventScroll: true});
  } catch (error) {
    if (activeCancellation !== state) return;
    state.busy = false;
    keepReservation.disabled = false;
    closeCancellation.disabled = false;
    cancellationConfirm.textContent = "Sí, cancelar reserva";
    await loadCancellationQuote(state, error.message + " Revisa los importes antes de confirmar nuevamente.");
  }
});

reservationList.addEventListener("click", async function (event) {
  const button = event.target.closest("[data-en-route], [data-cancel]");
  if (!button || button.disabled) return;
  const enRoute = button.hasAttribute("data-en-route");
  const code = decodeURIComponent(enRoute ? button.dataset.enRoute : button.dataset.cancel);
  const path = "/reservations/" + encodeURIComponent(code);
  if (!enRoute) {
    openCancellationDialog(button, code, path);
    return;
  }
  if (!window.confirm("¿Avisar al hotel que estás en camino para la reserva " + code + "?")) return;
  const originalText = button.textContent;
  button.disabled = true;
  const feedback = document.querySelector("#reservation-feedback");
  try {
    button.textContent = "Enviando aviso...";
    await HotelApi.post(path + "/en-route", {});
    await loadReservations();
    feedback.textContent = "Aviso enviado. Tu reserva está En camino.";
  } catch (error) {
    feedback.textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
});

loadReservations();
