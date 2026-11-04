"use strict";

// Booking dates use calendar days in Nicaragua, independent of the device timezone.
(() => {
  const popup = document.createElement("section");
  popup.className = "booking-calendar";
  popup.id = "booking-calendar";
  popup.hidden = true;
  popup.setAttribute("role", "dialog");
  popup.setAttribute("aria-labelledby", "calendar-month");
  popup.innerHTML = `
    <header class="booking-calendar-header">
      <button type="button" data-month-step="-1" aria-label="Mes anterior"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m14 6-6 6 6 6"/></svg></button>
      <h2 id="calendar-month" aria-live="polite"></h2>
      <button type="button" data-month-step="1" aria-label="Mes siguiente"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m10 6 6 6-6 6"/></svg></button>
    </header>
    <div class="booking-calendar-week" aria-hidden="true"><span>L</span><span>M</span><span>X</span><span>J</span><span>V</span><span>S</span><span>D</span></div>
    <div class="booking-calendar-days" role="group" aria-label="Días del mes"></div>
    <footer><span>Hora de Nicaragua</span><button type="button" data-calendar-close>Cerrar</button></footer>`;
  document.body.append(popup);
  const title = popup.querySelector("#calendar-month");
  const grid = popup.querySelector(".booking-calendar-days");
  const previous = popup.querySelector('[data-month-step="-1"]');
  const next = popup.querySelector('[data-month-step="1"]');
  let active = null;
  let month = "";
  let returnFocus = null;
  const date = value => new Date(value + "T12:00:00Z");
  const iso = value => value.toISOString().slice(0, 10);
  const monthKey = value => value.slice(0, 7);
  function shiftedMonth(amount) {
    const day = date(month + "-01");
    day.setUTCMonth(day.getUTCMonth() + amount);
    return monthKey(iso(day));
  }
  function bounds() {
    return {min: active.min || HotelPolicy.today(), max: active.max || HotelPolicy.horizon()};
  }
  function position() {
    if (!active || popup.hidden) return;
    const rect = active.closest(".date-control").getBoundingClientRect();
    const margin = 12;
    popup.style.width = Math.min(332, window.innerWidth - margin * 2) + "px";
    const height = popup.offsetHeight;
    let top = rect.bottom + 8;
    if (top + height > window.innerHeight - margin && rect.top - height - 8 >= margin) top = rect.top - height - 8;
    popup.style.top = Math.max(margin, Math.min(top, window.innerHeight - height - margin)) + "px";
    popup.style.left = Math.max(margin, Math.min(rect.left, window.innerWidth - popup.offsetWidth - margin)) + "px";
  }
  function render(focusValue) {
    const {min, max} = bounds();
    title.textContent = new Intl.DateTimeFormat("es-NI", {month: "long", year: "numeric", timeZone: "UTC"}).format(date(month + "-01"));
    previous.disabled = month <= monthKey(min);
    next.disabled = month >= monthKey(max);
    grid.replaceChildren();
    const start = date(month + "-01");
    const offset = (start.getUTCDay() + 6) % 7;
    const last = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 0)).getUTCDate();
    for (let index = 0; index < offset; index++) {
      const space = document.createElement("span");
      space.setAttribute("aria-hidden", "true");
      grid.append(space);
    }
    const buttons = [];
    for (let day = 1; day <= last; day++) {
      const value = month + "-" + String(day).padStart(2, "0");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = day;
      button.dataset.date = value;
      button.disabled = value < min || value > max;
      button.tabIndex = -1;
      button.setAttribute("aria-label", new Intl.DateTimeFormat("es-NI", {dateStyle: "full", timeZone: "UTC"}).format(date(value)));
      button.setAttribute("aria-pressed", String(value === active.value));
      if (value === HotelPolicy.today()) button.setAttribute("aria-current", "date");
      grid.append(button);
      buttons.push(button);
    }
    const target = buttons.find(button => !button.disabled && button.dataset.date === (focusValue || active.value)) || buttons.find(button => !button.disabled);
    if (target) {
      target.tabIndex = 0;
      if (focusValue) target.focus({preventScroll: true});
    }
    position();
  }
  function close(restore = true) {
    popup.hidden = true;
    if (active) active.closest(".date-control").querySelector(".calendar-button").setAttribute("aria-expanded", "false");
    active = null;
    if (restore && returnFocus) returnFocus.focus({preventScroll: true});
  }
  function open(input, trigger) {
    if (active === input && !popup.hidden) { close(); return; }
    close(false);
    HotelPolicy.limitDates(document.querySelector("#arrival"), document.querySelector("#departure"));
    active = input;
    returnFocus = trigger;
    const {min,max} = bounds();
    const chosen = input.value && input.value >= min && input.value <= max ? input.value : min;
    month = monthKey(chosen);
    popup.hidden = false;
    input.closest(".date-control").querySelector(".calendar-button").setAttribute("aria-expanded", "true");
    render(chosen);
  }
  document.querySelectorAll("[data-open-calendar]").forEach(trigger => {
    const input = document.getElementById(trigger.dataset.openCalendar);
    input.readOnly = true;
    input.setAttribute("aria-haspopup", "dialog");
    input.setAttribute("aria-controls", popup.id);
    trigger.setAttribute("aria-haspopup", "dialog");
    trigger.setAttribute("aria-controls", popup.id);
    trigger.setAttribute("aria-expanded", "false");
    trigger.addEventListener("click", () => open(input, trigger));
    input.addEventListener("click", event => {event.preventDefault(); open(input, input);});
    input.addEventListener("keydown", event => {
      if (["Enter", " ", "ArrowDown"].includes(event.key)) {event.preventDefault(); open(input, input);}
    });
  });
  popup.addEventListener("click", event => {
    const navigation = event.target.closest("[data-month-step]");
    if (navigation && !navigation.disabled) {month = shiftedMonth(Number(navigation.dataset.monthStep)); render(); return;}
    const chosen = event.target.closest("[data-date]");
    if (chosen && !chosen.disabled) {
      active.value = chosen.dataset.date;
      active.dispatchEvent(new Event("input", {bubbles: true}));
      active.dispatchEvent(new Event("change", {bubbles: true}));
      close();
    }
    if (event.target.closest("[data-calendar-close]")) close();
  });
  popup.addEventListener("keydown", event => {
    if (event.key === "Escape") {event.preventDefault(); close(); return;}
    const day = event.target.closest("[data-date]");
    const step = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7}[event.key];
    if (day && step) {
      event.preventDefault();
      const {min,max} = bounds();
      const value = HotelPolicy.addDays(day.dataset.date, step);
      if (value >= min && value <= max) {month = monthKey(value); render(value);}
    }
  });
  document.addEventListener("pointerdown", event => {
    if (active && !popup.contains(event.target) && !active.closest(".date-control").contains(event.target)) close(false);
  });
  document.addEventListener("focusin", event => {
    if (active && !popup.contains(event.target) && !active.closest(".date-control").contains(event.target)) close(false);
  });
  window.addEventListener("resize", position);
  window.addEventListener("scroll", position, true);
})();
