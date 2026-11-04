"use strict";
window.HotelPolicy = (() => {
  const zone = "America/Managua";
  function instant(value) {
    return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : value + "-06:00");
  }
  function deadline(arrival, created = new Date()) {
    const start = created instanceof Date ? created : instant(created);
    const end = instant(arrival + "T14:00:00");
    return new Date(start.getTime() + Math.floor(Math.max(0, end - start) * 3 / 7 / 1000) * 1000).toISOString();
  }
  function format(value) {
    return new Intl.DateTimeFormat("es-NI", {dateStyle: "short", timeStyle: "medium", timeZone: zone}).format(instant(value)) + " (Nicaragua)";
  }
  function today() {
    const parts = Object.fromEntries(new Intl.DateTimeFormat("en", {timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit"}).formatToParts(new Date()).map(p => [p.type, p.value]));
    return parts.year + "-" + parts.month + "-" + parts.day;
  }
  function addDays(value, count) {
    const day = new Date(value + "T00:00:00Z"); day.setUTCDate(day.getUTCDate() + count);
    return day.toISOString().slice(0,10);
  }
  function horizon(value = today()) {
    const [y,m,d] = value.split("-").map(Number);
    const first = new Date(Date.UTC(y, m - 1 + 8, 1));
    const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth()+1, 0)).getUTCDate();
    first.setUTCDate(Math.min(d,last)); return first.toISOString().slice(0,10);
  }
  function limitDates(arrival, departure) {
    arrival.min = today(); arrival.max = addDays(horizon(), -1); departure.max = horizon();
    departure.min = addDays(arrival.value || today(), 1);
    if (departure.value < departure.min) departure.value = departure.min;
  }
  return {deadline, format, today, addDays, horizon, limitDates, feePercentage: 30};
})();
