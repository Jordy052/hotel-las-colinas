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

const code = new URLSearchParams(window.location.search).get("code");
const receipt = document.querySelector("#receipt-document");
const notFound = document.querySelector("[data-receipt-not-found]");
const printButton = document.querySelector("[data-print-receipt]");

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
function formatDateTime(value) {
  return new Intl.DateTimeFormat("es-NI", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Managua"
  }).format(new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "-06:00"));
}

async function loadReceipt() {
  if (!HotelApi.getToken()) {
    sessionStorage.setItem(
      "hotel-return-to",
      "factura.html?code=" + encodeURIComponent(code || "")
    );
    window.location.replace("acceso.html");
    return;
  }

  try {
    const reservation = await HotelApi.get(
      "/reservations/" + encodeURIComponent(code || "")
    );
    document.title = reservation.receiptCode + " · Comprobante de reserva";
    document.querySelector("[data-receipt-code]").textContent =
      reservation.receiptCode;
    document.querySelector("[data-issued-at]").textContent =
      formatDateTime(reservation.issuedAt);
    document.querySelector("[data-booking-code]").textContent = reservation.code;
    document.querySelector("[data-payment-status]").textContent =
      "" + reservation.paymentStatus;
    document.querySelector("[data-guest-name]").textContent = reservation.guestName;
    document.querySelector("[data-guest-email]").textContent = reservation.guestEmail;
    document.querySelector("[data-room-name]").textContent = reservation.roomName;
    document.querySelector("[data-bed-info]").textContent = reservation.beds;
    document.querySelector("[data-nights]").textContent = String(reservation.nights);
    document.querySelector("[data-nightly-rate]").textContent =
      formatMoney(reservation.rate);
    document.querySelector("[data-line-total]").textContent =
      formatMoney(reservation.total);
    document.querySelector("[data-arrival]").textContent =
      formatDate(reservation.arrival);
    document.querySelector("[data-departure]").textContent =
      formatDate(reservation.departure);
    document.querySelector("[data-check-in-time]").textContent =
      reservation.checkInTime;
    document.querySelector("[data-check-out-time]").textContent =
      reservation.checkOutTime;
    document.querySelector("[data-guests]").textContent =
      reservation.guests + " persona(s)";
    document.querySelector("[data-grand-total]").textContent =
      formatMoney(reservation.total);
    document.querySelector("[data-cancellation-policy]").textContent =
      "Cancelación gratuita hasta " + HotelPolicy.format(reservation.cancellation.deadline) + ". Después: cargo del 30 % y reembolso del 70 %.";
    const summary = reservation.cancellation;
    document.querySelector("[data-refund-summary]").hidden = reservation.status !== "Cancelada";
    document.querySelector("[data-paid-amount]").textContent = formatMoney(summary.paidAmount);
    document.querySelector("[data-cancellation-fee]").textContent = formatMoney(summary.cancellationFee);
    document.querySelector("[data-refund-amount]").textContent = formatMoney(summary.refundAmount);
    document.querySelector("[data-net-paid]").textContent = formatMoney(summary.paidAmount - summary.refundAmount);
    receipt.hidden = false;
  } catch (error) {
    notFound.hidden = false;
    notFound.textContent = error.message;
    printButton.disabled = true;
  }
}

printButton.addEventListener("click", function () {
  if (!receipt.hidden) {
    window.print();
  }
});

loadReceipt();
