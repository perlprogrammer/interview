"use strict";

const el = (id) => document.getElementById(id);
const token = new URLSearchParams(location.search).get("token") || "";
const adminToken = localStorage.getItem("musahibe_admin_token") || "";

const POLL_MS = 3000;

let candidateName = ""; // "Namizəd" etiketinin yanında göstərilir
let shown = 0;          // ekranda göstərilən mesaj sayı
let remaining = null;   // qalan saniyə
let tickHandle = null;
let pollHandle = null;
let finished = false;

// ------------------------------------------------------------------ köməkçi

function fail(title, detail) {
  const state = el("state");
  state.className = "state error";
  state.innerHTML = `<h2>${title}</h2><p>${detail}</p>
    <p><a class="btn-back" href="/admin/">← Panelə qayıt</a></p>`;
  el("view").classList.add("hidden");
  state.classList.remove("hidden");
  stopAll();
}

function stopAll() {
  if (tickHandle) { clearInterval(tickHandle); tickHandle = null; }
  if (pollHandle) { clearInterval(pollHandle); pollHandle = null; }
}

function addMessage(role, text, fresh) {
  const wrap = document.createElement("div");
  wrap.className = "msg " + (role === "user" ? "me" : "ai") + (fresh ? " fresh" : "");

  const who = document.createElement("div");
  who.className = "who";

  const label = document.createElement("span");
  label.className = "who-label";
  label.textContent = role === "user" ? "Namizəd" : "Müsahibəçi";
  who.append(label);

  // İzləyici üçün kimin yazdığı aydın olsun — namizədin adı etiketin yanında
  if (role === "user" && candidateName) {
    const name = document.createElement("span");
    name.className = "who-name";
    name.textContent = candidateName;
    who.append(name);
  }

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  wrap.append(who, bubble);
  el("log").append(wrap);

  if (fresh) setTimeout(() => wrap.classList.remove("fresh"), 1600);
  const log = el("log");
  log.scrollTop = log.scrollHeight;
}

// ------------------------------------------------------------------ taymer

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function paintTimer() {
  const box = el("timer");
  if (remaining === null) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  el("timer-value").textContent = formatTime(Math.max(0, remaining));
  box.classList.toggle("warn", remaining <= 300 && remaining > 60);
  box.classList.toggle("danger", remaining <= 60);
}

function startTicking() {
  if (tickHandle || finished || remaining === null) return;
  tickHandle = setInterval(() => {
    remaining = Math.max(0, remaining - 1);
    paintTimer();
  }, 1000);
}

/** Serverdən gələn `timing` obyektini sayğaca tətbiq edir. */
function applyTiming(timing) {
  if (!timing) return;
  remaining = Math.max(0, timing.remaining_seconds);
  paintTimer();
  startTicking();
}

// ------------------------------------------------------------------ yükləmə

async function poll(first = false) {
  let response;
  try {
    response = await fetch(`/api/watch/${encodeURIComponent(token)}`, {
      headers: { "X-Admin-Token": adminToken },
    });
  } catch (_) {
    if (first) fail("Bağlantı xətası", "Serverə qoşulmaq mümkün olmadı.");
    return;
  }

  if (response.status === 401) {
    fail("Giriş tələb olunur", "Sessiyanızın vaxtı bitib. Panelə daxil olun və yenidən cəhd edin.");
    return;
  }
  if (response.status === 403) {
    fail("İcazəniz yoxdur",
         "Canlı izləmə yalnız <b>Baş HR mütəxəssis</b> rolu üçün açıqdır.");
    return;
  }
  if (response.status === 404) {
    fail("Müsahibə tapılmadı", "Bu link mövcud deyil və ya namizəd silinib.");
    return;
  }

  const info = await response.json();

  if (first) {
    candidateName = `${info.first_name} ${info.last_name}`.trim();
    el("subtitle").textContent = `${candidateName} · ${info.role}`;
    el("skills").innerHTML = (info.skills || [])
      .map(() => '<span class="skill-tag"></span>').join("");
    el("skills").querySelectorAll(".skill-tag").forEach((tag, index) => {
      const skill = info.skills[index];
      tag.textContent = `${skill.name} · ${skill.level}/10`;
    });
    el("state").classList.add("hidden");
    el("view").classList.remove("hidden");
  }

  // Yalnız YENİ mesajları əlavə edirik
  const messages = info.messages || [];
  for (let i = shown; i < messages.length; i++) {
    addMessage(messages[i].role, messages[i].content, !first);
  }
  shown = messages.length;

  // Taymer
  if (info.timing) {
    applyTiming(info.timing);
  } else if (info.duration_minutes && info.status === "pending") {
    remaining = info.duration_minutes * 60;
    paintTimer();
  }

  // Status
  if (info.status === "completed") {
    finished = true;
    stopAll();
    remaining = null;
    el("timer").classList.add("hidden");
    el("extend-box").classList.add("hidden");   // bitmiş müsahibə uzadılmır
    el("live").classList.add("ended");
    el("live-text").textContent = "Bitdi";
    el("status-note").textContent = "Müsahibə tamamlandı — hesabat paneldədir.";
  } else if (info.status === "pending") {
    el("status-note").textContent = "Namizəd hələ müsahibəyə başlamayıb.";
  } else {
    el("status-note").textContent = "Müsahibə davam edir…";
  }
}

// -------------------------------------------------------- vaxtın uzadılması

function extendMessage(text, isError) {
  const box = el("extend-msg");
  box.textContent = text;
  box.className = "extend-msg " + (isError ? "err" : "ok");
  setTimeout(() => { box.textContent = ""; box.className = "extend-msg"; }, 5000);
}

el("extend-btn").addEventListener("click", async () => {
  const button = el("extend-btn");
  const minutes = Number(el("extend-min").value);
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 60) {
    extendMessage("1-60 dəqiqə", true);
    return;
  }

  button.disabled = true;
  try {
    const response = await fetch(`/api/watch/${encodeURIComponent(token)}/extend`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ minutes }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Alınmadı");

    // Taymeri dərhal yenilə və qısa müddət yaşıl vurğula
    if (data.timing) applyTiming(data.timing);
    const timer = el("timer");
    timer.classList.add("boost");
    setTimeout(() => timer.classList.remove("boost"), 2500);

    extendMessage(`+${data.added} dəq · ümumi ${data.duration_minutes} dəq`);
  } catch (exception) {
    extendMessage(exception.message, true);
  } finally {
    button.disabled = false;
  }
});

// --------------------------------------------------------------- başlanğıc

(async function init() {
  if (!token) {
    fail("Link natamamdır", "İzləmə linkində müsahibə tokeni yoxdur.");
    return;
  }
  if (!adminToken) {
    fail("Giriş tələb olunur", "Əvvəlcə <a href='/admin/'>panelə daxil olun</a>, sonra izləməni açın.");
    return;
  }

  await poll(true);
  if (!finished) pollHandle = setInterval(() => poll(false), POLL_MS);
})();

// Səhifə bağlananda sorğuları dayandırırıq
window.addEventListener("beforeunload", stopAll);
