"use strict";
(function () {
  const signedIn = () => Boolean(sessionStorage.getItem("hotel-session-token"));
  function rememberDestination(destination) {
    sessionStorage.setItem("hotel-return-to", destination);
  }
  function actions(destination) {
    const row = document.createElement("div");
    row.className = "guest-access-actions";
    [["Iniciar sesión", "acceso.html", "guest-access-primary"],
     ["Crear cuenta", "crear-cuenta.html", "guest-access-secondary"]].forEach(([label, href, className]) => {
      const link = document.createElement("a");
      link.textContent = label;
      link.href = href;
      link.className = className;
      link.addEventListener("click", () => rememberDestination(destination));
      row.append(link);
    });
    return row;
  }
  function content(title, message, destination) {
    const panel = document.createElement("section");
    panel.className = "guest-access-panel";
    const logo = document.createElement("img");
    logo.src = "../img/hotel-las-colinas.svg";
    logo.alt = "";
    logo.width = 60;
    logo.height = 60;
    const heading = document.createElement("h2");
    heading.textContent = title;
    const text = document.createElement("p");
    text.textContent = message;
    panel.append(logo, heading, text, actions(destination));
    return {panel, heading, text};
  }
  window.HotelGuest = {
    promptReservation() {
      if (signedIn()) return;
      if (document.querySelector("#guest-login-dialog")) return;
      const previousFocus = document.activeElement;
      const dialog = document.createElement("dialog");
      dialog.id = "guest-login-dialog";
      dialog.className = "guest-access-dialog";
      const {panel, heading, text} = content("Inicia sesión para reservar",
        "Para realizar una reserva necesitas tener una cuenta e iniciar sesión. Si aún no tienes una, puedes crearla aquí.", "pago.html");
      heading.id = "guest-login-title";
      text.id = "guest-login-message";
      dialog.setAttribute("aria-labelledby", heading.id);
      dialog.setAttribute("aria-describedby", text.id);
      const close = document.createElement("button");
      close.type = "button";
      close.className = "guest-access-close";
      close.textContent = "×";
      close.setAttribute("aria-label", "Cerrar aviso");
      close.addEventListener("click", () => dialog.close());
      const keepBrowsing = document.createElement("button");
      keepBrowsing.type = "button";
      keepBrowsing.className = "guest-access-browse";
      keepBrowsing.textContent = "Seguir explorando";
      keepBrowsing.addEventListener("click", () => dialog.close());
      panel.append(keepBrowsing);
      dialog.append(close, panel);
      dialog.addEventListener("click", event => { if (event.target === dialog) dialog.close(); });
      dialog.addEventListener("close", () => {
        dialog.remove();
        if (previousFocus && previousFocus.isConnected) previousFocus.focus();
      }, {once: true});
      document.body.append(dialog);
      dialog.showModal();
      panel.querySelector("a").focus();
    },
    showPage(container, title, message, destination) {
      const {panel} = content(title, message, destination);
      container.replaceChildren(panel);
    }
  };
  if (!signedIn()) {
    document.querySelectorAll('nav a[href="reservas.html"], nav a[href="mi-cuenta.html"]').forEach(link => link.remove());
    const label = document.querySelector(".guest-label");
    if (label) {
      label.textContent = "Invitado";
      const login = document.createElement("a");
      login.href = "acceso.html";
      login.textContent = "Iniciar sesión";
      login.addEventListener("click", () => rememberDestination("habitaciones.html"));
      label.before(login);
    }
  }
})();
