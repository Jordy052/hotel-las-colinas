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

const resetForm = document.querySelector("#reset-form");
const resetMessage = document.querySelector("#form-message");
const emailInput = document.querySelector("#email");
const emailStep = document.querySelector("#email-step");
const verificationStep = document.querySelector("#verification-step");
const codeInput = document.querySelector("#code");
const passwordInput = document.querySelector("#password");
const confirmationInput = document.querySelector("#confirm");
const sendCodeButton = document.querySelector("#send-code");
const resendCodeButton = document.querySelector("#resend-code");
const changeEmailButton = document.querySelector("#change-email");
const resetPasswordButton = document.querySelector("#reset-password");
let resendTimer = null;

function setMessage(text, state) {
  resetMessage.textContent = text;
  resetMessage.dataset.state = state || "";
}

function showError(field, text) {
  setMessage(text, "error");
  field.parentElement.classList.add("has-error");
  field.setAttribute("aria-invalid", "true");
  field.focus();
}

function clearErrors() {
  resetForm.querySelectorAll(".has-error").forEach(function (field) {
    field.classList.remove("has-error");
  });
  resetForm.querySelectorAll("[aria-invalid]").forEach(function (field) {
    field.removeAttribute("aria-invalid");
  });
  setMessage("", "");
}

function validateEmail() {
  const email = emailInput.value.trim();
  const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  if (!email || email.length > 160 || !emailPattern.test(email)) {
    showError(emailInput, "Escribe un correo válido de hasta 160 caracteres.");
    return "";
  }
  return email;
}

async function sendCode(button) {
  const email = validateEmail();
  if (!email) {
    return false;
  }

  clearErrors();
  button.disabled = true;
  try {
    await HotelApi.post("/auth/password-reset/request", { email: email });
    emailInput.readOnly = true;
    emailStep.hidden = true;
    verificationStep.hidden = false;
    codeInput.focus();
    setMessage(
      "Si el correo está asociado a una cuenta, recibirás un código. Revisa tu bandeja y correo no deseado.",
      "success"
    );
    startResendTimer();
    return true;
  } catch (error) {
    setMessage(error.message, "error");
    return false;
  } finally {
    button.disabled = button === resendCodeButton && resendTimer !== null;
  }
}

function startResendTimer() {
  if (resendTimer) {
    window.clearInterval(resendTimer);
  }
  let seconds = 60;
  resendCodeButton.disabled = true;
  resendCodeButton.textContent = "Reenviar código (" + seconds + " s)";
  resendTimer = window.setInterval(function () {
    seconds -= 1;
    if (seconds <= 0) {
      window.clearInterval(resendTimer);
      resendTimer = null;
      resendCodeButton.disabled = false;
      resendCodeButton.textContent = "Reenviar código";
      return;
    }
    resendCodeButton.textContent = "Reenviar código (" + seconds + " s)";
  }, 1000);
}

resetForm.addEventListener("input", clearErrors);

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

resetForm.addEventListener("submit", async function (event) {
  event.preventDefault();
  if (verificationStep.hidden) {
    await sendCode(sendCodeButton);
    return;
  }

  const email = validateEmail();
  if (!email) {
    return;
  }
  const code = codeInput.value.trim();
  const newPassword = passwordInput.value;
  const confirmation = confirmationInput.value;
  if (!/^\d{6}$/.test(code)) {
    showError(codeInput, "Escribe el código de 6 dígitos que recibiste por correo.");
    return;
  }
  if (newPassword.length < 12 || newPassword.length > 30) {
    showError(passwordInput, "La contraseña debe tener entre 12 y 30 caracteres.");
    return;
  }
  if (newPassword !== confirmation) {
    showError(confirmationInput, "Las contraseñas no coinciden.");
    return;
  }

  clearErrors();
  resetPasswordButton.disabled = true;
  try {
    await HotelApi.post("/auth/password-reset/confirm", {
      email: email,
      code: code,
      newPassword: newPassword
    });
    HotelApi.clearSession();
    setMessage("Contraseña actualizada. Ya puedes iniciar sesión con tu nueva clave.", "success");
    resetForm.querySelectorAll("input").forEach(function (input) {
      input.value = "";
    });
    resetPasswordButton.textContent = "Contraseña actualizada";
    window.setTimeout(function () {
      window.location.href = "acceso.html";
    }, 1800);
  } catch (error) {
    setMessage(error.message, "error");
    if (error.message.toLowerCase().includes("código") || error.message.toLowerCase().includes("venció")) {
      codeInput.focus();
    }
  } finally {
    resetPasswordButton.disabled = false;
  }
});

resendCodeButton.addEventListener("click", async function () {
  if (!resendCodeButton.disabled) {
    await sendCode(resendCodeButton);
  }
});

changeEmailButton.addEventListener("click", function () {
  if (resendTimer) {
    window.clearInterval(resendTimer);
    resendTimer = null;
  }
  emailInput.readOnly = false;
  emailStep.hidden = false;
  verificationStep.hidden = true;
  codeInput.value = "";
  passwordInput.value = "";
  confirmationInput.value = "";
  resendCodeButton.disabled = false;
  resendCodeButton.textContent = "Reenviar código";
  clearErrors();
  emailInput.focus();
});

codeInput.addEventListener("input", function () {
  codeInput.value = codeInput.value.replace(/\D/g, "").slice(0, 6);
});
