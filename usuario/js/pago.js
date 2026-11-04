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

const pendingKey = "hotel-demo-pending-reservation";
const latestKey = "hotel-demo-last-reservation";
const reviewStep = document.querySelector("#review-step");
const paymentStep = document.querySelector("#payment-step");
const continueButton = document.querySelector("[data-continue-payment]");
const saveReservationButton = document.querySelector("[data-simulate-payment]");
const backButton = document.querySelector("[data-back-to-review]");
const acceptPolicy = document.querySelector("[data-accept-policy]");
const paymentMessage = document.querySelector("[data-payment-error]");
let paymentInProgress = false;
let checkoutReady = false;
let checkoutCompleted = false;
let holdExpiresAt = 0;
let holdServerOffset = 0;
const CHECK_IN_TIME = "2:00 p. m.";
const CHECK_OUT_TIME = "12:00 p. m.";

let pendingReservation = null;
try {
  pendingReservation = JSON.parse(sessionStorage.getItem(pendingKey) || "null");
} catch {
  pendingReservation = null;
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

function localDateString(value) {
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0")
  ].join("-");
}

function getCancellationDeadline(arrivalValue) {
  return HotelPolicy.deadline(arrivalValue);
}

function setStep(stepNumber) {
  const review = stepNumber === 1;
  reviewStep.hidden = !review;
  paymentStep.hidden = review;
  document.querySelector("[data-step-label]").textContent =
    "PASO " + stepNumber + " DE 3";
  document.querySelector("[data-page-title]").textContent =
    review ? "Revisa tu reserva" : "Confirma tu reserva";
  document.querySelector("[data-page-description]").textContent =
    review
      ? "Confirma los detalles antes de registrar la reserva."
      : "Completa los datos de pago y confirma tu reserva.";
  document.querySelectorAll("[data-progress-step]").forEach(function (item) {
    const itemStep = Number(item.dataset.progressStep);
    item.classList.toggle("active", itemStep === stepNumber);
    item.classList.toggle("completed", itemStep < stepNumber);
  });
}

function showReservationDetails() {
  if (!pendingReservation || !pendingReservation.room) {
    window.location.replace("habitaciones.html");
    return false;
  }
  if (!HotelApi.getToken()) {
    sessionStorage.setItem("hotel-return-to", "pago.html");
    window.location.replace("acceso.html");
    return false;
  }

  const room = pendingReservation.room;
  const rate = Number(pendingReservation.rate);
  const total = rate * Number(pendingReservation.nights);
  const deadline = getCancellationDeadline(pendingReservation.arrival);
  const cancellationFeePercentage = HotelPolicy.feePercentage;
  const cancellationFeeAmount = total * cancellationFeePercentage / 100;

  pendingReservation.rate = rate;
  pendingReservation.total = total;
  pendingReservation.cancellationDeadline = deadline;
  pendingReservation.cancellationFeePercentage = cancellationFeePercentage;
  pendingReservation.cancellationFeeAmount = cancellationFeeAmount;

  document.querySelector("[data-room-image]").src = room.image;
  document.querySelector("[data-room-image]").alt = room.name;
  document.querySelector("[data-room-category]").textContent = room.category;
  document.querySelector("[data-room-name]").textContent = room.name;
  document.querySelector("[data-room-description]").textContent =
    pendingReservation.guests + " huéspedes · " + room.beds;
  document.querySelector("[data-arrival]").textContent =
    formatDate(pendingReservation.arrival);
  document.querySelector("[data-departure]").textContent =
    formatDate(pendingReservation.departure);
  document.querySelector("[data-guests]").textContent =
    pendingReservation.guests + " personas";
  document.querySelector("[data-rate-line]").textContent =
    formatMoney(rate) + " × " + pendingReservation.nights + " noches";
  document.querySelector("[data-subtotal]").textContent = formatMoney(total);
  document.querySelector("[data-total]").textContent = formatMoney(total);
  document.querySelector("[data-compact-room]").textContent = room.name;
  document.querySelector("[data-compact-dates]").textContent =
    formatDate(pendingReservation.arrival) + " al " +
    formatDate(pendingReservation.departure) + " · " +
    pendingReservation.nights + " noches";
  document.querySelector("[data-compact-total]").textContent = formatMoney(total);
  document.querySelector("[data-payment-check-in]").textContent = CHECK_IN_TIME;
  document.querySelector("[data-payment-check-out]").textContent = CHECK_OUT_TIME;
  document.querySelector("[data-payment-cancellation-deadline]").textContent =
    HotelPolicy.format(deadline);
  document.querySelector("[data-payment-advance]").textContent =
    formatMoney(cancellationFeeAmount) + " (" + cancellationFeePercentage + "%)";
  document.querySelector("[data-payment-policy-note]").textContent =
    "El plazo gratuito equivale a 3/7 del tiempo entre la reserva y la entrada. Límite estimado: se fija al confirmar. Después se retiene el 30 % y se reembolsa el 70 %.";
  document.querySelector("[data-compact-policy]").textContent =
    "Límite gratuito estimado: " + HotelPolicy.format(deadline) + ".";
  acceptPolicy.checked = false;
  continueButton.disabled = true;
  setStep(1);
  return true;
}

acceptPolicy.addEventListener("change", function () {
  continueButton.disabled = !acceptPolicy.checked || !checkoutReady;
});

continueButton.addEventListener("click", function () {
  if (!acceptPolicy.checked) {
    acceptPolicy.focus();
    return;
  }
  setStep(2);
  window.scrollTo({ top: 0, behavior: "smooth" });
});

backButton.addEventListener("click", function () {
  setStep(1);
  window.scrollTo({ top: 0, behavior: "smooth" });
});

const cardForm = document.querySelector("#card-data-form");
const cardDetailsToggle = document.querySelector("[data-card-details-toggle]");
const cardHolder = document.querySelector("#card-holder");
const cardNumber = document.querySelector("#card-number");
const cardExpiry = document.querySelector("#card-expiry");
const cardCode = document.querySelector("#card-code");
const billingCountry = document.querySelector("#billing-country");
const billingCity = document.querySelector("#billing-city");
const billingAddress = document.querySelector("#billing-address");
const billingRegion = document.querySelector("#billing-region");
const billingPostal = document.querySelector("#billing-postal");
const billingEmail = document.querySelector("#billing-email");
const billingPhone = document.querySelector("#billing-phone");
const checkoutUser = HotelApi.getUser();
if (checkoutUser) {
  billingEmail.value = checkoutUser.email || "";
  billingPhone.value = checkoutUser.phone || "";
}


function setCardError(field, message) {
  document.querySelector("#" + field.id + "-error").textContent = message;
  field.setAttribute("aria-invalid", message ? "true" : "false");
}

function updateCardPreview() {
  const digits = cardNumber.value.replace(/\D/g, "").slice(0, 16);
  cardNumber.value = digits.replace(/(.{4})(?=.)/g, "$1 ");
  const expiryDigits = cardExpiry.value.replace(/\D/g, "").slice(0, 4);
  cardExpiry.value = expiryDigits.length > 2
    ? expiryDigits.slice(0, 2) + "/" + expiryDigits.slice(2)
    : expiryDigits;
  const previewDigits = digits.padEnd(16, "•");
  document.querySelector("[data-card-preview-number]").textContent =
    previewDigits.match(/.{4}/g).join(" ");
  document.querySelector("[data-card-preview-holder]").textContent =
    cardHolder.value.trim().toUpperCase() || "TITULAR DE LA TARJETA";
  document.querySelector("[data-card-preview-expiry]").textContent = cardExpiry.value || "MM/AA";
}

function validateDemoCard() {
  const now = new Date();
  const expiry = /^(0[1-9]|1[0-2])\/(\d{2})$/.exec(cardExpiry.value);
  const validExpiry = expiry && new Date(2000 + Number(expiry[2]), Number(expiry[1]), 1) > now;
  const phoneText = billingPhone.value.trim();
  const phoneDigits = phoneText.replace(/\D/g, "");
  const validPhone = !phoneText || (/^\+?[0-9 ()-]+$/.test(phoneText)
    && phoneDigits.length >= 7 && phoneDigits.length <= 15);
  const checks = [
    [billingEmail, /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(billingEmail.value.trim())
      && billingEmail.value.trim().length <= 254 ? "" : "Escribe un correo electrónico válido."],
    [billingPhone, validPhone ? "" : "Escribe un teléfono de 7 a 15 dígitos; puedes incluir el código del país."],
    [cardHolder, cardHolder.value.trim().length >= 2 ? "" : "Escribe el nombre del titular."],
    [cardNumber, ["4242424242424242", "5200828282828210"].includes(cardNumber.value.replace(/\s/g, ""))
      ? "" : "Utiliza el número indicado en el ejemplo: 5200 8282 8282 8210."],
    [cardExpiry, validExpiry ? "" : "Escribe una fecha vigente con el formato MM/AA."],
    [cardCode, cardCode.value === "123" ? "" : "Utiliza el código indicado en el ejemplo: 123."],
    [billingCountry, billingCountry.value.trim().length >= 2 && billingCountry.value.trim().length <= 80
      ? "" : "Escribe el país de la dirección de facturación."],
    [billingCity, billingCity.value.trim().length >= 2 && billingCity.value.trim().length <= 80
      ? "" : "Escribe la ciudad o municipio."],
    [billingAddress, billingAddress.value.trim().length >= 3 && billingAddress.value.trim().length <= 180
      ? "" : "Escribe la dirección de facturación."],
    [billingRegion, billingRegion.value.trim().length <= 80 ? "" : "El departamento admite hasta 80 caracteres."],
    [billingPostal, !billingPostal.value.trim() || /^[A-Za-z0-9 -]{2,16}$/.test(billingPostal.value.trim())
      ? "" : "El código postal debe contener entre 2 y 16 letras, números, espacios o guiones."]
  ];
  checks.forEach(function (check) {
    setCardError(check[0], check[1]);
  });
  const invalid = checks.find(function (check) { return Boolean(check[1]); });
  if (invalid) {
    cardForm.hidden = false;
    cardDetailsToggle.setAttribute("aria-expanded", "true");
    cardDetailsToggle.textContent = "Ocultar datos de la tarjeta";
    invalid[0].focus();
    return false;
  }
  return true;
}

cardDetailsToggle.addEventListener("click", function () {
  cardForm.hidden = !cardForm.hidden;
  cardDetailsToggle.setAttribute("aria-expanded", String(!cardForm.hidden));
  cardDetailsToggle.textContent = cardForm.hidden ? "Editar datos de la tarjeta" : "Ocultar datos de la tarjeta";
  if (!cardForm.hidden) {
    cardHolder.focus();
  }
});

cardForm.addEventListener("input", function (event) {
  setCardError(event.target, "");
  updateCardPreview();
});

cardForm.addEventListener("submit", function (event) {
  event.preventDefault();
  saveReservationButton.click();
});

saveReservationButton.addEventListener("click", async function () {
  if (paymentInProgress || !checkoutReady || checkoutCompleted) return;
  if (!pendingReservation || !HotelApi.getToken()) {
    sessionStorage.setItem("hotel-return-to", "pago.html");
    window.location.replace("acceso.html");
    return;
  }

  if (!validateDemoCard()) {
    return;
  }
  paymentMessage.textContent = "";
  paymentInProgress = true;
  saveReservationButton.disabled = true;
  saveReservationButton.textContent = "Guardando reserva…";
  try {
    const reservation = await HotelApi.post("/reservations", {
      roomId: pendingReservation.roomId,
      arrival: pendingReservation.arrival,
      departure: pendingReservation.departure,
      guests: pendingReservation.guests,
      simulatePayment: true,
      checkoutToken: pendingReservation.holdToken
    });
    checkoutCompleted = true;
    cardForm.reset();
    updateCardPreview();
    sessionStorage.setItem(latestKey, JSON.stringify(reservation));
    sessionStorage.removeItem(pendingKey);
    window.location.href =
      "confirmacion.html?code=" + encodeURIComponent(reservation.code);
  } catch (error) {
    paymentMessage.textContent = error.message;
    paymentInProgress = false;
    saveReservationButton.disabled = !checkoutReady;
    saveReservationButton.textContent = "Pagar y confirmar reserva";
  }
});

async function initializeCheckout() {
  checkoutReady = false;
  saveReservationButton.disabled = true;
  continueButton.disabled = true;
  try {
    let hold;
    if (pendingReservation.holdToken) {
      hold = await HotelApi.get("/booking-holds/" + pendingReservation.holdToken);
    } else {
      hold = await HotelApi.post("/booking-holds", pendingReservation);
      pendingReservation.holdToken = hold.holdToken;
      sessionStorage.setItem(pendingKey, JSON.stringify(pendingReservation));
    }
    if (hold.state === "Completada") {
      checkoutCompleted = true;
      window.location.replace("confirmacion.html?code=" + encodeURIComponent(hold.code));
      return;
    }
    if (hold.state !== "Pendiente") throw new Error("El apartado venció. Vuelve a elegir una habitación.");
    holdExpiresAt = new Date(hold.expiresAt).getTime();
    holdServerOffset = new Date(hold.serverNow).getTime() - Date.now();
    checkoutReady = true;
    saveReservationButton.disabled = false;
    continueButton.disabled = !acceptPolicy.checked;
    showHoldTime();
  } catch (error) { paymentMessage.textContent = error.message; }
}

const holdNotice = document.createElement("p");
holdNotice.className = "hold-notice";
holdNotice.setAttribute("role", "timer");
holdNotice.setAttribute("aria-live", "off");
document.querySelector(".checkout-heading").after(holdNotice);
function showHoldTime() {
  if (!checkoutReady || checkoutCompleted) return;
  const seconds = Math.max(0, Math.ceil((holdExpiresAt - Date.now() - holdServerOffset) / 1000));
  holdNotice.textContent = "Habitación apartada para ti · Tiempo restante: " + Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
  if (!seconds) {
    holdNotice.textContent = "El apartado venció. Vuelve a elegir una habitación.";
    checkoutReady = false;
    saveReservationButton.disabled = true;
    continueButton.disabled = true;
    paymentMessage.textContent = "El apartado venció. Vuelve a elegir una habitación.";
  }
}
setInterval(showHoldTime, 1000);
async function releaseCheckout() {
  if (checkoutCompleted || paymentInProgress || !pendingReservation?.holdToken) return;
  await HotelApi.post("/booking-holds/" + pendingReservation.holdToken + "/release", {});
  sessionStorage.removeItem(pendingKey);
}
document.querySelectorAll("a[href]").forEach(link => {
  link.addEventListener("click", async event => {
    if (link.getAttribute("href").startsWith("#") || checkoutCompleted) return;
    event.preventDefault();
    if (paymentInProgress) return;
    try { await releaseCheckout(); } catch { /* Expiration also releases abandoned holds. */ }
    window.location.href = link.href;
  });
});
window.addEventListener("pagehide", () => {
  if (checkoutCompleted || paymentInProgress || !pendingReservation?.holdToken || !HotelRuntime.apiBaseUrl) return;
  fetch(HotelRuntime.apiBaseUrl + "/booking-holds/" + pendingReservation.holdToken + "/release", {
    method: "POST", headers: {"Content-Type": "application/json", "Authorization": "Bearer " + HotelApi.getToken()},
    body: "{}", keepalive: true
  }).catch(() => {});
});
window.addEventListener("pageshow", event => { if (event.persisted && pendingReservation) initializeCheckout(); });
if (showReservationDetails()) initializeCheckout();
