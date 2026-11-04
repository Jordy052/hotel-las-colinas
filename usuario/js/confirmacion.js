(function () {
  const baseUrl = "http://127.0.0.1:8765/api";
  const tokenKey = "hotel-session-token";
  const userKey = "hotel-demo-user";

  async function request(path, options) {
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

const latestKey = "hotel-demo-last-reservation";
const codeFromUrl = new URLSearchParams(window.location.search).get("code");
let reservation = null;

try {
  reservation = JSON.parse(sessionStorage.getItem(latestKey) || "null");
} catch {
  reservation = null;
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

async function showConfirmation() {
  if ((!reservation || reservation.code !== codeFromUrl) && codeFromUrl) {
    try {
      reservation = await HotelApi.get("/reservations/" + encodeURIComponent(codeFromUrl));
      sessionStorage.setItem(latestKey, JSON.stringify(reservation));
    } catch {
      reservation = null;
    }
  }

  if (!reservation || !reservation.room) {
    window.location.replace("habitaciones.html");
    return;
  }

  const room = reservation.room;
  document.querySelector("[data-confirmation-code]").textContent = reservation.code;
  document.querySelector("[data-invoice-link]").href =
    "factura.html?code=" + encodeURIComponent(reservation.code);
  document.querySelector("[data-confirmation-image]").src =
    reservation.roomImage || room.image;
  document.querySelector("[data-confirmation-image]").alt =
    reservation.roomName || room.name;
  document.querySelector("[data-confirmation-room]").textContent =
    reservation.roomName || room.name;
  document.querySelector("[data-confirmation-beds]").textContent =
    reservation.beds || room.beds;
  document.querySelector("[data-confirmation-dates]").textContent =
    formatDate(reservation.arrival) + " al " + formatDate(reservation.departure) +
    " · " + reservation.nights + " noches";
  document.querySelector("[data-confirmation-guests]").textContent =
    reservation.guests + " huéspedes · Pago: " + reservation.paymentStatus;
  document.querySelector("[data-confirmation-policy]").textContent =
    "Entrada desde las " + reservation.checkInTime +
    " · salida hasta las " + reservation.checkOutTime +
    " · Cancelación gratuita hasta " + HotelPolicy.format(reservation.cancellation.deadline) + ". Después: cargo del 30 %.";
  document.querySelector("[data-confirmation-total]").textContent =
    formatMoney(reservation.total);
}

showConfirmation();
