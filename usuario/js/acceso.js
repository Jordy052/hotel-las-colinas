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

const loginForm = document.querySelector("#login-form");
const message = document.querySelector("#form-message");
const emailInput = document.querySelector("#email");
const passwordInput = document.querySelector("#password");
const passwordToggle = document.querySelector(".password-toggle");
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function setMessage(text, state) {
  message.textContent = text;
  message.dataset.state = state || "";
}

function showError(field, text) {
  setMessage(text, "error");
  field.parentElement.classList.add("has-error");
  field.setAttribute("aria-invalid", "true");
  field.focus();
}

loginForm.addEventListener("input", function () {
  loginForm.querySelectorAll(".has-error").forEach(function (field) {
    field.classList.remove("has-error");
  });
  loginForm.querySelectorAll("[aria-invalid]").forEach(function (field) {
    field.removeAttribute("aria-invalid");
  });
  setMessage("", "");
});

passwordToggle.addEventListener("click", function () {
  const isHidden = passwordInput.type === "password";

  passwordInput.type = isHidden ? "text" : "password";
  passwordToggle.classList.toggle("is-visible", isHidden);
  passwordToggle.setAttribute("aria-pressed", String(isHidden));
  passwordToggle.setAttribute(
    "aria-label",
    isHidden ? "Ocultar contraseña" : "Mostrar contraseña"
  );
});

loginForm.addEventListener("submit", async function (event) {
  event.preventDefault();
  const submitButton = loginForm.querySelector('[type="submit"]');
  const email = emailInput.value.trim().toLowerCase();
  const password = passwordInput.value;

  setMessage("", "");
  loginForm.querySelectorAll(".has-error").forEach(function (field) {
    field.classList.remove("has-error");
  });
  loginForm.querySelectorAll("[aria-invalid]").forEach(function (field) {
    field.removeAttribute("aria-invalid");
  });

  if (!email || email.length > 160 || !emailPattern.test(email)) {
    showError(emailInput, "Escribe un correo electrónico válido.");
    return;
  }
  if (!password) {
    showError(passwordInput, "Escribe tu contraseña.");
    return;
  }
  if (password.length > 30) {
    showError(passwordInput, "La contraseña no puede superar 30 caracteres.");
    return;
  }

  submitButton.disabled = true;
  try {
    const result = await HotelApi.post("/auth/login", {
      email: email,
      password: password
    });
    HotelApi.saveSession(result);
    setMessage("Sesión iniciada correctamente.", "success");

    const returnTo = sessionStorage.getItem("hotel-return-to");
    sessionStorage.removeItem("hotel-return-to");
    const safeReturn = /^[a-z0-9-]+\.html$/i.test(returnTo || "")
      ? returnTo
      : "habitaciones.html";
    window.location.href = safeReturn;
  } catch (error) {
    setMessage(error.message, "error");
    submitButton.disabled = false;
  }
});
