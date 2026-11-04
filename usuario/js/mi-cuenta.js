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

const accountName = document.querySelector("#account-name");
const accountEmail = document.querySelector("#account-email");
const profileName = document.querySelector("#profile-name");
const accountAvatar = document.querySelector("#account-avatar");
const sessionStatus = document.querySelector("#session-status");
const userChip = document.querySelector("#account-user-chip");
const contactPhone = HotelPhone.attach(document.querySelector("[data-contact-phone]"));
const phoneForm = document.querySelector("#phone-form");
let savedPhone = "";
const editPhoneButton = document.querySelector("#edit-phone");
const phoneDisplay = document.querySelector("#account-phone");
const phoneSaveMessage = document.querySelector("#phone-save-message");
const logoutButton = document.querySelector("#logout-button");

function setProfile(user) {
  accountName.textContent = user.name;
  accountEmail.textContent = user.email;
  savedPhone = user.phone || "";
  contactPhone.fill(savedPhone);
  phoneDisplay.textContent = savedPhone || "Sin registrar";
  editPhoneButton.textContent = savedPhone ? "Editar" : "Agregar";
  editPhoneButton.disabled = false;
  phoneForm.querySelector("[type=submit]").disabled = false;
  profileName.textContent = user.name;
  userChip.textContent = user.name;
  const parts = user.name.trim().split(/\s+/).filter(Boolean);
  const initials = parts.length > 1
    ? parts.slice(0, 2).map(function (part) { return part.charAt(0); }).join("")
    : (parts[0] || "H").slice(0, 2);
  accountAvatar.textContent = initials.toLocaleUpperCase("es");
  accountAvatar.setAttribute("aria-label", "Iniciales de " + user.name);
}

async function loadAccount() {
  if (!HotelApi.getToken()) {
    HotelGuest.showPage(document.querySelector(".account-grid"), "Tu cuenta en Hotel Las Colinas",
      "Inicia sesión para consultar y actualizar tu información personal. Si aún no tienes una cuenta, créala para gestionar tus próximas estancias.", "mi-cuenta.html");
    return;
  }
  try {
    const user = await HotelApi.get("/account");
    sessionStorage.setItem("hotel-demo-user", JSON.stringify(user));
    setProfile(user);
    sessionStatus.textContent = "Sesión activa";
  } catch (error) {
    sessionStatus.textContent = error.message;
  }
}

logoutButton.addEventListener("click", async function () {
  try {
    await HotelApi.post("/auth/logout", {});
  } catch {
    // La sesión local también se elimina si el servidor ya no está disponible.
  }
  HotelApi.clearSession();
  window.location.href = "acceso.html";
});

function closePhoneEditor() {
  phoneForm.hidden = true;
  editPhoneButton.setAttribute("aria-expanded", "false");
  editPhoneButton.focus();
}
editPhoneButton.addEventListener("click", function() {
  contactPhone.fill(savedPhone);
  phoneSaveMessage.textContent = "";
  phoneForm.hidden = false;
  editPhoneButton.setAttribute("aria-expanded", "true");
  document.querySelector("#phone").focus();
});
document.querySelector("#cancel-phone-edit").addEventListener("click", function() {
  contactPhone.fill(savedPhone);
  closePhoneEditor();
});
phoneForm.addEventListener("submit", async function(event) {
  event.preventDefault();
  phoneSaveMessage.textContent="";
  const telephone=contactPhone.value();
  if(!telephone)return;
  const button=phoneForm.querySelector("[type=submit]");
  button.disabled=true;
  try {
    const user=await HotelApi.post("/account/phone",telephone);
    sessionStorage.setItem("hotel-demo-user",JSON.stringify(user));
    setProfile(user);
    closePhoneEditor();
    phoneSaveMessage.dataset.state="success";
    phoneSaveMessage.textContent="Teléfono actualizado correctamente.";
  } catch(error) {
    phoneSaveMessage.dataset.state="error";
    phoneSaveMessage.textContent=error.message;
  } finally {button.disabled=false;}
});

loadAccount();
