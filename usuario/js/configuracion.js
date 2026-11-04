"use strict";
(function () {
  // Only the API's public HTTPS address belongs here. Never put passwords or database URLs here.
  const publishedApiUrl = "";
  const localPage = location.protocol === "file:" || ["localhost", "127.0.0.1", "::1", "[::1]"].includes(location.hostname);
  const apiBaseUrl = (publishedApiUrl || (localPage ? "http://127.0.0.1:8765/api" : "")).replace(/\/+$/, "");
  window.HotelRuntime = Object.freeze({apiBaseUrl});
})();
