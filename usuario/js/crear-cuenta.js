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

const registerForm = document.querySelector("#register-form");
const registerMessage = document.querySelector("#form-message");
const nameInput = document.querySelector("#name");
const emailInput = document.querySelector("#email");
const passwordInput = document.querySelector("#password");
const confirmationInput = document.querySelector("#confirm");
const contactPhone = HotelPhone.attach(document.querySelector("[data-contact-phone]"));
const verificationPanel = document.querySelector("#email-verification");
const verificationCode = document.querySelector("#verification-code");
const resendVerification = document.querySelector("#resend-verification");
const editRegistration = document.querySelector("#edit-registration");
let verificationId = null;
let verificationRetryAt = 0;
let registrationData = null;
let registrationBusy = false;
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function setMessage(text, state) {
  registerMessage.textContent = text;
  registerMessage.dataset.state = state || "";
}

function showError(field, text) {
  setMessage(text, "error");
  field.parentElement.classList.add("has-error");
  field.setAttribute("aria-invalid", "true");
  field.focus();
}

registerForm.addEventListener("input", function () {
  registerForm.querySelectorAll(".has-error").forEach(function (field) {
    field.classList.remove("has-error");
  });
  registerForm.querySelectorAll("[aria-invalid]").forEach(function (field) {
    field.removeAttribute("aria-invalid");
  });
  setMessage("", "");
});

document.querySelectorAll(".password-toggle").forEach(function (toggle) {
  toggle.addEventListener("click", function () {
    const input = toggle.parentElement.querySelector("input");
    const isHidden = input.type === "password";

    input.type = isHidden ? "text" : "password";
    toggle.classList.toggle("is-visible", isHidden);
    toggle.setAttribute("aria-pressed", String(isHidden));
    toggle.setAttribute(
      "aria-label",
      isHidden ? "Ocultar contraseña" : "Mostrar contraseña"
    );
  });
});

registerForm.addEventListener("submit", async function (event) {
  event.preventDefault();
  if (registrationBusy) return;
  const submitButton = registerForm.querySelector('[type="submit"]');
  const name = nameInput.value.trim();
  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value;
  const confirmation = confirmationInput.value;

  setMessage("", "");
  registerForm.querySelectorAll(".has-error").forEach(function (field) {
    field.classList.remove("has-error");
  });
  registerForm.querySelectorAll("[aria-invalid]").forEach(function (field) {
    field.removeAttribute("aria-invalid");
  });

  if (name.length < 5 || name.length > 30) {
    showError(nameInput, "El nombre de usuario debe tener entre 5 y 30 caracteres.");
    return;
  }
  if (!email || email.length > 160 || !emailPattern.test(email)) {
    showError(emailInput, "Escribe un correo electrónico válido de hasta 160 caracteres.");
    return;
  }
  const telephone = contactPhone.value();
  if (!telephone) return;
  if (password.length < 12 || password.length > 30) {
    showError(passwordInput, "La contraseña debe tener entre 12 y 30 caracteres.");
    return;
  }
  if (password !== confirmation) {
    showError(confirmationInput, "Las contraseñas no coinciden.");
    return;
  }

  if (verificationId && !/^[0-9]{6}$/.test(verificationCode.value.trim())) {
    showError(verificationCode, "Escribe los seis números del código que recibiste.");
    return;
  }
  registrationData = {name, email, password, ...telephone};
  registrationBusy = true;
  submitButton.disabled = true;
  try {
    const result = await HotelApi.post("/auth/register", {
      ...registrationData,
      ...(verificationId ? {verificationId, verificationCode: verificationCode.value.trim()} : {})
    });
    handleRegistrationResult(result);
  } catch (error) {
    setMessage(error.message, "error");
  } finally {
    registrationBusy = false;
    submitButton.disabled = false;
  }
});

function lockRegistrationFields(locked) {
  registerForm.querySelectorAll("input, select, .password-toggle").forEach(field => {
    if (!verificationPanel.contains(field)) field.disabled = locked;
  });
}
function handleRegistrationResult(result) {
  if (result.verificationRequired) {
    verificationId = result.verificationId;
    verificationRetryAt = Date.now() + result.retryAfter * 1000;
    verificationPanel.hidden = false;
    verificationCode.value = "";
    document.querySelector("#verification-description").textContent = "Enviamos un código a " + registrationData.email + ". Vence en 10 minutos. Revisa también el correo no deseado.";
    lockRegistrationFields(true);
    registerForm.querySelector('[type="submit"]').textContent = "Verificar y crear cuenta";
    setMessage(result.message, "success");
    updateResendButton();
    verificationCode.focus();
    return;
  }
  HotelApi.saveSession(result);
  passwordInput.value = "";
  confirmationInput.value = "";
  registrationData = null;
  window.location.href = "habitaciones.html";
}
function updateResendButton() {
  const seconds = Math.max(0, Math.ceil((verificationRetryAt - Date.now()) / 1000));
  resendVerification.disabled = registrationBusy || seconds > 0;
  resendVerification.textContent = seconds ? "Reenviar en " + seconds + " s" : "Reenviar código";
}
setInterval(updateResendButton, 1000);
resendVerification.addEventListener("click", async () => {
  if (registrationBusy || !registrationData || Date.now() < verificationRetryAt) return;
  registrationBusy = true;
  updateResendButton();
  registerForm.querySelector('[type="submit"]').disabled = true;
  try {
    const result = await HotelApi.post("/auth/register", registrationData);
    handleRegistrationResult(result);
  } catch (error) { setMessage(error.message, "error"); }
  finally {
    registrationBusy = false;
    registerForm.querySelector('[type="submit"]').disabled = false;
    updateResendButton();
  }
});
editRegistration.addEventListener("click", () => {
  if (registrationBusy) return;
  verificationId = null;
  registrationData = null;
  verificationPanel.hidden = true;
  verificationCode.value = "";
  lockRegistrationFields(false);
  registerForm.querySelector('[type="submit"]').textContent = "Crear cuenta";
  setMessage("", "");
  emailInput.focus();
});
