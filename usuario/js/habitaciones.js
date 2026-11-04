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

let rooms = [];

const searchForm = document.querySelector("#search-form");
const roomGrid = document.querySelector("#room-grid");
const searchSummary = document.querySelector("#search-summary");
const arrivalInput = document.querySelector("#arrival");
const departureInput = document.querySelector("#departure");
const guestInput = document.querySelector("#guests");
const guestCount = document.querySelector("#guest-count");
const guestDecrease = document.querySelector("#guest-decrease");
const guestIncrease = document.querySelector("#guest-increase");
const sortSelect = document.querySelector("#sort");
const roomDialog = document.querySelector("#room-details");
const dialogImage = document.querySelector("[data-gallery-image]");
const dialogCount = document.querySelector("[data-gallery-count]");
const dialogThumbnails = document.querySelector("[data-gallery-thumbnails]");
const dialogPrevious = document.querySelector("[data-gallery-previous]");
const dialogNext = document.querySelector("[data-gallery-next]");
const dialogReserve = document.querySelector("[data-dialog-reserve]");
let selectedCategory = "Todas";
let activeRoomPhotos = [];
let activePhotoIndex = 0;
const CHECK_IN_TIME = "2:00 p. m.";
const CHECK_OUT_TIME = "12:00 p. m.";

function escapeHtml(value) {
  return String(value || "").replace(/[&<>"']/g, function (character) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
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

function getNightCount() {
  const arrival = new Date(arrivalInput.value + "T00:00:00");
  const departure = new Date(departureInput.value + "T00:00:00");
  return Math.max(1, Math.round((departure - arrival) / 86400000));
}

function updateGuestStepper() {
  const count = Number(guestInput.value);
  guestCount.textContent = count + (count === 1 ? " persona" : " personas");
  guestCount.setAttribute("aria-valuenow", String(count));
  guestDecrease.disabled = count <= 1;
  guestIncrease.disabled = count >= 4;
}

function changeGuestCount(amount) {
  guestInput.value = String(
    Math.min(4, Math.max(1, Number(guestInput.value) + amount))
  );
  updateGuestStepper();
  refreshRooms();
}

function setDefaultDates() {
  const today = new Date();
  const arrival = new Date(today);
  const departure = new Date(today);
  arrival.setDate(today.getDate() + 1);
  departure.setDate(today.getDate() + 3);
  arrivalInput.value = localDateString(arrival);
  departureInput.value = localDateString(departure);
  arrivalInput.min = localDateString(today);
  HotelPolicy.limitDates(arrivalInput, departureInput);
}

async function reserveRoom(room) {
  if (window.roomCheckoutOpening) return;
  if (room && room.availableToBook === false) return;
  if (!room) {
    return;
  }

  const pending = {
    roomId: room.id,
    arrival: arrivalInput.value,
    departure: departureInput.value,
    guests: Number(guestInput.value),
    nights: getNightCount(),
    rate: Number(room.rate),
    room: {
      id: room.id,
      name: room.name,
      category: room.category,
      beds: room.beds,
      image: room.image,
      amenities: room.amenities || []
    }
  };
  sessionStorage.setItem("hotel-demo-pending-reservation", JSON.stringify(pending));

  if (!HotelApi.getToken()) {
    sessionStorage.setItem("hotel-return-to", "pago.html");
    window.location.href = "acceso.html";
    return;
  }
  window.roomCheckoutOpening = true;
  try {
    const hold = await HotelApi.post("/booking-holds", pending);
    pending.holdToken = hold.holdToken;
    sessionStorage.setItem("hotel-demo-pending-reservation", JSON.stringify(pending));
    window.location.href = "pago.html";
  } catch (error) {
    window.roomCheckoutOpening = false;
    await refreshRooms();
    searchSummary.textContent = error.message;
  }
}

function showRoomPhoto(index) {
  if (activeRoomPhotos.length === 0) {
    return;
  }
  activePhotoIndex = (index + activeRoomPhotos.length) % activeRoomPhotos.length;
  const photo = activeRoomPhotos[activePhotoIndex];
  dialogImage.src = photo.url;
  dialogImage.alt = photo.label + " de " + roomDialog.dataset.roomName;
  dialogCount.textContent =
    "FOTO " + (activePhotoIndex + 1) + " DE " + activeRoomPhotos.length;

  dialogThumbnails.querySelectorAll("[data-photo-index]").forEach(function (button) {
    const selected = Number(button.dataset.photoIndex) === activePhotoIndex;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function openRoomDetails(room) {
  if (!room) {
    return;
  }
  const nightCount = getNightCount();
  activeRoomPhotos = room.photos || [{ url: room.image, label: "Vista general" }];
  activePhotoIndex = 0;
  roomDialog.dataset.roomName = room.name;

  document.querySelector("[data-dialog-category]").textContent = room.category;
  document.querySelector("[data-dialog-name]").textContent = room.name;
  document.querySelector("[data-dialog-capacity]").textContent =
    "Hasta " + room.capacity + " huéspedes";
  document.querySelector("[data-dialog-beds]").textContent = room.beds;
  document.querySelector(".dialog-description").textContent =
    room.description || "Un espacio cómodo para disfrutar tu estadía en Puerto Cabezas.";
  document.querySelector("[data-dialog-dates]").textContent =
    "Entrada " + formatDate(arrivalInput.value) +
    " · Salida " + formatDate(departureInput.value) +
    " · " + guestInput.value + " huéspedes · " + nightCount + " noches";
  document.querySelector("[data-dialog-rate]").textContent =
    formatMoney(room.rate) + " / noche";
  document.querySelector("[data-dialog-total]").textContent =
    formatMoney(room.rate * nightCount) + " total por " + nightCount + " noches";
  document.querySelector("[data-dialog-check-in]").textContent = CHECK_IN_TIME;
  document.querySelector("[data-dialog-check-out]").textContent = CHECK_OUT_TIME;
  document.querySelector("[data-dialog-cancellation-deadline]").textContent =
    HotelPolicy.format(getCancellationDeadline(arrivalInput.value));
  dialogReserve.dataset.reserveRoom = String(room.id);

  dialogThumbnails.replaceChildren();
  activeRoomPhotos.forEach(function (photo, index) {
    const thumbnail = document.createElement("button");
    const image = document.createElement("img");
    const caption = document.createElement("span");
    thumbnail.className = "gallery-thumbnail";
    thumbnail.type = "button";
    thumbnail.dataset.photoIndex = String(index);
    thumbnail.setAttribute("aria-label", "Ver foto: " + photo.label);
    thumbnail.setAttribute("aria-pressed", "false");
    image.src = photo.url;
    image.alt = "";
    caption.textContent = photo.label;
    thumbnail.append(image, caption);
    thumbnail.addEventListener("click", function () {
      showRoomPhoto(index);
    });
    dialogThumbnails.append(thumbnail);
  });

  const multiple = activeRoomPhotos.length > 1;
  dialogPrevious.hidden = !multiple;
  dialogNext.hidden = !multiple;
  dialogThumbnails.hidden = !multiple;
  showRoomPhoto(0);
  roomDialog.showModal();
}

function renderRooms() {
  const guestTotal = Number(guestInput.value);
  const nights = getNightCount();
  let visible = rooms.filter(function (room) {
    const categoryMatches =
      selectedCategory === "Todas" || room.category === selectedCategory;
    return room.capacity >= guestTotal && categoryMatches;
  });

  visible.sort(function (first, second) {
    return sortSelect.value === "desc"
      ? second.rate - first.rate
      : first.rate - second.rate;
  });

  document.querySelector("[data-check-in-time]").textContent = CHECK_IN_TIME;
  document.querySelector("[data-check-out-time]").textContent = CHECK_OUT_TIME;
  document.querySelector("[data-search-cancellation]").textContent =
    new Intl.DateTimeFormat("es-NI", {
      day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit",
      timeZone: "America/Managua"
    }).format(new Date(getCancellationDeadline(arrivalInput.value)));
  searchSummary.textContent =
    visible.length + " habitaciones · " + guestTotal + " huéspedes · " +
    nights + " noches · " + formatDate(arrivalInput.value) +
    " al " + formatDate(departureInput.value);

  if (visible.length === 0) {
    roomGrid.innerHTML =
      '<p class="empty-message">No hay habitaciones disponibles con estos datos.</p>';
    return;
  }

  roomGrid.innerHTML = visible.map(function (room) {
    const amenities = (room.amenities || []).length
      ? room.amenities.map(escapeHtml).join(" · ")
      : "Comodidades por confirmar";
    return (
      '<article class="room-card">' +
        '<img src="' + escapeHtml(room.image) + '" alt="' +
          escapeHtml(room.name) + '">' +
        '<div class="room-content">' +
          '<p class="available">' + (room.availableToBook === false ? 'PENDIENTE DE PAGO' : 'DISPONIBLE') + '</p>' +
          '<h3>' + escapeHtml(room.name) + '</h3>' +
          '<p class="room-meta">' + room.capacity + ' huéspedes · ' +
            escapeHtml(room.beds) + '</p>' +
          '<p class="amenities">' + amenities + '</p>' +
          '<p class="price">' + formatMoney(room.rate) + ' / noche</p>' +
          '<p class="room-meta">' + formatMoney(room.rate * nights) +
            ' por ' + nights + ' noches</p>' +
          '<div class="room-actions">' +
            '<button class="button primary" type="button" data-reserve="' +
              room.id + '"' + (room.availableToBook === false ? ' disabled' : '') + '>' + (room.availableToBook === false ? 'Pendiente' : 'Reservar') + '</button>' +
            '<button class="button secondary" type="button" data-details="' +
              room.id + '">Ver detalles</button>' +
          '</div>' +
        '</div>' +
      '</article>'
    );
  }).join("");
}

let latestRoomSearch = 0;
async function refreshRooms(background = false) {
  const searchNumber = ++latestRoomSearch;
  if (!arrivalInput.value || !departureInput.value) {
    return;
  }
  if (!background) roomGrid.innerHTML = '<p class="empty-message">Consultando disponibilidad…</p>';
  try {
    const query = new URLSearchParams({
      check_in: arrivalInput.value,
      check_out: departureInput.value,
      guests: guestInput.value
    });
    const result = await HotelApi.get("/rooms?" + query.toString());
    if (searchNumber !== latestRoomSearch) return;
    const incoming = result.rooms || [];
    if (background && JSON.stringify(incoming) === JSON.stringify(rooms)) return;
    rooms = incoming;
    renderRooms();
  } catch (error) {
    if (background || searchNumber !== latestRoomSearch) return;
    rooms = [];
    searchSummary.textContent = "";
    roomGrid.innerHTML =
      '<p class="empty-message">' + escapeHtml(error.message) + '</p>';
  }
}

guestDecrease.addEventListener("click", function () {
  changeGuestCount(-1);
});
guestIncrease.addEventListener("click", function () {
  changeGuestCount(1);
});

searchForm.addEventListener("submit", function (event) {
  event.preventDefault();
  refreshRooms();
});
searchForm.addEventListener("change", function (event) {
  HotelPolicy.limitDates(arrivalInput, departureInput);
  refreshRooms();
});
sortSelect.addEventListener("change", renderRooms);

document.querySelectorAll(".filter").forEach(function (button) {
  button.addEventListener("click", function () {
    selectedCategory = button.dataset.category;
    document.querySelectorAll(".filter").forEach(function (filterButton) {
      filterButton.classList.toggle("active", filterButton === button);
    });
    renderRooms();
  });
});

roomGrid.addEventListener("click", function (event) {
  const reserveButton = event.target.closest("[data-reserve]");
  const detailsButton = event.target.closest("[data-details]");
  if (reserveButton) {
    reserveRoom(rooms.find(function (room) {
      return room.id === Number(reserveButton.dataset.reserve);
    }));
  }
  if (detailsButton) {
    openRoomDetails(rooms.find(function (room) {
      return room.id === Number(detailsButton.dataset.details);
    }));
  }
});

dialogPrevious.addEventListener("click", function () {
  showRoomPhoto(activePhotoIndex - 1);
});
dialogNext.addEventListener("click", function () {
  showRoomPhoto(activePhotoIndex + 1);
});
dialogReserve.addEventListener("click", function () {
  const room = rooms.find(function (item) {
    return item.id === Number(dialogReserve.dataset.reserveRoom);
  });
  reserveRoom(room);
});
document.querySelector("[data-close-dialog]").addEventListener("click", function () {
  roomDialog.close();
});
roomDialog.addEventListener("click", function (event) {
  if (event.target === roomDialog) {
    roomDialog.close();
  }
});

setDefaultDates();
updateGuestStepper();
refreshRooms();

// Keep pending availability current without allowing stale searches to overwrite newer ones.
setInterval(() => { if (!document.hidden && !window.roomCheckoutOpening) refreshRooms(true); }, 5000);
window.addEventListener("pageshow", () => { window.roomCheckoutOpening = false; });
