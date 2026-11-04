// Hotel Las Colinas: correo transaccional por HTTPS.
// Este proyecto debe pertenecer a la cuenta Gmail remitente.
const HOTEL_PRIVATE_KEY_ = "REEMPLAZAR_CLAVE_PRIVADA";

function configurar() {
  if (HOTEL_PRIVATE_KEY_.length < 40 || HOTEL_PRIVATE_KEY_ === "REEMPLAZAR_CLAVE_PRIVADA") {
    throw new Error("Falta la clave privada del archivo preparado para este proyecto.");
  }
  PropertiesService.getScriptProperties().setProperty("HOTEL_MAIL_SECRET", HOTEL_PRIVATE_KEY_);
  // Solicita autorización de correo sin enviar ningún mensaje.
  const disponible = MailApp.getRemainingDailyQuota();
  console.log("Configuración guardada. Cuota disponible: " + disponible);
}

function doGet() {
  return json_({service: "Hotel Las Colinas · correo", status: "online"});
}

function doPost(event) {
  const secret = PropertiesService.getScriptProperties().getProperty("HOTEL_MAIL_SECRET");
  if (!secret) return json_({ok: false, error: "not_configured"});
  let envelope;
  try {
    const raw = event && event.postData && event.postData.contents;
    if (!raw || raw.length > 20000) throw new Error("invalid");
    envelope = JSON.parse(raw);
    if (!Number.isInteger(envelope.timestamp) || Math.abs(Date.now()/1000 - envelope.timestamp) > 300 ||
        !/^[a-f0-9]{32}$/.test(envelope.requestId || "") || typeof envelope.payload !== "string" ||
        !/^[a-f0-9]{64}$/.test(envelope.signature || "")) throw new Error("invalid");
    const expected = hmac_(envelope.timestamp + "." + envelope.requestId + "." + envelope.payload, secret);
    if (!equal_(expected, envelope.signature)) throw new Error("invalid");
  } catch (error) {
    return json_({ok: false, error: "unauthorized"});
  }
  const requestId = envelope.requestId;
  let payload;
  try {
    payload = JSON.parse(Utilities.newBlob(Utilities.base64Decode(envelope.payload)).getDataAsString("UTF-8"));
  } catch (error) {
    return reply_({ok: false, error: "invalid_payload"}, requestId, secret);
  }
  if (payload.operation === "check") {
    return reply_({ok: true, quotaRemaining: MailApp.getRemainingDailyQuota()}, requestId, secret);
  }
  if (payload.operation !== "send" || typeof payload.to !== "string" || payload.to.length > 254 ||
      !/^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+$/.test(payload.to) ||
      typeof payload.subject !== "string" || !payload.subject.length || payload.subject.length > 250 ||
      /[\r\n]/.test(payload.subject) || typeof payload.body !== "string" || !payload.body.length || payload.body.length > 10000) {
    return reply_({ok: false, error: "invalid_message"}, requestId, secret);
  }
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return reply_({ok: false, error: "busy"}, requestId, secret);
  try {
    const cache = CacheService.getScriptCache();
    const key = "mail:" + requestId;
    const previous = cache.get(key);
    if (previous === "sent") return reply_({ok: true, messageId: requestId}, requestId, secret);
    if (previous) return reply_({ok: false, error: "already_processing"}, requestId, secret);
    if (MailApp.getRemainingDailyQuota() < 1) return reply_({ok: false, error: "daily_quota"}, requestId, secret);
    cache.put(key, "processing", 600);
    try {
      MailApp.sendEmail({to: payload.to, subject: payload.subject, body: payload.body, name: "Hotel Las Colinas"});
      cache.put(key, "sent", 600);
    } catch (error) {
      // Do not retry an uncertain send automatically or expose recipients/codes in logs.
      cache.put(key, "uncertain", 600);
      return reply_({ok: false, error: "delivery_failed"}, requestId, secret);
    }
    return reply_({ok: true, messageId: requestId}, requestId, secret);
  } finally {
    lock.releaseLock();
  }
}

function hmac_(text, secret) {
  return Utilities.computeHmacSha256Signature(text, secret, Utilities.Charset.UTF_8)
    .map(value => (value & 255).toString(16).padStart(2, "0")).join("");
}
function equal_(left, right) {
  if (left.length !== right.length) return false;
  let result = 0;
  for (let index=0; index<left.length; index++) result |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return result === 0;
}
function reply_(result, requestId, secret) {
  const payload = Utilities.base64Encode(JSON.stringify(result), Utilities.Charset.UTF_8);
  return json_({requestId: requestId, payload: payload, signature: hmac_("response." + requestId + "." + payload, secret)});
}
function json_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}
